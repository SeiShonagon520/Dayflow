"""
Dayflow Windows - 动效补充测试

覆盖折叠/展开、菜单入场、错误抖动、分析进度。
这些是「必须有但容易漏」的动效：漏了不会报错，只是界面变得死板。
"""
import pytest

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def full_motion():
    """这些测试要验证动效真的会动，所以先确保动效是开的"""
    from ui.motion import get_motion_settings
    get_motion_settings().set_override(True)
    yield
    get_motion_settings().set_override(None)


def _pump(ms: int = 200):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ── 折叠 / 展开 ──────────────────────────────────────────────


def _stack(n=4):
    host = QWidget()
    lay = QVBoxLayout(host)
    inner = QWidget()
    il = QVBoxLayout(inner)
    for i in range(n):
        il.addWidget(QLabel(f"row {i}"))
    lay.addWidget(inner)
    host.resize(300, 300)
    host.show()
    return host, inner


def test_expand_height_animates_and_hands_back_control(app):
    """
    展开要有高度变化过程，结束后把高度控制权还给布局。

    不还回来的话，内容变多时高度会被钉死，容器再也长不大。
    """
    from ui.motion import expand_height

    host, inner = _stack()
    inner.setVisible(False)
    app.processEvents()

    anim = expand_height(inner, duration="space")
    assert anim is not None, "展开没有产生动画"
    _pump(60)
    mid = inner.maximumHeight()
    _pump(400)
    assert inner.isVisible()
    assert inner.maximumHeight() == 16777215, "展开后没有交还尺寸控制权"
    host.close()


def test_collapse_height_hides_widget(app):
    """折叠要真的隐藏，而不是只把高度压到 0"""
    from ui.motion import collapse_height

    host, inner = _stack()
    app.processEvents()
    anim = collapse_height(inner, duration="base")
    assert anim is not None
    _pump(250)
    assert not inner.isVisible(), "折叠后控件仍然可见"
    assert inner.maximumHeight() == 16777215, "折叠后尺寸控制权没还回来"
    host.close()


def test_expand_collapse_instant_when_reduced(app):
    """减少动效时折叠/展开应当瞬时完成，不做高度动画"""
    from ui.motion import get_motion_settings, collapse_height, expand_height

    get_motion_settings().set_override(False)
    host, inner = _stack()
    inner.setVisible(False)
    app.processEvents()

    assert expand_height(inner) is None
    assert inner.isVisible(), "减少动效下展开后应该直接可见"
    assert collapse_height(inner) is None
    assert not inner.isVisible()
    host.close()


# ── 菜单入场 ─────────────────────────────────────────────────


def test_pop_in_fades_and_cleans_up(app):
    """
    菜单入场要淡入，结束后摘掉 graphicsEffect。

    不摘的话 effect 会一直挂在控件上，后续每次重绘都多一层合成开销。
    """
    from PySide6.QtWidgets import QMenu
    from ui.motion import pop_in

    m = QMenu()
    m.addAction("编辑")
    m.adjustSize()
    m.show()
    app.processEvents()

    anim = pop_in(m, duration="menu", offset=(0, 4))
    assert anim is not None
    eff = m.graphicsEffect()
    assert eff is not None, "入场没有挂上透明度效果"
    assert eff.opacity() < 1.0, "入场起点应该是不透明的 0"

    _pump(400)
    assert m.graphicsEffect() is None, "入场结束后没有清理 graphicsEffect"
    m.close()


# ── 错误抖动 ─────────────────────────────────────────────────


def test_shake_returns_to_origin(app):
    """
    错误抖动结束必须回到原位。

    停在偏移位置会让控件和它旁边的文字错位，比不抖还糟。
    """
    from ui.components.scale_feedback import FeedbackButton
    from ui.motion import shake

    b = FeedbackButton("保存配置")
    b.setFixedSize(160, 44)
    b.move(50, 50)
    b.show()
    app.processEvents()

    origin = b.pos()
    anim = shake(b, distance=6, cycles=3)
    assert anim is not None
    # 采样整段抖动过程：第一个子动画可能还没推进，
    # 只在单一时间点断言会漏掉「其实完全没动」的情况
    seen = set()
    for _ in range(6):
        _pump(30)
        seen.add((b.pos().x(), b.pos().y()))
    assert len(seen) > 1, "抖动过程中位置始终没变"
    assert (origin.x(), origin.y()) not in seen or len(seen) > 1
    _pump(500)
    assert b.pos() == origin, f"抖动后没有归位: {b.pos()} != {origin}"


def test_shake_is_short(app):
    """错误动效必须短促，拖沓的报错比不报还烦人"""
    from ui.motion import DURATION, duration_ms
    # shake 用 instant + tactile 两档，都应该在 100ms 量级
    assert duration_ms("instant") == 0
    assert duration_ms("tactile") <= 100


