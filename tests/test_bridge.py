"""
Dayflow Bridge 测试

覆盖新增/改动的端点。这些接口是前端唯一的入口，
出问题时用户看到的是「无法连接后台服务」，定位成本很高。
"""
import pytest
from datetime import datetime, timedelta


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from bridge.server import app
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_settings_masks_api_key(client):
    """
    API Key 不能回传明文。

    后端没有鉴权、只靠 CORS 限制来源，一旦被别处读到就是明文密钥。
    """
    r = client.get("/api/settings/all")
    assert r.status_code == 200
    body = r.json()
    assert "api_key" in body
    assert body["api_key"] in ("", "********")
    assert "api_key_configured" in body


def test_cards_reject_bad_date(client):
    r = client.get("/api/cards/not-a-date")
    assert r.status_code == 400
    # 错误信息要说清正确格式，而不是抛栈
    assert "YYYY-MM-DD" in r.json()["detail"]


def test_cards_today_shape(client):
    """卡片字段名是 camelCase，前端直接用它们渲染"""
    r = client.get(f"/api/cards/{datetime.now():%Y-%m-%d}")
    assert r.status_code == 200
    cards = r.json()["cards"]
    for c in cards[:1]:
        for k in ("id", "category", "title", "summary", "startTime",
                  "endTime", "durationMinutes", "productivityScore", "appSites"):
            assert k in c, f"卡片缺少字段 {k}"


def test_stats_7_and_30_days(client):
    """两个时间窗口都要能出，且 30 天的区间长度正确"""
    r7 = client.get("/api/stats?days=7")
    assert r7.status_code == 200
    s7 = r7.json()
    assert s7["days"] == 7
    assert len(s7["trend"]) == 7
    assert len(s7["calendar"]) == 126        # 18 周
    assert len(s7["hourly"]) == 24

    r30 = client.get("/api/stats?days=30")
    assert r30.status_code == 200
    s30 = r30.json()
    assert s30["days"] == 30
    start = datetime.strptime(s30["rangeStart"], "%Y-%m-%d")
    end = datetime.strptime(s30["rangeEnd"], "%Y-%m-%d")
    assert (end - start).days == 29


def test_stats_rejects_bad_window(client):
    """非法窗口回落到 7 天，而不是报错或算 40 天"""
    r = client.get("/api/stats?days=999")
    assert r.status_code == 200
    assert r.json()["days"] == 7


def test_recording_state(client):
    r = client.get("/api/recording/state")
    assert r.status_code == 200
    body = r.json()
    for k in ("isRecording", "isPaused", "isIdlePaused"):
        assert k in body
        assert isinstance(body[k], bool)


def test_analysis_progress(client):
    r = client.get("/api/analysis/progress")
    assert r.status_code == 200
    assert isinstance(r.json()["pending"], int)


def test_autostart_reports_state(client):
    r = client.get("/api/autostart")
    assert r.status_code == 200
    assert isinstance(r.json()["enabled"], bool)


def test_storage_info(client):
    r = client.get("/api/storage/info")
    assert r.status_code == 200
    body = r.json()
    for k in ("chunksDir", "usedMb", "limitGb", "percent"):
        assert k in body


def test_reports_list_and_fetch(client):
    r = client.get("/api/reports/dates")
    assert r.status_code == 200
    dates = r.json()["dates"]
    assert isinstance(dates, list)

    r2 = client.get("/api/reports/2026-09-28")
    assert r2.status_code == 200
    assert "content" in r2.json()


def test_report_deletion_404(client):
    r = client.delete("/api/cards/99999999")
    assert r.status_code == 404


# ── 统计聚合逻辑（纯函数，不碰 HTTP）─────────────────────────


def test_stats_service_normalizes_app_names():
    """应用名归一化：.exe 后缀和大小写差异不该在榜单里裂成多项"""
    from bridge.stats_service import normalize_app_name
    assert normalize_app_name("chrome.exe") == "chrome"
    assert normalize_app_name("Chrome") == "Chrome"
    assert normalize_app_name("") == "未命名"
    assert normalize_app_name("Code.exe") == "Code"


def test_stats_service_app_minutes_matches_card_total():
    """
    应用时长合计应与卡片总时长自洽。

    app_sites 里的 duration_seconds 是模型给的估计值，常与卡片总时长
    对不上。归一化做错的话，榜单总量会和其他图表互相矛盾。
    """
    from bridge.stats_service import _app_minutes
    from core.types import ActivityCard, AppSite

    card = ActivityCard(
        category="编程", title="t", summary="",
        start_time=datetime.now(), end_time=datetime.now() + timedelta(minutes=60),
        # 模型说这些应用共 30 分钟，但卡片本身是 60 分钟
        app_sites=[AppSite(name="A", duration_seconds=600),
                   AppSite(name="B", duration_seconds=1200)],
        distractions=[], productivity_score=80,
    )
    out = _app_minutes(card)
    assert abs(sum(out.values()) - 60.0) < 0.01

    # 全是 0 时要平均分配，不能让这些应用从榜单上消失
    card2 = ActivityCard(
        category="编程", title="t", summary="",
        start_time=datetime.now(), end_time=datetime.now() + timedelta(minutes=30),
        app_sites=[AppSite(name="X", duration_seconds=0),
                   AppSite(name="Y", duration_seconds=0)],
        distractions=[], productivity_score=80,
    )
    out2 = _app_minutes(card2)
    assert abs(sum(out2.values()) - 30.0) < 0.01
    assert abs(out2["X"] - 15.0) < 0.01


def test_stats_service_empty_database():
    """空库不能崩，要返回结构完整的零值"""
    from bridge.stats_service import collect_stats

    class FakeStorage:
        def get_cards_for_date(self, d):
            return []

    s = collect_stats(FakeStorage(), days=7)
    assert s["metrics"]["activityCount"] == 0
    assert s["categories"] == []
    assert len(s["calendar"]) == 126
    assert len(s["hourly"]) == 24
