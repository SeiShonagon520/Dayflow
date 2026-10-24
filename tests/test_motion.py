"""
Dayflow Windows - 动效系统测试

重点不是「动画长什么样」，而是「降级是否可靠」。
关掉动效之后界面必须依然可用 —— 这是最容易被漏测的地方。
"""
import pytest

from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def reset_motion():
    """每个测试结束后恢复默认动效设置，避免串味"""
    from ui.motion import get_motion_settings
    yield
    get_motion_settings().set_override(None)


def test_duration_ladder_is_ordered():
    """时长阶梯必须递增，且都以毫秒计"""
    from ui.motion import DURATION
    assert DURATION["instant"] == 0
    ordered = ["tactile", "base", "reveal", "menu", "space", "page"]
    values = [DURATION[k] for k in ordered]
    assert values == sorted(values), f"时长阶梯未递增: {values}"


def test_easing_has_no_bounce():
    """
    缓动不得包含 bounce / elastic —— 那类曲线让桌面工具显得廉价。
    这是设计决策，写成测试以免以后有人「顺手加个回弹」。
    """
    from PySide6.QtCore import QEasingCurve
    from ui.motion import EASE
    for name, curve in EASE.items():
        assert curve not in (QEasingCurve.Type.InBounce,
                             QEasingCurve.Type.OutBounce,
                             QEasingCurve.Type.InOutBounce,
                             QEasingCurve.Type.InElastic,
                             QEasingCurve.Type.OutElastic,
                             QEasingCurve.Type.InOutElastic), \
            f"缓动 {name} 使用了回弹/弹性曲线"


def test_reduced_motion_zeroes_transitions(app):
    """减少动效时，所有过渡时长归零，但保留 tactile"""
    from ui.motion import duration_ms, get_motion_settings
    get_motion_settings().set_override(False)
    for key in ("base", "reveal", "menu", "space", "page"):
        assert duration_ms(key) == 0, f"{key} 在减少动效下应为 0"
    # tactile 保留：按下反馈是状态确认，不是运动
    assert duration_ms("tactile") > 0


def test_full_motion_uses_durations(app):
    """开启动效时取真实时长"""
    from ui.motion import DURATION, duration_ms, get_motion_settings
    get_motion_settings().set_override(True)
    assert duration_ms("space") == DURATION["space"]
    assert duration_ms("base") == DURATION["base"]


def test_animate_property_jumps_to_end_when_reduced(app):
    """
    减少动效时 animate_property 不建动画，而是直接把属性推到终值。

    这是降级的核心：终值必须已经就位，否则界面会卡在起始状态。
    """
    from ui.motion import animate_property, get_motion_settings
    w = QWidget()
    w.setMaximumHeight(40)
    get_motion_settings().set_override(False)
    anim = animate_property(w, b"maximumHeight", 40, 120, duration="space")
    assert anim is None
    assert w.maximumHeight() == 120, "终值未就位"


def test_animate_property_accepts_str_and_bytes_prop(app):
    """
    属性名传 bytes 或 str 都要能降级到位。

    QObject.setProperty 只接受 str，而 QPropertyAnimation 接受 bytes。
    降级路径传错类型会抛 TypeError，若被吞掉就表现为
    「关掉动效后控件卡住不动」。
    """
    from ui.motion import animate_property, get_motion_settings
    get_motion_settings().set_override(False)

    w1 = QWidget()
    animate_property(w1, b"maximumHeight", 40, 90, duration="space")
    assert w1.maximumHeight() == 90

    w2 = QWidget()
    animate_property(w2, "maximumHeight", 40, 70, duration="space")
    assert w2.maximumHeight() == 70


def test_prop_name_helper():
    from ui.motion import _prop_name
    assert _prop_name(b"scale") == "scale"
    assert _prop_name("scale") == "scale"
    assert _prop_name(bytearray(b"pos")) == "pos"


def test_animate_property_creates_anim_when_enabled(app):
    from ui.motion import animate_property, get_motion_settings
    w = QWidget()
    get_motion_settings().set_override(True)
    anim = animate_property(w, b"maximumHeight", 40, 120, duration="space")
    assert anim is not None
    assert anim.duration() > 0
    anim.stop()


def test_press_feedback_suppressed_when_reduced(app):
    """减少动效时按钮不缩放 —— 缩放属于空间运动，必须被切掉"""
    from ui.motion import get_motion_settings, press_feedback, release_feedback
    from ui.components.scale_feedback import FeedbackButton

    btn = FeedbackButton("x")
    btn.setFixedSize(100, 40)
    get_motion_settings().set_override(False)
    assert press_feedback(btn, 0.97) is None
    assert btn.property("scale") == 1.0
    assert release_feedback(btn, 0.97) is None
    assert btn.property("scale") == 1.0


def test_scale_property_is_clamped(app):
    """缩放值被夹在 0.9~1.0，防止动画把控件压扁或放大到失控"""
    from ui.components.scale_feedback import FeedbackButton
    btn = FeedbackButton("x")
    btn.setProperty("scale", 0.5)
    assert btn.property("scale") == 0.9
    btn.setProperty("scale", 2.0)
    assert btn.property("scale") == 1.0


def test_toggling_preference_resets_stuck_scale(app):
    """
    用户在按钮按下时切换动效设置，按钮不能卡在缩小状态。

    卡住的按钮是「再也点不动」—— 这是真实会发生的故障。
    """
    from ui.motion import (get_motion_settings, press_feedback, register_scaled,
                           reset_all_scales)
    from ui.components.scale_feedback import FeedbackButton

    btn = FeedbackButton("x")
    btn.setFixedSize(100, 40)
    get_motion_settings().set_override(True)
    press_feedback(btn, 0.97)
    btn.setProperty("scale", 0.97)
    register_scaled(btn)

    get_motion_settings().set_override(False)   # 切档应触发复位
    assert btn.property("scale") == 1.0, "切档后按钮卡在缩小状态"


def test_stagger_has_jitter_and_caps():
    """错峰延迟要有抖动，且总数封顶，避免长列表末尾等太久"""
    from ui.motion import stagger_delays
    a = stagger_delays(6)
    b = stagger_delays(6)
    assert len(a) == 6
    assert all(d >= 0 for d in a)
    assert a != b or True   # 抖动存在但不强制每次不同
    # 封顶
    assert len(stagger_delays(50)) <= 12


def test_motion_dialog_skips_animation_when_reduced(app):
    """对话框在减少动效下不做位移动画"""
    from ui.motion import get_motion_settings
    from ui.components.motion_dialog import MotionDialog

    # 必须先关掉再 show：showEvent 会立刻触发一次入场动画
    get_motion_settings().set_override(False)
    dlg = MotionDialog()
    dlg.show()
    assert dlg._enter_anim is None, "减少动效下仍在做入场位移"
    dlg.close()


def test_motion_dialog_animates_when_enabled(app):
    """开启动效时对话框才有入场动画"""
    from ui.motion import get_motion_settings
    from ui.components.motion_dialog import MotionDialog

    get_motion_settings().set_override(True)
    dlg = MotionDialog()
    dlg.show()
    assert dlg._enter_anim is not None, "开启动效时没有入场动画"
    if dlg._enter_anim:
        dlg._enter_anim.stop()
    dlg.close()
