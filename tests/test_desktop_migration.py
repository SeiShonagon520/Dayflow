from datetime import datetime
from hashlib import sha256

import httpx
import pytest
from fastapi.testclient import TestClient

import config
from bridge import server
from core import desktop_update
from database.storage import StorageManager


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    root = tmp_path / "Dayflow"
    root.mkdir()
    monkeypatch.setattr(config, "APP_DATA_DIR", root)
    monkeypatch.setattr(config, "CHUNKS_DIR", root / "chunks")
    monkeypatch.setattr(config, "DATABASE_PATH", root / "dayflow.db")
    storage = StorageManager()
    monkeypatch.setattr(server, "_storage", storage)
    monkeypatch.setattr(server, "_recorder", None)
    monkeypatch.setattr(server, "_analysis", None)
    monkeypatch.setattr(server, "_provider", None)
    for name in ("API_BASE_URL", "API_KEY", "API_MODEL", "CUSTOM_CHUNKS_DIR",
                 "CHUNKS_MAX_SIZE_GB", "IDLE_PAUSE_ENABLED", "IDLE_PAUSE_TIMEOUT_SECONDS"):
        monkeypatch.setattr(config, name, getattr(config, name))
    yield TestClient(server.app), storage
    storage.close()


def test_existing_database_settings_are_loaded_and_masked(desktop, tmp_path):
    client, storage = desktop
    output = tmp_path / "custom-slices"
    storage.set_setting("custom_chunks_dir", str(output))
    storage.set_setting("api_model", "legacy-model")
    storage.set_setting("email_auth", "smtp-test-credential")
    storage.set_setting("email_enabled", "true")
    storage.set_setting("email_sender", "from@example.com")
    storage.set_setting("email_receiver", "to@example.com")
    storage.set_setting("idle_pause_timeout_min", "18")
    storage.set_setting("record_output_idx", "-1")
    try:
        server._startup()
        assert config.CHUNKS_DIR == output and output.is_dir()
        assert config.API_MODEL == "legacy-model"
        assert config.IDLE_PAUSE_TIMEOUT_SECONDS == 1080
        settings = client.get("/api/settings/all").json()
        assert settings["record_output_idx"] == "-1"
        assert settings["email_auth_code"] == "********"
        assert settings["email_enabled"] == "1"
        assert client.post("/api/settings", json={"values": {
            "email_auth_code": "********", "email_send_times": "7:30,23:05",
        }}).status_code == 200
        assert storage.get_setting("email_auth") == "smtp-test-credential"
        assert storage.get_setting("email_send_times") == "07:30,23:05"
    finally:
        import logging
        logging.shutdown()


