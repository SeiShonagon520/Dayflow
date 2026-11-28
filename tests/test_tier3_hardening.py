"""Regression tests for Tier 3 structural hardening."""
from datetime import datetime, timedelta
import logging
import os
import time

from fastapi.testclient import TestClient

from core.dashboard_exporter import DashboardExporter
from core.email_service import AICommentGenerator, ReportGenerator
from core.log_manager import LogManager
from core.types import ActivityCard
from database.storage import StorageManager


def test_email_ai_generator_supports_ollama_and_clean_time_formatting(tmp_path, monkeypatch):
    storage = StorageManager(db_path=tmp_path / "mail.db")
    try:
        storage.set_setting("api_url", "http://localhost:11434")
        storage.set_setting("api_key", "")
        storage.set_setting("api_model", "qwen2.5-vl:7b")

        captured = {}

        async def fake_completion(self, messages, temperature=0.7, max_tokens=200):
            captured["url"] = self.api_base_url
            captured["is_ollama"] = self.is_ollama
            captured["prompt"] = messages[0]["content"]
            return "节奏很稳。"

        from core.llm_provider import DayflowBackendProvider
        monkeypatch.setattr(DayflowBackendProvider, "_chat_completion", fake_completion)

        gen = AICommentGenerator(storage)
        stats = {
            "date": "2026年11月24日",
            "recorded_minutes": 90.5,
            "score": 82,
            "categories": [("编程", 90)],
        }
        deep = {
            "focus": {"has_data": False},
            "rhythm": {"has_data": False},
            "switching": {"has_data": False},
            "categories": {"has_data": False},
            "day_type": {"type": "常规日", "indicators": "节奏正常"},
        }
        result = gen.generate_comment(stats, deep)
        assert result == "节奏很稳。"
        assert captured["is_ollama"] is True
        assert captured["url"] == "http://localhost:11434/v1"
        assert "1小时30分钟" in captured["prompt"]
        assert "1.0小时" not in captured["prompt"]
    finally:
        storage.close()


def test_email_html_escapes_dynamic_fields_and_highlights_midnight_peak():
    gen = ReportGenerator(storage=None)
    deep_analysis = {
        "focus": {
            "has_data": True,
            "total_sessions": 2,
            "fragment_count": 0,
            "fragment_percent": 0,
            "deep_count": 1,
            "deep_total_mins": 70,
            "avg_duration": 45,
            "max_session": {"category": "<script>alert(1)</script>", "duration": 70, "time": "02:00"},
        },
        "rhythm": {
            "has_data": True,
            "peak_hour": 2,
            "peak_score": 92,
            "low_hour": 14,
            "low_score": 60,
            "periods": {
                "凌晨(0-6)": {"avg_score": 92, "total_mins": 70, "session_count": 1},
                "下午(12-18)": {"avg_score": 60, "total_mins": 20, "session_count": 1},
            },
        },
        "switching": {
            "has_data": True,
            "total_switches": 2,
            "common_patterns": [("<img src=x onerror=alert(1)>→工作", 2)],
        },
        "categories": {
            "has_data": True,
            "best": "<b>编程</b>",
            "worst": "<i>休息</i>",
            "stats": {
                "<b>编程</b>": {"avg_score": 90, "total_mins": 70, "session_count": 1},
                "<i>休息</i>": {"avg_score": 40, "total_mins": 20, "session_count": 1},
            },
        },
        "day_type": {"type": "深度工作日"},
    }
    html = gen._build_html(
        date=datetime(2026, 11, 24, 2, 0),
        stats=[("编程", 70), ("休息", 20)],
        total_minutes=90,
        score=82,
        deep_analysis=deep_analysis,
        ai_comment="点评",
        expert_analysis="## 建议\n- 保持 **专注** <script>bad()</script>",
    )
    assert "<title>Dayflow 深度分析报告 - 2026年11月24日</title>" in html
    assert "凌晨 ⭐" in html
    assert "<script>alert(1)</script>" not in html
    assert "<script>bad()</script>" not in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;script&gt;bad()&lt;/script&gt;" in html
    assert "<strong>专注</strong>" in html


def test_storage_update_card_returns_false_for_missing_id_and_bridge_returns_404(tmp_path):
    storage = StorageManager(db_path=tmp_path / "cards.db")
    try:
        assert storage.update_card(999999, title="不存在") is False
        storage.set_setting("k1", "v1")
        assert storage.get_setting("k1") == "v1"
    finally:
        storage.close()

    from bridge.server import app
    client = TestClient(app)
    resp = client.patch("/api/cards/999999", json={"title": "不存在"})
    assert resp.status_code == 404


def test_log_manager_closes_previous_handlers_and_cleans_expired_logs(tmp_path):
    old_log = tmp_path / "dayflow.log.1"
    old_log.write_text("old", encoding="utf-8")
    expired = time.time() - 40 * 86400
    os.utime(old_log, (expired, expired))

    first = LogManager(log_dir=tmp_path, retention_days=30)
    first.setup()
    first_handler = first._file_handler
    assert first_handler is not None

    second = LogManager(log_dir=tmp_path, retention_days=30)
    second.setup()
    # Prior file handler must be closed on replacement to avoid Windows handle leaks.
    assert first_handler.stream is None or first_handler.stream.closed

    removed = second.cleanup_old_logs()
    assert removed == 1
    assert not old_log.exists()
    second.close()
    assert all(h is not second._file_handler for h in logging.getLogger().handlers)


def test_dashboard_html_is_offline_self_contained_and_consistent(tmp_path):
    storage = StorageManager(db_path=tmp_path / "dash.db")
    try:
        day = datetime(2026, 11, 24, 9, 0)
        storage.save_card(ActivityCard(
            category="编程",
            title="核心开发",
            summary="离线仪表盘",
            start_time=day,
            end_time=day + timedelta(minutes=75),
            productivity_score=85,
        ))
        html = DashboardExporter(storage).render(day.date(), day.date())
        assert "cdn.jsdelivr.net" not in html
        assert "echarts" not in html.lower()
        assert "AI 洞察" not in html
        assert "单段 ≥ 60 分钟" in html
        assert "85 分" in html
        assert "event.target" not in html
        assert 'data-filter="all"' in html
    finally:
        storage.close()
