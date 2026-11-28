"""Isolated acceptance checks for local timing, vision cost and report revisions."""

import asyncio
import base64
from datetime import datetime, timedelta
import json
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import config
from bridge import server
from core import local_recorder
from core.email_service import ReportGenerator
from core.llm_provider import DayflowBackendProvider
from core.types import ActivityCard
from core.window_tracker import WindowInfo
from database.storage import StorageManager


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    storage = StorageManager(tmp_path / "next.db")
    monkeypatch.setattr(server, "_storage", storage)
    monkeypatch.setattr(server, "_recorder", None)
    monkeypatch.setattr(server, "_analysis", None)
    monkeypatch.setattr(config, "CHUNKS_DIR", tmp_path / "chunks")
    monkeypatch.setattr(config, "API_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setattr(config, "API_MODEL", "fixture")
    monkeypatch.setattr(config, "API_KEY", "")
    monkeypatch.setattr(config, "IDLE_PAUSE_ENABLED", False)
    yield storage, TestClient(server.app)
    if server._recorder and server._recorder.is_recording:
        server._recorder.stop_recording()
    storage.close()


class Tracker:
    is_available = True

    def get_active_window(self):
        return WindowInfo("Code.exe", "private-document-9384", 1)

    def get_friendly_app_name(self, window):
        return "Visual Studio Code"


def test_fresh_recording_and_report_work_without_models(desktop, monkeypatch, tmp_path):
    storage, client = desktop
    monkeypatch.setattr(local_recorder, "get_tracker", Tracker)
    monkeypatch.setattr(server, "get_analysis", lambda: pytest.fail("local timing started vision analysis"))
    monkeypatch.setattr(server, "get_provider", lambda: pytest.fail("local report called a model"))
    assert client.get("/api/recording/state").json()["recordingMode"] == "local"
    assert not client.get("/api/recording/state").json()["needsSetup"]
    assert client.post("/api/recording/start").status_code == 200
    for _ in range(40):
        start = datetime.now()
        cards = storage.get_cards_for_date(start)
        if cards:
            break
        time.sleep(.1)
    assert client.post("/api/recording/stop").status_code == 200
    cards = storage.get_cards_for_date(datetime.now())
    assert len(cards) == 1 and cards[0].title == "Visual Studio Code"
    assert cards[0].duration_minutes > 0
    assert "private-document-9384" not in json.dumps(cards[0].to_dict())
    assert not list(tmp_path.rglob("*.mp4"))
    day = datetime.now().date().isoformat()
    report = client.get(f"/api/reports/{day}").json()
    assert report["localSummary"] and report["evidence"][0]["id"] == cards[0].id
    assert not report["canSupplement"]
    assert day in client.get("/api/reports/dates").json()["dates"]
    assert client.post("/api/settings", json={"values": {"recording_mode": "visual"}}).status_code == 200
    assert client.get("/api/recording/state").json()["needsSetup"]
    assert client.post("/api/recording/start").status_code == 412


def test_local_samples_exclude_privacy_gap_and_preserve_edits(desktop, monkeypatch):
    storage, _ = desktop
    monkeypatch.setattr(local_recorder, "get_tracker", Tracker)
    recorder = local_recorder.LocalActivityRecorder(storage)
    recorder.privacy.app_blacklist = {"keepass"}
    start = datetime(2026, 11, 25, 9)
    editor = WindowInfo("Code.exe", "private-document-9384", 1)
    protected = WindowInfo("KeePass.exe", "fixture secret", 2)
    recorder.sample(start, editor)
    recorder.sample(start + timedelta(seconds=1), editor)
    card = storage.get_cards_for_date(start)[0]
    storage.update_card(card.id, title="我修改的标题")
    for seconds in (2, 3, 4, 5):
        recorder.sample(start + timedelta(seconds=seconds), editor)
    recorder.sample(start + timedelta(seconds=6), protected)
    assert recorder.is_privacy_paused
    recorder.sample(start + timedelta(seconds=7), editor)
    recorder.sample(start + timedelta(seconds=8), editor)
    recorder._finish()
    cards = storage.get_cards_for_date(start)
    assert [(card.title, round(card.duration_minutes * 60)) for card in cards] == [
        ("我修改的标题", 5), ("Visual Studio Code", 1),
    ]


def test_visual_budget_keeps_window_transition(tmp_path):
    path = tmp_path / "sample.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 1, (160, 80))
    assert writer.isOpened()
    for index in range(24):
        value = 245 if index == 11 else index * 7
        writer.write(np.full((80, 160, 3), value, np.uint8))
    writer.release()

    provider = DayflowBackendProvider()
    frames = provider._extract_frames_from_video(str(path), max_frames=4, window_records=[{"timestamp": 11}])
    assert len(frames) == 4
    samples = [cv2.imdecode(np.frombuffer(base64.b64decode(frame), dtype=np.uint8), cv2.IMREAD_COLOR) for frame in frames]
    assert any(image.mean() > 230 for image in samples)
    assert all(image.shape[:2] == (80, 160) for image in samples)


def test_connection_test_requires_recognizing_generated_image(monkeypatch):
    from core import llm_provider
    provider = DayflowBackendProvider("http://127.0.0.1:12345/v1", "", "fixture")
    monkeypatch.setattr(llm_provider.secrets, "randbelow", lambda _: 1234)

    async def reply(messages, **kwargs):
        parts = messages[0]["content"]
        encoded = parts[1]["image_url"]["url"].split(",", 1)[1]
        image = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), dtype=np.uint8), cv2.IMREAD_COLOR)
        assert image.shape[:2] == (104, 288)
        assert image.min() < 50
        assert "2234" not in parts[0]["text"]
        assert kwargs["max_tokens"] == 64
        return '{"code":"2234"}'

    async def text_only(*args, **kwargs):
        return "连接成功"

    monkeypatch.setattr(provider, "_chat_completion", text_only)
    assert not asyncio.run(provider.test_connection())[0]
    monkeypatch.setattr(provider, "_chat_completion", reply)
    assert asyncio.run(provider.test_connection())[0]