def test_shake_suppressed_when_reduced(app):
    from ui.motion import get_motion_settings, shake
    get_motion_settings().set_override(False)
    b = QWidget()
    b.move(10, 10)
    assert shake(b) is None, "减少动效下仍在抖动"
    assert b.pos().x() == 10


# ── 分析进度 ─────────────────────────────────────────────────


def test_progress_bar_only_when_total_known(app):
    """
    有真实总量才画进度条。

    画一条不知道多长的条是编造进度，比不画更糟。
    """
    from ui.timeline_view import EmptyStateWidget

    w = EmptyStateWidget()
    w.show()          # isVisible() 需要父控件可见才为真
    app.processEvents()

    w.set_has_pending_analysis(True, 0, 0)
    assert not w.progress_bar.isVisible(), "没有总量时不该显示进度条"

    w.set_has_pending_analysis(True, 2, 5)
    assert w.progress_bar.isVisible()
    assert w.progress_bar.maximum() == 5
    assert w.progress_bar.value() == 2
    w.close()


def test_timeline_progress_drives_empty_state(app):
    """进度要真的能驱动空状态显示"""
    from ui.timeline_view import TimelineView

    tv = TimelineView()
    tv.resize(600, 400)
    tv.show()
    tv.set_cards([])
    app.processEvents()

    tv.set_analysis_progress(1, 3)
    app.processEvents()
    ew = tv.empty_widget
    assert ew.progress_bar.isVisible()
    assert ew.progress_bar.value() == 1
    assert ew.progress_bar.maximum() == 3

    # 分析完成：0/0 表示没有待处理切片，不该还显示进度
    tv.set_analysis_progress(0, 0)
    app.processEvents()
    assert not ew.progress_bar.isVisible()
    tv.close()


def test_progress_beyond_total_is_clamped(app):
    """进度不该超过总量，否则进度条画过头"""
    from ui.timeline_view import EmptyStateWidget

    w = EmptyStateWidget()
    w.show()
    app.processEvents()
    w.set_has_pending_analysis(True, 99, 3)
    assert w.progress_bar.value() <= w.progress_bar.maximum()
    w.close()


def test_scheduler_emits_progress(app):
    """调度器要真的发出进度序列"""
    import asyncio
    import threading
    from core.analysis import AnalysisScheduler

    seen = []
    sched = AnalysisScheduler.__new__(AnalysisScheduler)
    sched.progress_callback = lambda d, t: seen.append((d, t))
    sched._stop_event = threading.Event()
    sched._create_batches = lambda chunks: [[1], [2], [3]]

    async def noop(*a, **k):
        return []

    sched._process_batch = noop
    sched.storage = type("S", (), {"get_pending_chunks": lambda self: [1, 2, 3]})()

    asyncio.new_event_loop().run_until_complete(sched._scan_and_process())

    assert seen, "调度器没有发出任何进度"
    assert seen[0] == (0, 3), f"起始进度不对: {seen[0]}"
    assert seen[-1] == (3, 3), f"结束进度不对: {seen[-1]}"
    assert len(seen) >= 4, "进度序列不完整"


def test_scheduler_progress_callback_failure_does_not_break(app):
    """进度回调抛异常不该拖垮分析本身"""
    import asyncio
    import threading
    from core.analysis import AnalysisScheduler

    def boom(done, total):
        raise RuntimeError("callback exploded")

    sched = AnalysisScheduler.__new__(AnalysisScheduler)
    sched.progress_callback = boom
    sched._stop_event = threading.Event()
    sched._create_batches = lambda chunks: [[1]]

    async def noop(*a, **k):
        return []

    sched._process_batch = noop
    sched.storage = type("S", (), {"get_pending_chunks": lambda self: [1]})()

    # 不抛出来就算通过
    asyncio.new_event_loop().run_until_complete(sched._scan_and_process())


def test_settings_result_motion_used(app):
    """设置页的连接结果要带动效（成功上浮 / 失败抖动）"""
    import inspect
    from ui.settings_view import SettingsPanel

    src = inspect.getsource(SettingsPanel._show_test_result)
    assert "shake" in src, "失败结果没有抖动"
    assert "rise_in" in src, "成功结果没有上浮"

    src2 = inspect.getsource(SettingsPanel._set_email_result)
    assert "shake" in src2 and "rise_in" in src2


def test_collapse_uses_motion(app):
    """折叠按钮要真的走动画，而不是瞬时隐藏"""
    import inspect
    from ui.timeline_view import StatsSummaryWidget

    src = inspect.getsource(StatsSummaryWidget._toggle_collapse)
    assert "collapse_height" in src
    assert "expand_height" in src
    assert "setVisible" not in src, "折叠仍在用瞬时 setVisible"
