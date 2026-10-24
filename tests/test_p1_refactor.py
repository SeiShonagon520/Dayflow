"""
Unit tests for P1 refactoring:
- Modularized UI components imports and initialization
- SettingsPanel extraction
- Email template Jinja2 rendering
"""
from datetime import datetime
import pytest

from ui.components.title_bar import TitleBarButton, CustomTitleBar
from ui.components.sidebar_button import SidebarButton
from ui.components.recording_indicator import RecordingIndicator
from ui.components.collapsible_section import CollapsibleSection
from ui.daily_report_dialog import DailyReportDialog
from ui.settings_view import SettingsPanel
from ui.main_window import (
    MainWindow,
    SettingsPanel as MainSettingsPanel,
    CustomTitleBar as MainCustomTitleBar,
)
from core.email_service import ReportGenerator


def test_ui_components_classes():
    """Test that all modular UI components can be instantiated or referenced."""
    assert TitleBarButton is not None
    assert CustomTitleBar is not None
    assert SidebarButton is not None
    assert RecordingIndicator is not None
    assert CollapsibleSection is not None
    assert DailyReportDialog is not None
    assert SettingsPanel is not None


def test_main_window_backwards_compatibility_exports():
    """Test that ui.main_window re-exports extracted components for backwards compatibility."""
    assert MainSettingsPanel is SettingsPanel
    assert MainCustomTitleBar is CustomTitleBar


def test_email_report_jinja_rendering(tmp_path):
    """Test that ReportGenerator successfully renders the Jinja2 email template."""
    # We test _build_html directly
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


def test_theme_tokens_and_markdown_css():
    """Test upgraded design tokens and markdown CSS generation."""
    from ui.themes import (
        DARK_THEME, LIGHT_THEME, RADIUS, TYPE_SCALE, SPACE,
        get_markdown_stylesheet, with_alpha,
    )
    
    # 颜色字面量会随设计系统迭代变化，这里断言结构性质而非具体色值：
    # 每个 token 都是合法 hex，且浅/深两套主题共用同一套 token 名称。
    for theme in (DARK_THEME, LIGHT_THEME):
        for name in ("bg_primary", "bg_secondary", "bg_tertiary", "bg_sidebar",
                     "border", "text_primary", "text_secondary", "text_muted",
                     "accent", "accent_hover", "accent_focus",
                     "success", "warning", "error"):
            value = getattr(theme, name)
            assert value, f"{theme.name}.{name} 不能为空"
            assert value.startswith("#") or value.startswith("rgba("), \
                f"{theme.name}.{name} 格式非法: {value}"
    
    # 焦点环必须存在且与强调色同族 —— Apple 规范要求 2px Action Blue
    assert DARK_THEME.accent_focus
    assert LIGHT_THEME.accent_focus
    
    css = _global_css(LIGHT_THEME)
    assert ":focus" in css
    # 焦点环的 2px 实线必须真的出现在样式表里
    assert f"border: 2px solid {LIGHT_THEME.accent_focus}" in css
    assert f"border: 2px solid {DARK_THEME.accent_focus}" in _global_css(DARK_THEME)
    
    # Apple 圆角阶梯
    assert RADIUS["sm"] == 8
    assert RADIUS["pill"] == 9999
    
    # Apple 排版阶梯：标题带负字距
    assert TYPE_SCALE["title"][2] < 0
    assert TYPE_SCALE["body"][2] == 0
    
    # 间距基准 8px
    assert SPACE["xs"] == 8 and SPACE["lg"] == 24
    
    # with_alpha 修复 Qt 的 AARRGGBB 陷阱
    assert with_alpha("#0A6ED1", 0.12) == "rgba(10, 110, 209, 0.12)"
    
    dark_md = get_markdown_stylesheet(DARK_THEME)
    light_md = get_markdown_stylesheet(LIGHT_THEME)
    
    for css in (dark_md, light_md):
        assert "blockquote" in css
        assert "table" in css
        assert "code" in css
        assert "font-family" in css


