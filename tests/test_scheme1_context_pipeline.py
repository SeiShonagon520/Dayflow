"""Comprehensive verification suite for Scheme 1 architecture contracts & guardrails."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

import config
from bridge import server
from bridge.backup import Backup, export_backup, import_backup
from bridge.settings import read_settings
from core import local_recorder
from core.activity_time import app_minutes, clip_card, summarize_activities
from core.context_extractor import (
    ContextExtractor,
    classify_domain,
    domain_matches,
    parse_ide_or_office_title,
    sanitize_browser_url,
)
from core.email_service import ReportGenerator
from core.llm_provider import DayflowBackendProvider
from core.privacy_filter import PrivacyFilter
from core.text_refiner import (
    RefinementCancelledError,
    TextRefinementWorker,
    build_minimal_outbound_payload,
    validate_refinement_response,
)
from core.types import ActivityCard, ActivitySegment, AppSite, CaptureState
from core.win_event_watcher import WinEventWatcher, compute_tick_lag_ms
from core.window_tracker import WindowInfo, WindowTracker, get_outbound_app_label
from database.storage import StorageManager


@pytest.fixture
def env(tmp_path, monkeypatch):
    storage = StorageManager(tmp_path / "scheme1.db")
    monkeypatch.setattr(server, "_storage", storage)
    monkeypatch.setattr(server, "_recorder", None)
    monkeypatch.setattr(server, "_analysis", None)
    monkeypatch.setattr(server, "_refiner", None)
    monkeypatch.setattr(server, "_provider", None)
    monkeypatch.setattr(server, "_shutting_down", False)
    monkeypatch.setattr(config, "CHUNKS_DIR", tmp_path / "chunks")
    monkeypatch.setattr(config, "API_BASE_URL", "http://127.0.0.1:12345/v1")
    monkeypatch.setattr(config, "API_MODEL", "text-fixture")
    monkeypatch.setattr(config, "API_KEY", "")
    monkeypatch.setattr(config, "IDLE_PAUSE_ENABLED", False)
    yield storage, TestClient(server.app)
    if server._recorder and server._recorder.is_recording:
        server._recorder.stop_recording()
    if server._refiner is not None:
        server._refiner.stop()
    if storage._pool is not None:
        storage.close()


class FakeUia:
    def __init__(self, url: str | None = None, on_query=None):
        self.url = url
        self.on_query = on_query
        self.calls = 0

    def query_browser_url(self, **kwargs):
        self.calls += 1
        if self.on_query:
            return self.on_query(**kwargs)
        return self.url


class FakeMic:
    def __init__(self, apps=None):
        self._apps = apps

    def clear_cache(self):
        pass

    def active_apps(self, now_mono=None):
        return self._apps


class FakeTracker(WindowTracker):
    def __init__(self, active: WindowInfo | None = None, by_hwnd=None):
        super().__init__()
        self._available = True
        self._active = active
        self._by_hwnd = by_hwnd or {}

    def get_active_window(self):
        return self._active

    def get_window_info(self, hwnd: int):
        if hwnd in self._by_hwnd:
            return self._by_hwnd[hwnd]
        return self._active


# ==================== 1. 三态隐私、URL 校验与适配器 ====================


def test_defaults_are_app_only_and_refinement_off(env):
    storage, client = env
    settings = read_settings(storage)
    assert settings["recording_mode"] == "local"
    assert settings["local_context_mode"] == "app_only"
    assert settings["local_ai_refinement"] == "0"
    state = client.get("/api/recording/state").json()
    assert state["contextMode"] == "app_only"
    assert state["refinementEnabled"] is False


def test_three_state_privacy_and_browser_non_private_gate():
    tracker = FakeTracker()
    privacy = PrivacyFilter()
    uia = FakeUia(url="https://github.com/SeiShonagon520/Dayflow?token=abc")
    extractor = ContextExtractor(tracker, privacy, uia_client=uia, mic_monitor=FakeMic())

    # 1. 空窗口 / Unknown / 黑名单进程 -> SENSITIVE_OR_UNKNOWN，绝不触碰 UIA
    assert extractor.extract(None, context_mode="structured").state == CaptureState.SENSITIVE_OR_UNKNOWN
    assert extractor.extract(WindowInfo("Unknown", "abc", 1), context_mode="structured").state == CaptureState.SENSITIVE_OR_UNKNOWN
    assert extractor.extract(WindowInfo("KeePass.exe", "vault", 2), context_mode="structured").state == CaptureState.SENSITIVE_OR_UNKNOWN

    # 2. 浏览器无痕 / 空标题 / 无法确认非私密后缀 -> 统一 SENSITIVE_OR_UNKNOWN，绝不触碰 UIA
    assert extractor.extract(
        WindowInfo("msedge.exe", "GitHub - InPrivate - Microsoft Edge", 3, hwnd=10, process_create_time=100.0),
        context_mode="structured",
    ).state == CaptureState.SENSITIVE_OR_UNKNOWN
    assert extractor.extract(
        WindowInfo("chrome.exe", "", 4, hwnd=11, process_create_time=100.0),
        context_mode="structured",
    ).state == CaptureState.SENSITIVE_OR_UNKNOWN
    assert extractor.extract(
        WindowInfo("chrome.exe", "Ambiguous Window Without Browser Suffix", 5, hwnd=12, process_create_time=100.0),
        context_mode="structured",
    ).state == CaptureState.SENSITIVE_OR_UNKNOWN
    assert uia.calls == 0

    # 3. app_only 下已确认非私密浏览器 -> APP_VERIFIED，不触碰 UIA
    ok_edge = WindowInfo("msedge.exe", "Dayflow - Microsoft Edge", 6, hwnd=13, process_create_time=100.0)
    res_app = extractor.extract(ok_edge, context_mode="app_only")
    assert res_app.state == CaptureState.APP_VERIFIED
    assert res_app.domain is None
    assert uia.calls == 0

    # 4. structured 下已确认非私密浏览器 -> CONTEXT_VERIFIED，仅保留规范化 hostname（无路径/查询串/page_title）
    res_struct = extractor.extract(ok_edge, context_mode="structured")
    assert res_struct.state == CaptureState.CONTEXT_VERIFIED
    assert res_struct.domain == "github.com"
    assert res_struct.category == "编程"
    assert uia.calls == 1

    # 5. 非受支持浏览器（如 brave）非私密 -> 降级 APP_VERIFIED，不调 UIA
    res_brave = extractor.extract(
        WindowInfo("brave.exe", "Docs - Brave", 7, hwnd=14, process_create_time=100.0),
        context_mode="structured",
    )
    assert res_brave.state == CaptureState.APP_VERIFIED
    assert res_brave.domain is None
    assert uia.calls == 1


def test_url_sanitizer_and_domain_boundary():
    privacy = PrivacyFilter()
    assert sanitize_browser_url("https://user:pass@github.com/a", privacy) == ("invalid", None, False)
    assert sanitize_browser_url("chrome://settings/passwords", privacy) == ("invalid", None, False)
    assert sanitize_browser_url("https://example.com/oauth/%74oken/callback", privacy)[0] == "sensitive"
    assert sanitize_browser_url("file:///C:/Users/Alice/Desktop/notes.pdf", privacy) == ("ok", "local-file", False)
    assert sanitize_browser_url("file:///C:/Users/Alice/password.txt", privacy)[0] == "sensitive"
    assert sanitize_browser_url("http://localhost:1420/timeline?x=1", privacy) == ("ok", "localhost:1420", False)
    assert sanitize_browser_url("https://feishu.cn/vc/12345", privacy) == ("ok", "feishu.cn", True)
    assert domain_matches("docs.github.com", "github.com")
    assert not domain_matches("evilgithub.com", "github.com")
    assert classify_domain("evilgithub.com") is None


def test_late_uia_discarded_when_nav_token_or_settings_gen_changes():
    nav = [1]
    gen = [1]
    tracker = FakeTracker()
    privacy = PrivacyFilter()

    def mutate_nav(**kwargs):
        nav[0] += 1
        return "https://github.com/org/repo"

    extractor = ContextExtractor(
        tracker,
        privacy,
        uia_client=FakeUia(on_query=mutate_nav),
        mic_monitor=FakeMic(),
        nav_token_provider=lambda: nav[0],
        settings_gen_provider=lambda: gen[0],
    )
    win = WindowInfo("chrome.exe", "Repo - Google Chrome", 1, hwnd=99, process_create_time=10.0)
    res = extractor.extract(win, context_mode="structured", expected_nav_token=1, expected_settings_gen=1)
    assert res.state == CaptureState.APP_VERIFIED
    assert res.domain is None


def test_ide_office_title_parser_and_secondary_privacy_check():
    assert parse_ide_or_office_title("code", "● server.py - Dayflow [WSL: Ubuntu] - Visual Studio Code") == ("Dayflow", "server.py")
    assert parse_ide_or_office_title("pycharm64", "Dayflow [D:\\github\\Dayflow] – storage.py") == ("Dayflow", "storage.py")
    assert parse_ide_or_office_title("windowsterminal", r"D:\github\Dayflow") == ("Dayflow", None)
    assert parse_ide_or_office_title("code", "Unrecognized Plain Title") == (None, None)


# ==================== 2. WinEvent 边界与投递延迟 ====================


def test_win_event_watcher_overflow_and_lag_invalidation(env, monkeypatch):
    storage, _ = env
    watcher = WinEventWatcher(queue_maxlen=8, delivery_lag_ms=250)
    assert compute_tick_lag_ms(100, 0xFFFFFFFC) == 104  # 32-bit wraparound

    # 延迟超限 -> boundary_uncertain
    item = watcher.push_synthetic_event(kind="namechange", hwnd=10, title_snapshot="Normal", delivery_lag_ms=400)
    assert item.boundary_uncertain is True
    assert watcher.drain()[0].kind == "boundary_uncertain"

    # 队列溢出 -> 清空并产生 boundary_uncertain，作废 nav_token
    prev_tok = watcher.nav_token
    for i in range(12):
        watcher.push_synthetic_event(kind="foreground", hwnd=100 + i, title_snapshot=f"Win {i}")
    drained = watcher.drain()
    assert watcher.nav_token > prev_tok + 12
    assert any(ev.boundary_uncertain for ev in drained)

    # 回放 A -> 敏感窗口 -> A 不被吞掉
    win_a = WindowInfo("Code.exe", "app.py - Dayflow - Visual Studio Code", 1, hwnd=1, process_create_time=1.0)
    tracker = FakeTracker(active=win_a, by_hwnd={1: win_a})
    monkeypatch.setattr(local_recorder, "get_tracker", lambda: tracker)
    rec = local_recorder.LocalActivityRecorder(storage, context_mode="structured", watcher=watcher, use_win_events=True)
    t0 = datetime(2026, 11, 25, 10, 0, 0)
    rec.sample(t0, win_a, now_mono=0.0)
    rec.sample(t0 + timedelta(seconds=2), win_a, now_mono=2.0)
    watcher.push_synthetic_event(kind="namechange", hwnd=1, title_snapshot="我的网银密码 - Visual Studio Code", event_mono=3.0, event_wall=t0 + timedelta(seconds=3))
    watcher.push_synthetic_event(kind="namechange", hwnd=1, title_snapshot=win_a.window_title, event_mono=4.0, event_wall=t0 + timedelta(seconds=4))
    rec._consume_win_events()
    rec.sample(t0 + timedelta(seconds=5), win_a, now_mono=5.0)
    rec._finish()
    cards = storage.get_cards_for_date(t0)
    # 敏感事件必须切开成两张卡并留空档
    assert len(cards) == 2
    assert cards[0].end_time < cards[1].start_time


# ==================== 3. 聚类冲突优先、30s 吸收、精确分段与回拨 ====================


def test_project_conflict_across_missing_context_and_conflict_beats_absorption(env, monkeypatch):
    storage, _ = env
    tracker = FakeTracker()
    monkeypatch.setattr(local_recorder, "get_tracker", lambda: tracker)
    rec = local_recorder.LocalActivityRecorder(storage, context_mode="structured", use_win_events=False)

    t0 = datetime(2026, 11, 25, 9, 0, 0)
    proj_p = WindowInfo("Code.exe", "a.py - ProjectP - Visual Studio Code", 1, hwnd=1, process_create_time=1.0)
    missing = WindowInfo("Code.exe", "Unmatched Title", 1, hwnd=1, process_create_time=1.0)
    proj_q = WindowInfo("Code.exe", "b.py - ProjectQ - Visual Studio Code", 1, hwnd=1, process_create_time=1.0)

    # P 持续 62s（中间夹杂上下文缺失不应擦除 P）-> 冲突项目 Q 10s -> 回到 P：冲突优先必须生成 3 张卡
    for sec in range(0, 63, 2):
        w = missing if 20 <= sec <= 24 else proj_p
        rec.sample(t0 + timedelta(seconds=sec), w, now_mono=float(sec))
    for sec in range(64, 74, 2):
        rec.sample(t0 + timedelta(seconds=sec), proj_q, now_mono=float(sec))
    for sec in range(74, 80, 2):
        rec.sample(t0 + timedelta(seconds=sec), proj_p, now_mono=float(sec))
    rec._finish()

    cards = storage.get_cards_for_date(t0)
    assert len(cards) == 3
    assert [c.title for c in cards] == ["ProjectP · 编程", "ProjectQ · 编程", "ProjectP · 编程"]


def test_cross_app_same_project_merge_and_exact_segment_clipping(env, monkeypatch):
    storage, _ = env
    tracker = FakeTracker()
    monkeypatch.setattr(local_recorder, "get_tracker", lambda: tracker)
    rec = local_recorder.LocalActivityRecorder(storage, context_mode="structured", use_win_events=False)

    # 11:59:00-12:00:00 用 VS Code (Dayflow)，12:00:00-12:01:00 用 Windows Terminal (Dayflow)
    t0 = datetime(2026, 11, 25, 11, 59, 0)
    ide = WindowInfo("Code.exe", "server.py - Dayflow - Visual Studio Code", 1, hwnd=1, process_create_time=1.0)
    term = WindowInfo("WindowsTerminal.exe", r"D:\github\Dayflow", 2, hwnd=2, process_create_time=1.0)
    for sec in range(0, 61, 2):
        rec.sample(t0 + timedelta(seconds=sec), ide, now_mono=float(sec))
    for sec in range(62, 121, 2):
        rec.sample(t0 + timedelta(seconds=sec), term, now_mono=float(sec))
    rec._finish()

    cards = storage.get_cards_for_date(t0)
    assert len(cards) == 1
    card = cards[0]
    assert card.title == "Dayflow · 编程"
    # 查询 12:00 之后，精确分段裁切应将 1.0 分钟全部归属 Windows Terminal，VS Code 为 0
    clipped = clip_card(card, datetime(2026, 11, 25, 12, 0, 0), datetime(2026, 11, 25, 13, 0, 0))
    assert clipped is not None
    mins = app_minutes(clipped)
    assert mins.get("Visual Studio Code", 0.0) == 0.0
    assert abs(mins["Windows Terminal"] - 1.0) < 1e-6


def test_30s_distraction_absorption_and_deep_work_deduction(env, monkeypatch):
    storage, _ = env
    tracker = FakeTracker()
    monkeypatch.setattr(local_recorder, "get_tracker", lambda: tracker)
    rec = local_recorder.LocalActivityRecorder(storage, context_mode="structured", use_win_events=False)

    # 59.5 分钟编程 + 20 秒微信（<=30s 吸收）+ 20 秒编程 = 总跨度 60m10s，但实际专注 59m50s < 60m -> deepWork=0
    t0 = datetime(2026, 11, 25, 10, 0, 0)
    ide = WindowInfo("Code.exe", "app.py - Dayflow - Visual Studio Code", 1, hwnd=1, process_create_time=1.0)
    chat = WindowInfo("WeChat.exe", "聊天", 2, hwnd=2, process_create_time=1.0)

    for sec in range(0, 3571, 3):  # 0..3570s (59m30s)
        rec.sample(t0 + timedelta(seconds=sec), ide, now_mono=float(sec))
    # 3570 -> 3590s (20s 微信)
    for sec in range(3572, 3591, 2):
        rec.sample(t0 + timedelta(seconds=sec), chat, now_mono=float(sec))
    # 3592..3610s 回到 VS Code（单调间隔 20s <= 30s -> 吸收！）
    for sec in range(3592, 3611, 2):
        rec.sample(t0 + timedelta(seconds=sec), ide, now_mono=float(sec))
    rec._finish()

    cards = storage.get_cards_for_date(t0)
    assert len(cards) == 1
    card = cards[0]
    assert len(card.distractions) == 1
    assert card.duration_minutes > 60.0
    # 扣除吸收的 20s 微信分心后实际专注 < 60 分钟，不计入深度工作
    summary = summarize_activities(cards)
    assert summary["deepWork"] == 0
    # 微信时间归属微信而非全部算作 VS Code
    am = app_minutes(card)
    assert am["微信"] > 0


def test_delete_during_candidate_settles_candidate_and_undo_restores_segments_and_clears_lease(env, monkeypatch):
    storage, client = env
    tracker = FakeTracker()
    monkeypatch.setattr(local_recorder, "get_tracker", lambda: tracker)
    rec = local_recorder.LocalActivityRecorder(storage, context_mode="app_only", use_win_events=False)

    t0 = datetime(2026, 11, 25, 14, 0, 0)
    ide = WindowInfo("Code.exe", "main.py", 1, hwnd=1, process_create_time=1.0)
    chat = WindowInfo("WeChat.exe", "chat", 2, hwnd=2, process_create_time=1.0)

    for sec in range(0, 63, 2):
        rec.sample(t0 + timedelta(seconds=sec), ide, now_mono=float(sec))
    for sec in range(64, 71, 2):
        rec.sample(t0 + timedelta(seconds=sec), chat, now_mono=float(sec))

    primary_id = rec._session.card.id
    assert primary_id is not None

    # 模拟删除前卡片有旧租约/版本，随后删除主卡
    with storage._get_connection() as conn:
        conn.execute(
            "UPDATE timeline_cards SET refinement_status='claimed', refinement_lease_id='old-lease', version=3 WHERE id=?",
            (primary_id,),
        )
    resp = client.delete(f"/api/cards/{primary_id}")
    assert resp.status_code == 200
    undo_token = resp.json()["undoToken"]

    # 候选微信时间必须被独立结算保留，且主卡关联分段/事件已被显式清理
    cards_after_delete = storage.get_cards_for_date(t0)
    assert len(cards_after_delete) == 1
    assert cards_after_delete[0].title == "微信"
    with storage._get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM card_segments WHERE card_id=?", (primary_id,)).fetchone()[0] == 0

    # 撤销恢复：必须完整恢复分段，且递增版本、清空租约、标记 is_finalized=1 & skipped
    undo_resp = client.post(
        "/api/cards/restore",
        json={
            "undoToken": undo_token,
            "card": {
                "id": primary_id,
                "category": "编程",
                "title": "Visual Studio Code",
                "summary": "",
                "startTime": t0.isoformat(),
                "endTime": (t0 + timedelta(seconds=62)).isoformat(),
                "appSites": [],
                "distractions": [],
                "productivityScore": 0,
            },
        },
    )
    assert undo_resp.status_code == 200
    with storage._get_connection() as conn:
        row = conn.execute("SELECT * FROM timeline_cards WHERE id=?", (primary_id,)).fetchone()
        segs = conn.execute("SELECT * FROM card_segments WHERE card_id=?", (primary_id,)).fetchall()
        assert row["is_finalized"] == 1
        assert row["session_token"] is None
        assert row["version"] == 4  # 3 + 1，旧请求凭 version=3 无法提交
        assert row["refinement_lease_id"] is None
        assert row["refinement_status"] == "skipped"
        assert len(segs) >= 1

    # 旧租约尝试回写必须被拒绝（committed=0）
    assert storage.commit_refinement_results(
        "old-lease",
        [{"id": primary_id, "expected_version": 3, "category": "编程", "title": "Hijack", "summary": "x", "productivity_score": 90}],
    ) == 0


def test_watermark_survives_delete_and_clock_rollback_prevents_overlap(env, monkeypatch):
    storage, _ = env
    tracker = FakeTracker()
    monkeypatch.setattr(local_recorder, "get_tracker", lambda: tracker)
    t0 = datetime(2026, 11, 25, 16, 0, 0)
    cid = storage.save_card(
        ActivityCard(category="编程", title="Visual Studio Code", start_time=t0, end_time=t0 + timedelta(minutes=10), source="local"),
        source="local",
    )
    assert storage.delete_card(cid)
    wm = storage.get_local_watermark()
    assert wm == t0 + timedelta(minutes=10)

    rec = local_recorder.LocalActivityRecorder(storage, context_mode="app_only", use_win_events=False)
    rec._watermark = wm
    # 墙钟回拨到水位之前：拒绝开重叠新卡
    rec.sample(t0 + timedelta(minutes=5), WindowInfo("Code.exe", "x", 1), now_mono=1.0)
    rec._finish()
    assert storage.get_cards_for_date(t0) == []


# ==================== 4. 精炼原子门控、终态租约、持久额度与外发隔离 ====================


def test_refinement_can_toggle_while_recording_and_outbound_uses_fixed_labels(env, monkeypatch):
    storage, client = env
    tracker = FakeTracker(active=WindowInfo("Code.exe", "secret.py", 1, hwnd=1, process_create_time=1.0))
    monkeypatch.setattr(local_recorder, "get_tracker", lambda: tracker)

    assert client.post("/api/recording/start").status_code == 200
    # 录制期间开启与关闭 local_ai_refinement 均允许（不返 409）
    assert client.post("/api/settings", json={"values": {"local_ai_refinement": "1"}}).status_code == 200
    assert client.post("/api/settings", json={"values": {"local_ai_refinement": "0"}}).status_code == 200
    # 修改 local_context_mode 属于 RECORDING_KEYS，录制中必须返回 409
    assert client.post("/api/settings", json={"values": {"local_context_mode": "structured"}}).status_code == 409
    assert client.post("/api/recording/stop").status_code == 200

    # 校验最小外发清单：仅含固定应用标签，未知进程折叠为 "其他应用"，无标题/域名/项目
    card = ActivityCard(
        id=42,
        category="编程",
        title="SecretProject · 编程",
        summary="项目：SecretProject；站点：private.corp.local",
        start_time=datetime(2026, 11, 25, 10, 0),
        end_time=datetime(2026, 11, 25, 10, 30),
        segments=[
            ActivitySegment(datetime(2026, 11, 25, 10, 0), datetime(2026, 11, 25, 10, 20), "Visual Studio Code", False),
            ActivitySegment(datetime(2026, 11, 25, 10, 20), datetime(2026, 11, 25, 10, 30), "my_secret_internal_tool.exe", False),
        ],
    )
    payload = build_minimal_outbound_payload([card])
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "SecretProject" not in serialized
    assert "private.corp.local" not in serialized
    assert "my_secret_internal_tool" not in serialized
    assert {a["name"] for a in payload[0]["app_sites"]} == {"Visual Studio Code", "其他应用"}
    assert get_outbound_app_label("unknown_custom.exe") == "其他应用"


def test_refinement_third_attempt_lease_expiry_terminal_and_persisted_quota(tmp_path):
    db_path = tmp_path / "quota.db"
    s1 = StorageManager(db_path)
    t0 = datetime(2026, 11, 25, 9, 0)
    cid = s1.save_card(
        ActivityCard(category="编程", title="Visual Studio Code", start_time=t0, end_time=t0 + timedelta(minutes=20), source="local"),
        source="local",
    )
    # 模拟 3 次领取均崩溃且租约过期 -> 第 3 次到期收口为终态 failed
    for attempt in range(3):
        claimed = s1.claim_refinement_batch(f"lease-{attempt}", now_ts=1000.0 + attempt * 300, lease_ttl=60.0, daily_limit=24)
        assert [c.id for c in claimed] == [cid]
    rec = s1.reconcile_expired_refinement_leases(now_ts=3000.0, max_attempts=3)
    assert rec["failed"] == 1
    with s1._get_connection() as conn:
        assert conn.execute("SELECT refinement_status FROM timeline_cards WHERE id=?", (cid,)).fetchone()[0] == "failed"

    # 验证每日额度跨重启持久化（用 daily_limit=3，今天已经用了 3 批，新建 StorageManager 后应直接拒绝）
    s1.close()
    s2 = StorageManager(db_path)
    cid2 = s2.save_card(
        ActivityCard(category="工作", title="Microsoft Word", start_time=t0 + timedelta(hours=1), end_time=t0 + timedelta(hours=1, minutes=15), source="local"),
        source="local",
    )
    assert s2.claim_refinement_batch("lease-after-restart", now_ts=4000.0, daily_limit=3) == []
    assert [c.id for c in s2.claim_refinement_batch("lease-under-limit", now_ts=4000.0, daily_limit=4)] == [cid2]
    s2.close()


def test_refinement_disable_gate_linearizes_pre_send_and_commit(env):
    storage, _ = env
    t0 = datetime(2026, 11, 25, 11, 0)
    cid = storage.save_card(
        ActivityCard(category="编程", title="Visual Studio Code", start_time=t0, end_time=t0 + timedelta(minutes=30), source="local"),
        source="local",
    )

    class BlockingProvider(DayflowBackendProvider):
        def __init__(self, worker_ref):
            super().__init__("http://127.0.0.1:12345/v1", "", "fixture")
            self._worker_ref = worker_ref

        async def refine_local_cards(self, cards_payload, *, max_tokens=1024, pre_send_hook=None):
            # 在真正发送前关闭开关 -> pre_send_hook 必须抛出 RefinementCancelledError 拦截发送
            self._worker_ref.configure(enabled=False, bump_generation=True)
            if pre_send_hook is not None:
                await pre_send_hook(None)
            return [{"id": cid, "category": "编程", "title": "ShouldNotWrite", "summary": "x", "productivity_score": 88}]

    worker = TextRefinementWorker(storage)
    worker._provider_factory = lambda: BlockingProvider(worker)
    worker._enabled = True
    result = asyncio.run(worker.run_once_manual())
    assert result["committed"] == 0
    assert result["reason"] == "cancelled"
    assert storage.get_cards_for_date(t0)[0].title == "Visual Studio Code"


def test_visual_recent_cards_filter_and_email_outbound_isolation(env, monkeypatch):
    storage, _ = env
    t0 = datetime(2026, 11, 25, 9, 0)
    # 先写一条合法视觉卡，再写 6 条较新的本机卡（若先 LIMIT 5 再过滤会拿到 0 条，必须先过滤再 LIMIT 5）
    from core.types import AnalysisBatch, BatchStatus, ChunkStatus, VideoChunk
    chunk_id = storage.save_chunk(VideoChunk(file_path="a.mp4", start_time=t0, end_time=t0 + timedelta(minutes=1), duration_seconds=60, status=ChunkStatus.PENDING))
    bid = storage.claim_analysis_batch(AnalysisBatch(chunk_ids=[chunk_id], start_time=t0, end_time=t0 + timedelta(minutes=1), status=BatchStatus.PROCESSING))
    storage.commit_analysis_batch(
        bid,
        [chunk_id],
        [{"text": "ok"}],
        [ActivityCard(category="编程", title="Verified Visual Card", start_time=t0, end_time=t0 + timedelta(minutes=1))],
    )
    for i in range(6):
        storage.save_card(
            ActivityCard(
                category="编程",
                title=f"SecretLocalRepo-{i} · 编程",
                summary="站点：internal.secret.local",
                start_time=t0 + timedelta(minutes=10 + i * 5),
                end_time=t0 + timedelta(minutes=14 + i * 5),
                source="local",
            ),
            source="local",
        )
    visual_recent = storage.get_recent_visual_cards(limit=5)
    assert [c.title for c in visual_recent] == ["Verified Visual Card"]

    # 验证邮件 AI 解读两个请求体均不含本机标题/域名/文档名
    sent_prompts = []
    report = ReportGenerator(storage)

    def capture_call(prompt, max_tokens=200):
        sent_prompts.append(prompt)
        return "简评"

    monkeypatch.setattr(report.ai_generator, "_call_provider", capture_call)
    report.generate_daily_report(t0, use_ai=True)
    assert len(sent_prompts) == 2
    for body in sent_prompts:
        assert "SecretLocalRepo" not in body
        assert "internal.secret.local" not in body


# ==================== 5. 草稿按模式测试、备份无损去重与统一停机 ====================


def test_draft_connection_test_by_recording_mode(env, monkeypatch):
    _, client = env
    seen_require_vision = []

    async def fake_test_connection(self, require_vision=True):
        seen_require_vision.append((require_vision, self.api_key))
        return True, ("vision ok" if require_vision else "text ok")

    monkeypatch.setattr(DayflowBackendProvider, "test_connection", fake_test_connection)
    r_local = client.post(
        "/api/test/connection",
        json={"values": {"api_url": "http://127.0.0.1:11434/v1", "api_model": "qwen2.5:3b", "recording_mode": "local"}},
    )
    assert r_local.status_code == 200 and r_local.json()["mode"] == "local"
    r_vis = client.post(
        "/api/test/connection",
        json={"values": {"api_url": "http://127.0.0.1:11434/v1", "api_model": "qwen2.5-vl", "recording_mode": "visual"}},
    )
    assert r_vis.status_code == 200 and r_vis.json()["mode"] == "visual"
    assert [v for v, _ in seen_require_vision] == [False, True]


def test_backup_bidirectional_opt_in_exclusion_and_lossless_dedup_and_report_remap(tmp_path):
    src = StorageManager(tmp_path / "src.db")
    src.set_setting("local_context_mode", "structured")
    src.set_setting("local_ai_refinement", "1")
    src.set_setting("daily_goal", "6")

    t1 = datetime(2026, 11, 25, 10, 0, 0, 100000)
    t2 = datetime(2026, 11, 25, 10, 0, 0, 900000)
    id1 = src.save_card(
        ActivityCard(
            category="编程",
            title="Dayflow",
            summary="片段 A",
            start_time=t1,
            end_time=t1 + timedelta(minutes=10),
            productivity_score=80.1234,
            source="local",
            segments=[ActivitySegment(t1, t1 + timedelta(minutes=10), "Visual Studio Code", False)],
        ),
        source="local",
    )
    id2 = src.save_card(
        ActivityCard(
            category="编程",
            title="Dayflow",
            summary="片段 B",
            start_time=t2,
            end_time=t2 + timedelta(minutes=10),
            productivity_score=80.1235,
            source="local",
            segments=[ActivitySegment(t2, t2 + timedelta(minutes=10), "Cursor", False)],
        ),
        source="local",
    )
    src.save_report_revision("2026-11-25", f"- 完成开发 [活动 #{id1}]，另见未知 [活动 #9999]", "k1")

    exported = export_backup(src)
    assert "local_context_mode" not in exported["settings"]
    assert "local_ai_refinement" not in exported["settings"]
    assert exported["settings"]["daily_goal"] == "6"
    src.close()

    dst = StorageManager(tmp_path / "dst.db")
    # 预先插入一张占位卡以偏移目标库 ID
    dst.save_card(ActivityCard(category="学习", title="Preexisting", start_time=datetime(2026, 11, 24, 8, 0), end_time=datetime(2026, 11, 24, 9, 0)))

    # 尝试注入授权键也必须被拒绝
    res = import_backup(
        dst,
        Backup.model_validate(exported),
        settings={"daily_goal": "6", "local_context_mode": "structured", "local_ai_refinement": "1"},
    )
    # .100 和 .900 两条微秒不同记录必须全部导入，绝不因 datetime() 截断合并
    assert res == {"imported": 2, "skipped": 0}
    assert read_settings(dst)["local_context_mode"] == "app_only"
    assert read_settings(dst)["local_ai_refinement"] == "0"

    cards = dst.get_cards_for_date(t1)
    assert len(cards) == 2
    assert len(cards[0].segments) == 1 and len(cards[1].segments) == 1
    new_id1 = next(c.id for c in cards if c.summary == "片段 A")
    report_text = dst.get_report_revision("2026-11-25")["content"]
    assert f"[活动 #{new_id1}]" in report_text
    assert "[活动 #9999]" not in report_text
    assert "[活动记录]" in report_text
    dst.close()


def test_system_shutdown_drains_and_closes_storage(env):
    storage, client = env
    r = client.post("/api/system/shutdown")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert storage._pool is None
    # 关闭后拒绝新写入
    r2 = client.post("/api/settings", json={"values": {"daily_goal": "9"}})
    assert r2.status_code == 503