def test_desktop_api_requires_session_and_restricts_web_origins(desktop, monkeypatch):
    client, _ = desktop
    monkeypatch.setenv("DAYFLOW_BRIDGE_TOKEN", "test-session")
    assert client.get("/api/backup").status_code == 401
    headers = {"X-Dayflow-Session": "test-session", "Origin": "http://tauri.localhost"}
    response = client.get("/api/backup", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == headers["Origin"]
    assert client.get("/api/backup", headers={**headers, "Origin": "https://example.org"}).status_code == 403


def test_qt_backup_merges_activities_and_preserves_credentials(desktop):
    client, storage = desktop
    storage.set_setting("api_key", "test-local-key")
    storage.set_setting("email_auth", "test-local-mail")
    legacy = {
        "version": "1.2.0",
        "cards": [{
            "id": 55, "category": "学习", "title": "<script>alert(1)</script>",
            "summary": "旧版记录", "start_time": "2025-12-20 09:00:00",
            "end_time": "2025-12-20 10:00:00",
            "app_sites_json": "[]", "distractions_json": "[]",
        }],
        "settings": {"api_key": "an-import-value", "email_auth": "another-import-value"},
        "daily_reports": {"2025-12-20": "旧日报"},
    }
    assert client.post("/api/backup", json=legacy).json() == {"imported": 1, "skipped": 0}
    assert client.post("/api/backup", json=legacy).json() == {"imported": 0, "skipped": 1}
    assert storage.get_setting("api_key") == "test-local-key"
    legacy["settings"]["daily_goal"] = "9"
    assert client.post("/api/backup?restore_settings=true", json=legacy).status_code == 200
    assert storage.get_setting("daily_goal") == "9" and storage.get_setting("email_auth") == "test-local-mail"
    data = client.get("/api/backup").json()
    assert len(data["cards"]) == 1 and data["daily_reports"]["2025-12-20"] == "旧日报"
    assert "api_key" not in data["settings"] and "email_auth" not in data["settings"]
    html = client.get("/api/export/dashboard?start=2025-12-20&end=2025-12-20").json()["content"]
    assert "旧版记录" in html or "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_email_respects_custom_minute_and_deduplicates(desktop, monkeypatch):
    from bridge.mail import check_email_schedule
    from core.email_service import EmailService, ReportGenerator

    client, storage = desktop
    for key, value in {"email_enabled": "true", "email_sender": "from@example.com",
                       "email_receiver": "to@example.com", "email_auth": "mail-test",
                       "email_send_times": "08:45"}.items():
        storage.set_setting(key, value)
    sends = []
    monkeypatch.setattr(ReportGenerator, "generate_daily_report", lambda *_: "<p>测试日报</p>")
    monkeypatch.setattr(EmailService, "send_report", lambda _, title, html: (sends.append((title, html)) or True, ""))
    check_email_schedule(storage, datetime(2026, 1, 1, 8, 44))
    assert sends == []
    check_email_schedule(storage, datetime(2026, 1, 1, 8, 45))
    check_email_schedule(storage, datetime(2026, 1, 1, 8, 46))
    assert len(sends) == 1
    assert client.get("/api/email/status").json()["last"]["success"] == 1
    assert client.post("/api/email/test").status_code == 200 and len(sends) == 2


def test_staging_accepts_official_nsis_and_verifies_digest(desktop, monkeypatch):
    payload = b"test-installer"
    digest = sha256(payload).hexdigest()
    version = "99.0.0"
    tag = "v" + version
    url = f"https://github.com/{config.GITHUB_REPO}/releases/download/{tag}/Dayflow_{version}_x64-setup.exe"
    release = {"tag_name": tag, "assets": [
        {"name": "portable.zip", "browser_download_url": "https://example.com/portable.zip"},
        {"name": f"Dayflow_{version}_x64-setup.exe", "browser_download_url": url,
         "size": len(payload), "digest": f"sha256:{digest}"},
    ]}
    client = httpx.Client
    served = payload

    def respond(request):
        if request.url.host == "api.github.com":
            return httpx.Response(200, json=release)
        assert str(request.url) == url
        return httpx.Response(200, content=served)

    monkeypatch.setattr(desktop_update.httpx, "Client",
                        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))
    assert desktop_update.check_update().download_url == url
    assert desktop_update.stage_update() == digest
    staged = config.APP_DATA_DIR / "updates" / "setup.exe"
    assert staged.read_bytes() == payload
    served = b"not-installer!"
    with pytest.raises(ValueError, match="校验失败|大小"):
        desktop_update.stage_update()
    assert staged.read_bytes() == payload
    assert not staged.with_suffix(".part").exists()


def test_clear_custom_directory_only_removes_dayflow_slices(desktop):
    client, storage = desktop
    config.CHUNKS_DIR.mkdir()
    keep = config.CHUNKS_DIR / "personal.mp4"
    keep.touch()
    generated = config.CHUNKS_DIR / "chunk_20261124_120000.mp4"
    generated.touch()
    pending = config.CHUNKS_DIR / "chunk_20261124_121000.mp4"
    pending.touch()
    with storage._get_connection() as conn, conn:
        conn.execute(
            "INSERT INTO chunks(file_path,start_time,end_time,duration_seconds,status) "
            "VALUES(?, '2026-11-24T12:10:00', '2026-11-24T12:20:00', 600, 'pending')",
            (str(pending),),
        )
    assert client.get("/api/storage/info").json()["removableCount"] == 1
    assert client.post("/api/storage/clear-chunks").json() == {"ok": True, "removed": 1}
    assert keep.is_file() and pending.is_file() and not generated.exists()


def test_minimized_desktop_starts_recording_after_bridge_startup(desktop, monkeypatch):
    from threading import Event

    started = Event()
    monkeypatch.setenv("DAYFLOW_BRIDGE_TOKEN", "test-session")
    monkeypatch.setenv("DAYFLOW_START_MINIMIZED", "1")
    monkeypatch.setattr(server, "start_recording", started.set)
    monkeypatch.setattr(server, "mail_loop", lambda *_: None)
    monkeypatch.setattr(server, "_startup", lambda: None)
    monkeypatch.setattr(server, "_shutdown", lambda: None)
    with TestClient(server.app) as client:
        assert started.wait(timeout=3)
        assert client.get("/api/health", headers={"X-Dayflow-Session": "test-session"}).status_code == 200