def _global_css(theme):
    """针对指定主题生成全局样式表（不改动全局单例状态）"""
    from ui.themes import ThemeManager
    original = ThemeManager()._current_theme
    try:
        ThemeManager()._current_theme = theme
        return ThemeManager().get_global_stylesheet()
    finally:
        ThemeManager()._current_theme = original


def test_recording_indicator_pill():
    """Test RecordingIndicator pill state switches and elapsed format."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    indicator = RecordingIndicator()
    try:
        assert "未录制" in indicator.status_label.text()
        
        indicator.set_recording(True, paused=False)
        assert "REC" in indicator.status_label.text()
        
        indicator.set_recording(True, paused=True)
        assert "PAUSED" in indicator.status_label.text()
        
        indicator.set_recording(False)
        assert "未录制" in indicator.status_label.text()
    finally:
        indicator._blink_timer.stop()
        indicator._duration_timer.stop()
        indicator.deleteLater()


def test_timeline_spine_and_gap_and_filter():
    """Test TimelineView spine rendering, gap widget insertion, and category filtering."""
    from datetime import timedelta
    from PySide6.QtWidgets import QApplication
    from core.types import ActivityCard
    from ui.timeline_view import TimelineView, TimelineCardItemWidget, TimelineGapWidget
    
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        
    t0 = datetime(2026, 9, 3, 9, 0)
    card1 = ActivityCard(id=1, start_time=t0, end_time=t0 + timedelta(minutes=45), category="编程", title="编码开发")
    # 45 min gap
    t1 = t0 + timedelta(minutes=90)
    card2 = ActivityCard(id=2, start_time=t1, end_time=t1 + timedelta(minutes=75), category="工作", title="深度会议")
    
    view = TimelineView()
    try:
        view.set_cards([card1, card2])
        
        widgets = [view.cards_layout.itemAt(i).widget() for i in range(view.cards_layout.count()) if view.cards_layout.itemAt(i).widget()]
        widget_types = [type(w).__name__ for w in widgets]
        
        assert "TimelineCardItemWidget" in widget_types
        assert "TimelineGapWidget" in widget_types
        
        # Test category filter
        view._on_category_selected("编程")
        filtered = view._get_filtered_cards()
        assert len(filtered) == 1
        assert filtered[0].category == "编程"
        
        view._on_category_selected("")
        assert len(view._get_filtered_cards()) == 2
    finally:
        view.deleteLater()


def test_contribution_grid_and_stats_panel():
    """Test ContributionGridWidget rendering and StatsPanel date_clicked signal."""
    from PySide6.QtWidgets import QApplication
    from database.storage import StorageManager
    from ui.stats_view import ContributionGridWidget, StatsPanel
    from ui.main_window import apply_dwm_window_attributes
    
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        
    grid = ContributionGridWidget()
    try:
        grid.set_data({
            "2026-09-03": {"hours": 6.5, "score": 85.0, "activities": 10},
            "2026-09-02": {"hours": 1.5, "score": 60.0, "activities": 3},
            "2026-09-01": {"hours": 0.0, "score": 0.0, "activities": 0},
        })
        assert len(grid._cells) == 35  # 5 weeks x 7 days
    finally:
        grid.deleteLater()
        
    storage = StorageManager()
    panel = StatsPanel(storage)
    try:
        assert panel.contribution_grid is not None
        
        # Test date_clicked signal
        clicked_dates = []
        panel.date_clicked.connect(lambda d: clicked_dates.append(d))
        target_date = datetime(2026, 9, 3)
        panel.contribution_grid.date_clicked.emit(target_date)
        assert len(clicked_dates) == 1
        assert clicked_dates[0] == target_date
    finally:
        panel.deleteLater()
        
    # Test DWM function executes safely
    apply_dwm_window_attributes(0, is_dark=True)
