"""
Dayflow Windows - 交互状态测试

关注点是「状态是否真的存在、是否真的会触发」，
而不是控件长什么样 —— 视觉由渲染验证，这里验证行为契约。
"""
import pytest

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ── 空状态：必须可点，且点出不同动作 ──────────────────────────


def test_empty_state_has_action_button(app):
    """空状态不能只是一段文字，必须给出下一步"""
    from ui.timeline_view import EmptyStateWidget
    w = EmptyStateWidget()
    assert w.action_btn is not None
    assert w.action_btn.text() != "", "空状态没有可点的出口"
    assert w.action_btn.isVisibleTo(w)


def test_empty_state_variants_emit_distinct_actions(app):
    """
    三种空状态对应三种不同的下一步。

    「还没录」给开始录制，「分析中」给刷新，「搜索无结果」给清除搜索 ——
    如果都退化成同一个按钮，用户在错误的地方点了错误的按钮。
    """
    from ui.timeline_view import EmptyStateWidget

    cases = [
        (lambda w: w.set_has_pending_analysis(False), "start"),
        (lambda w: w.set_has_pending_analysis(True), "refresh"),
        (lambda w: w.set_search_mode(True), "clear_search"),
    ]
    for setup, expected in cases:
        w = EmptyStateWidget()
        setup(w)
        got = []
        w.action_triggered.connect(got.append)
        w.action_btn.click()
        app.processEvents()
        assert got == [expected], f"期望动作 {expected}，实际 {got}"


def test_empty_state_variants_have_distinct_copy(app):
    """不同空状态要有不同文案，否则用户分不清发生了什么"""
    from ui.timeline_view import EmptyStateWidget

    texts = set()
    for setup in (lambda w: w.set_has_pending_analysis(False),
                  lambda w: w.set_has_pending_analysis(True),
                  lambda w: w.set_search_mode(True)):
        w = EmptyStateWidget()
        setup(w)
        texts.add((w.title_label.text(), w.desc_label.text()))
    assert len(texts) == 3, "三种空状态的文案没有区分开"


# ── 撤销：删除必须可恢复 ──────────────────────────────────────


def test_card_delete_is_undoable(app):
    """
    删除活动记录必须可撤销。

    这条记录能原样恢复，用确认框拦一次只是让用户多点一下，
    还会训练出「无脑点确定」。
    """
    from PySide6.QtWidgets import QMessageBox
    import ui.timeline_view as tv

    calls = []
    original = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: calls.append(a) or QMessageBox.No)
    try:
        card = _make_card(1)
        widget = tv.ActivityCardWidget(card)
        got = []
        widget.delete_requested.connect(got.append)
        widget._confirm_delete()
        assert got == [1], "删除没有发出信号"
        assert not calls, "删除不该再弹确认框"
    finally:
        QMessageBox.question = original


def test_undo_restores_the_card(app):
    """撤销后卡片回到列表里，并发出恢复信号"""
    from PySide6.QtCore import QEventLoop, QTimer
    from ui.timeline_view import TimelineView

    view = TimelineView()
    view.resize(600, 400)
    view.show()
    cards = [_make_card(1), _make_card(2), _make_card(3)]
    view.set_cards(cards)
    app.processEvents()
    assert len(view._cards) == 3

    restored = []
    view.card_restored.connect(restored.append)

    view._handle_card_deleted(2)
    assert [c.id for c in view._cards] == [1, 3]

    # 折叠动画结束后（QTimer 160ms）才会重建列表并弹出撤销条，
    # 这里必须真的把事件循环转起来，否则测的是还没发生的将来
    loop = QEventLoop()
    QTimer.singleShot(260, loop.quit)
    loop.exec()
    app.processEvents()

    assert view.snackbar is not None, "删除后没有撤销出口"
    assert view.snackbar.isVisible()
    assert hasattr(view.snackbar, "action_btn")

    view.snackbar.action_btn.click()
    app.processEvents()
    assert len(view._cards) == 3, "撤销后卡片没回来"
    assert [c.id for c in restored] == [2], "card_restored 信号没发出"


def test_snackbar_has_timeout(app):
    """
    提示条必须会自己消失。

    永远挂着的提示条会挡住下面的内容，也训练不出「稍后处理」的习惯。
    """
    from ui.components.snackbar import Snackbar
    sb = Snackbar()
    sb.show_message("已删除", "撤销", lambda: None, timeout=1200)
    assert sb._timer.isActive()
    assert sb._timer.interval() == 1200