def test_report_insights_reject_unknown_or_unattributed_claims(monkeypatch):
    provider = DayflowBackendProvider()
    evidence = [{"id": 17, "title": "合成活动", "minutes": 10}]

    async def unsupported(*args, **kwargs):
        return "- 一条观察 [活动 #17]\n- 没有依据的结论"

    monkeypatch.setattr(provider, "_chat_completion", unsupported)
    with pytest.raises(ValueError, match="有效活动依据"):
        asyncio.run(provider.generate_report_insights("本机总结", evidence))

    async def supported(*args, **kwargs):
        assert kwargs["max_tokens"] == 500
        return "- 一条观察 [活动 #17]"

    monkeypatch.setattr(provider, "_chat_completion", supported)
    assert "[活动 #17]" in asyncio.run(provider.generate_report_insights("本机总结", evidence))


def test_report_cache_and_revision_history(desktop, monkeypatch):
    storage, client = desktop
    start = datetime(2026, 11, 24, 23, 50)
    card_id = storage.save_card(ActivityCard(category="学习", title="课程阅读", start_time=start,
                                             end_time=start + timedelta(minutes=20)))
    day = "2026-11-25"
    calls = []

    class Provider:
        async def generate_report_insights(self, summary, evidence):
            calls.append(evidence)
            assert "10.0 分钟" in summary
            return f"- 第 {len(calls)} 版 [活动 #{card_id}]"

    monkeypatch.setattr(server, "get_provider", Provider)
    monkeypatch.setattr(config, "API_BASE_URL", "http://127.0.0.1:12345/v1")
    report = client.get(f"/api/reports/{day}").json()
    assert [row["id"] for row in report["evidence"]] == [card_id]
    assert report["evidence"][0]["minutes"] == 10
    assert report["localSummary"] and not calls
    assert day in client.get("/api/reports/dates").json()["dates"]

    first = client.post(f"/api/reports/{day}").json()
    assert len(calls) == 1 and first["supplement"] and not first["isStale"]
    assert client.post(f"/api/reports/{day}").json()["supplement"] == first["supplement"]
    assert len(calls) == 1
    storage.update_card(card_id, title="更正后的阅读活动")
    assert client.get(f"/api/reports/{day}").json()["isStale"]
    second = client.post(f"/api/reports/{day}").json()
    assert len(calls) == 2 and second["hasPrevious"] and not second["isStale"]
    restored = client.post(f"/api/reports/{day}/restore").json()
    assert restored["supplement"] == first["supplement"]
    assert restored["isStale"] and len(calls) == 2


def test_scheduled_email_content_can_stay_local(desktop, monkeypatch):
    storage, _ = desktop
    day = datetime(2026, 11, 24, 11)
    storage.save_card(ActivityCard(category="学习", title="阅读", start_time=day,
                                   end_time=day + timedelta(minutes=10)))
    report = ReportGenerator(storage)
    calls = []
    monkeypatch.setattr(report.ai_generator, "generate_comment", lambda *_: calls.append("comment") or "点评")
    monkeypatch.setattr(report.ai_generator, "generate_deep_analysis", lambda *_: calls.append("analysis") or "解读")
    assert "<!DOCTYPE html>" in report.generate_daily_report(day)
    assert not calls
    report.generate_daily_report(day, use_ai=True)
    assert calls == ["comment", "analysis"]