def test_timeline_shows_both_legacy_timestamp_formats_in_order(desktop):
    client, storage = desktop
    with storage._get_connection() as conn, conn:
        conn.executemany(
            "INSERT INTO timeline_cards(category,title,start_time,end_time) VALUES('work',?,?,?)",
            [
                ("space", "2025-12-20 11:00:00", "2025-12-20 12:00:00"),
                ("iso", "2025-12-20T08:00:00", "2025-12-20T09:00:00"),
                ("following day", "2025-12-21 00:00:00", "2025-12-21 01:00:00"),
            ],
        )
    payload = client.get("/api/cards/2025-12-20").json()
    assert [card["title"] for card in payload["cards"]] == ["iso", "space"]
    assert client.get("/api/reports/2025-12-20").json()["hasActivity"] is True
    assert client.get("/api/reports/2025-12-22").json()["hasActivity"] is False
    csv = client.get("/api/export/csv?start=2025-12-20&end=2025-12-21").json()
    assert "2025-12-20,08:00" in csv and "following day" in csv
    card = payload["cards"][0]
    assert client.delete(f"/api/cards/{card['id']}").status_code == 200
    for _ in range(2):
        assert client.post("/api/cards/restore", json={"card": card}).status_code == 200
    assert [entry["id"] for entry in client.get("/api/cards/2025-12-20").json()["cards"]].count(card["id"]) == 1


def test_connection_check_uses_draft_without_saving_or_forwarding_old_key(desktop, monkeypatch):
    from core import llm_provider

    client, storage = desktop
    storage.set_setting("api_url", "https://original.invalid/v1")
    storage.set_setting("api_key", "isolated-test-credential")
    storage.set_setting("api_model", "saved-model")
    requests = []

    class Provider:
        def __init__(self, url=None, key=None, model=None):
            requests.append((url, key, model))

        async def test_connection(self):
            return True, "connected"

    monkeypatch.setattr(llm_provider, "DayflowBackendProvider", Provider)
    response = client.post("/api/test/connection", json={"values": {
        "api_url": "https://new.invalid/v1", "api_model": "draft-model", "api_key": "********",
    }})
    assert response.json()["ok"]
    assert requests[-1] == ("https://new.invalid/v1", "", "draft-model")
    assert storage.get_setting("api_model") == "saved-model"
    assert storage.get_setting("daily_goal", "8") == "8"


def test_autostart_reuses_legacy_registry_name_and_targets_tauri(tmp_path, monkeypatch):
    import winreg
    from contextlib import nullcontext
    from core import autostart

    old = tmp_path / "old" / "Dayflow.exe"
    host = tmp_path / "new" / "dayflow.exe"
    host.parent.mkdir()
    host.touch()
    monkeypatch.setenv("DAYFLOW_HOST_EXE", str(host))
    entries = {"Dayflow": f'"{old}" --minimized'}
    monkeypatch.setattr(winreg, "OpenKey", lambda *_: nullcontext("registry"))
    monkeypatch.setattr(winreg, "CreateKeyEx", lambda *_: nullcontext("registry"))
    monkeypatch.setattr(winreg, "QueryValueEx", lambda _, name: (entries[name], winreg.REG_SZ))
    monkeypatch.setattr(winreg, "SetValueEx", lambda _, name, _reserved, _type, data: entries.__setitem__(name, data))
    assert autostart.check_path_changed() == (True, str(old), str(host))
    assert autostart.update_autostart_path()[0]
    assert entries["Dayflow"] == f'"{host}" --minimized'


def test_email_report_jinja_rendering():
    """Test that ReportGenerator successfully renders the Jinja2 email template."""
    from core.email_service import ReportGenerator
    now = datetime(2026, 9, 3, 16, 0)
    stats = [
        ("编程", 120),
        ("工作", 60),
        ("休息", 30)
    ]
    total_minutes = 210
    score = 88
    deep_analysis = {
        "focus": {"has_data": True, "deep_count": 2, "max_session": {"duration": 90, "category": "编程", "time": "10:00"}},
        "rhythm": {"has_data": False},
        "switching": {"has_data": False},
        "categories": {"has_data": False},
        "day_type": {"type": "高效工作日"}
    }
    ai_comment = "今日表现极其出色，持续专注深度工作。"

    class DummyStorage:
        pass

    gen = ReportGenerator(DummyStorage())
    html = gen._build_html(
        date=now,
        stats=stats,
        total_minutes=total_minutes,
        score=score,
        deep_analysis=deep_analysis,
        ai_comment=ai_comment,
        expert_analysis="## 专业建议\n保持早晨的高专注状态。"
    )

    assert "<!DOCTYPE html>" in html
    assert "2026年09月03日" in html
    assert "高效工作日" in html
    assert "今日洞察" in html
    assert "今日表现极其出色" in html
    assert "专业分析报告" in html or "专业建议" in html