def test_snackbar_actually_paints(app):
    """
    提示条必须真的画出东西。

    回归测试：Snackbar 曾是 QWidget 子类，QSS 里的裸 QWidget 选择器
    不会给自定义 QWidget 绘制背景 —— 结果控件存在、有文字、但整个
    卡片一片透明，界面上等于没有。改成 QFrame 后才有背景。
    """
    from PySide6.QtCore import QEventLoop, QPoint, QTimer
    from PySide6.QtGui import QColor, QImage, QPainter
    from ui.components.snackbar import Snackbar

    sb = Snackbar()
    sb.show_message("已删除一条活动记录", "撤销", lambda: None)
    sb.adjustSize()

    # 入场是淡入动画，不等它走完就截图只会拍到 opacity=0
    _pump(300)

    bg = QColor("#1C1C1E")
    img = QImage(sb.size(), QImage.Format_ARGB32)
    img.fill(bg)
    p = QPainter(img)
    sb.render(p, QPoint())
    p.end()

    painted = sum(1 for y in range(img.height()) for x in range(img.width())
                  if QColor(img.pixel(x, y)) != bg)
    assert painted > 2000, f"提示条几乎没有绘制任何像素（{painted}），会完全看不见"


def test_snackbar_action_fires_and_dismisses(app):
    """点撤销应该执行回调并收起提示条"""
    from ui.components.snackbar import Snackbar
    sb = Snackbar()
    fired = []
    sb.show_message("已删除", "撤销", lambda: fired.append(1))
    sb.action_btn.click()
    app.processEvents()
    assert fired == [1], "撤销回调没触发"
    # 收起是淡出动画，隐藏发生在动画结束后
    _pump(260)
    assert not sb.isVisible(), "点完撤销后提示条应该收起"


def _pump(ms: int):
    """让事件循环真的转起来，否则定时器与动画都不会推进"""
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ── 加载态：宽度不能变 ───────────────────────────────────────


def test_loading_button_keeps_its_label(app):
    """
    按钮进入加载态时文案不变。

    换文案会让宽度收缩，旁边的控件被顶得挪位置 ——
    布局在等待期间抖一下，看起来像卡了。
    """
    from ui.components.spinner import SpinnerDot
    from ui.components.scale_feedback import FeedbackButton
    import ui.motion as M

    M.get_motion_settings().set_override(True)
    btn = FeedbackButton("停止录制")
    btn.setFixedSize(180, 44)
    text_before = btn.text()
    width_before = btn.width()

    sp = SpinnerDot(btn, "#FFFFFF", 14)
    sp.show()
    app.processEvents()
    assert btn.text() == text_before, "加载态换了文案"
    assert btn.width() == width_before, "加载态改变了按钮宽度"
    sp.stop()


def test_spinner_stops_when_reduced_motion(app):
    """减少动效下不启动定时器，但点阵仍然画出来表明在处理"""
    from ui.components.spinner import SpinnerDot
    import ui.motion as M

    M.get_motion_settings().set_override(False)
    sp = SpinnerDot(None, "#FFFFFF", 14)
    sp.start()
    assert not sp.is_animating(), "减少动效下仍在跑脉冲定时器"
    sp.stop()
    M.get_motion_settings().set_override(None)


# ── 禁用态：必须说明原因 ──────────────────────────────────────


def test_disabled_report_buttons_explain_why(app):
    """
    灰掉的复制/导出按钮要说明为什么不可用。

    纯灰按钮不会自解释，用户只能猜。
    """
    import os
    import tempfile
    from database.storage import StorageManager
    from ui.daily_report_view import DailyReportView

    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "t.db")
    try:
        storage = StorageManager(db_path=db_path)
        view = DailyReportView(storage)
        view._load_report("2026-09-28")
        assert not view.copy_btn.isEnabled()
        assert not view.export_btn.isEnabled()
        assert "尚未生成" in view.copy_btn.toolTip()
        assert "尚未生成" in view.export_btn.toolTip()
        # Windows 上文件句柄会阻止删除，交给 pytest 清理 tmp 即可
        view.deleteLater()
    finally:
        app.processEvents()


# ── 命中区与可访问名称 ────────────────────────────────────────


def test_icon_only_controls_have_accessible_names(app):
    """
    纯图标按钮必须有可访问名称。

    没有名称时读屏只会念「按钮」，用户完全不知道它是上一天还是下一天。
    """
    from ui.timeline_view import TimelineHeader
    h = TimelineHeader()
    for btn in (h.prev_btn, h.next_btn):
        assert btn.accessibleName(), "图标按钮缺少可访问名称"
        assert btn.toolTip(), "图标按钮缺少提示"


def test_collapsible_button_meets_hit_target(app):
    """折叠按钮命中区要够大（桌面 40px 起步）"""
    from ui.timeline_view import StatsSummaryWidget
    s = StatsSummaryWidget()
    assert s.collapse_btn.width() >= 40
    assert s.collapse_btn.height() >= 40
    assert s.collapse_btn.accessibleName()


def test_filter_pills_meet_hit_target_and_name(app):
    """筛选药丸是高频点击目标，且要能被读屏识别"""
    from ui.timeline_view import CategoryFilterBar
    bar = CategoryFilterBar()
    bar.update_counts([])
    assert bar._buttons, "没有生成筛选药丸"
    for cat, btn in bar._buttons.items():
        assert btn.height() >= 40, f"{cat} 药丸命中区只有 {btn.height()}px"
        assert btn.accessibleName(), f"{cat} 药丸缺少可访问名称"


def test_filter_pill_name_includes_count(app):
    """药丸的可访问名称要带上数量，否则筛选结果无从预期"""
    from ui.timeline_view import CategoryFilterBar
    from core.types import ActivityCard
    from datetime import datetime, timedelta

    bar = CategoryFilterBar()
    s = datetime.now()
    cards = [
        ActivityCard(id=1, category="编程", title="a", summary="",
                     start_time=s, end_time=s + timedelta(minutes=10),
                     app_sites=[], distractions=[], productivity_score=50),
        ActivityCard(id=2, category="编程", title="b", summary="",
                     start_time=s, end_time=s + timedelta(minutes=10),
                     app_sites=[], distractions=[], productivity_score=50),
    ]
    bar.update_counts(cards)
    name = bar._buttons["编程"].accessibleName()
    assert "编程" in name
    assert "2" in name, f"名称里没有数量: {name}"


def _make_card(cid: int):
    from datetime import datetime, timedelta
    from core.types import ActivityCard

    s = datetime.now() + timedelta(hours=cid)
    return ActivityCard(
        id=cid, category="编程", title=f"活动 {cid}", summary="摘要",
        start_time=s, end_time=s + timedelta(minutes=30),
        app_sites=[], distractions=[], productivity_score=80,
    )


# ── 构造冒烟：import 错不会在 import 期暴露，只在构造时炸 ──────


def test_settings_panel_constructs(app):
    """
    设置面板必须能真的构造出来。

    回归测试：settings_view 用了 QProgressBar 但只 import 了
    QProgressDialog。模块 import 不会报错（那个名字到构造时才被
    读到），所以 78 个测试全绿也照样启动崩溃。
    """
    import os
    import tempfile
    from database.storage import StorageManager
    from ui.settings_view import SettingsPanel

    tmp = tempfile.mkdtemp()
    try:
        storage = StorageManager(db_path=os.path.join(tmp, "t.db"))
        panel = SettingsPanel(storage)
        panel.show()
        app.processEvents()
        assert panel is not None
        panel.deleteLater()
    finally:
        app.processEvents()


def test_all_qt_names_are_imported(app):
    """
    静态检查：文件里用到的 Qt 类名必须都在 import 里。

    这类错误只在运行时炸，测试和 import 检查都发现不了 ——
    除非专门做一次 AST 扫描。
    """
    import ast
    import io
    from pathlib import Path

    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    offenders = []

    for py in sorted(ui_dir.rglob("*.py")):
        src = io.open(py, encoding="utf-8").read()
        tree = ast.parse(src, str(py))

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    imported.add(a.asname or a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    imported.add((a.asname or a.name).split(".")[0])

        used = {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}

        missing = sorted(
            n for n in used
            if n.startswith("Q") and n[1:2].isupper() and n not in imported
        )
        if missing:
            offenders.append(f"{py.name}: {', '.join(missing)}")

    assert not offenders, "以下文件用了未 import 的 Qt 类:\n" + "\n".join(offenders)
