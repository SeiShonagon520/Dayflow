"""
Dayflow Windows - 动效系统

统一管理时长、缓动曲线与降级策略。所有界面动效都必须走这里，
不允许在各个 widget 里硬编码毫秒数 —— 否则动效会各自为政，
而且关掉「减少动态效果」时总会有几个地方漏掉。

设计约束（来自 design/motion 规范）：
  · 动效只用来解释「变了 / 从哪来 / 归谁触发 / 正在处理」，
    不做入场表演。产品界面要一打开就能用。
  · 只动 transform 与 opacity，不动 width/height/margin —— 那会触发重排。
  · 150ms 是响应基线；离开要比进入快。
  · prefers-reduced-motion 不是补丁，是设计的一部分。Windows 上对应
    「设置 → 辅助功能 → 视觉效果 → 动画效果」关闭，这里读系统偏好。
"""
from __future__ import annotations

import ctypes
import logging
import sys
from typing import Optional

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QObject, QPoint, QPropertyAnimation,
    QTimer, Qt, Signal,
)

logger = logging.getLogger(__name__)


# ── 时长阶梯（毫秒）─────────────────────────────────────────
# 全应用只用这几个值。新增动效请先想清楚落在哪一档。
DURATION = {
    "instant": 0,
    "tactile": 100,   # 按下反馈、快速关闭
    "base": 150,      # 基线：hover、按下、焦点环
    "reveal": 200,    # 小范围揭示、成功确认
    "menu": 250,      # 菜单、弹出层、小对话框
    "space": 300,     # 卡片入场、折叠展开、页面切换
    "page": 400,      # 全屏级转场
}


# ── 缓动曲线 ────────────────────────────────────────────────
# 全部是减速出（decelerate），符合「物体会停下来的直觉」。
# 刻意不用 bounce / elastic —— 那类曲线让软件显得廉价。
EASE = {
    # 最常用的出弯：起步快、收尾稳
    "out": QEasingCurve.Type.OutCubic,
    # 更强的减速，用于位移较大的入场
    "out_quart": QEasingCurve.Type.OutQuart,
    # 对称缓动，用于可逆的开关类动效
    "in_out": QEasingCurve.Type.InOutCubic,
    # 线性，用于进度条这类需要匀速表达的
    "linear": QEasingCurve.Type.Linear,
}


# ── 减少动态效果 ────────────────────────────────────────────
_SPI_GETCLIENTAREAANIMATION = 0x1042


def _windows_animations_enabled() -> bool:
    """
    读取 Windows 的「动画效果」系统偏好。

    对应「设置 → 辅助功能 → 视觉效果 → 动画效果」开关，
    也是 SystemParametersInfo(SPI_GETCLIENTAREAANIMATION)，
    很多第三方 Qt 应用都用它做 reduced-motion 判断。

    非 Windows 或读取失败时一律返回 True（保留动效），
    宁可多动也不要因为读不到开关就让界面失去反馈。
    """
    if sys.platform != "win32":
        return True
    try:
        enabled = ctypes.c_int(0)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            _SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
        if not ok:
            return True
        return bool(enabled.value)
    except Exception as e:  # pragma: no cover - 平台相关
        logger.debug("读取系统动画偏好失败，按启用处理: %s", e)
        return True


class MotionSettings(QObject):
    """
    全局动效开关。

    默认跟随 Windows 系统偏好；用户可在设置里覆盖为
    「跟随系统 / 关闭 / 开启」三档。
    """

    preference_changed = Signal(bool)  # (reduce_motion 是否生效)

    # 存储键：off=强制关闭, on=强制开启, system=跟随系统
    KEY = "reduce_motion"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._system_reduces = not _windows_animations_enabled()
        self._override: Optional[bool] = None  # True=强制开启动效
        self._storage = None
        self._loaded = False

    def attach_storage(self, storage):
        """挂上配置存储并读取用户偏好"""
        self._storage = storage
        self.reload()

    def reload(self):
        raw = None
        if self._storage is not None:
            try:
                raw = self._storage.get_setting(self.KEY, "system")
            except Exception as e:
                logger.debug("读取动效偏好失败: %s", e)
        self._loaded = True
        if raw == "off":
            self._override = False
        elif raw == "on":
            self._override = True
        else:
            self._override = None
        self.preference_changed.emit(self.reduced)

    def set_override(self, value: Optional[bool]):
        """
        设置用户覆盖。
        True = 强制开启动效，False = 强制关闭，None = 跟随系统。
        """
        self._override = value
        if self._storage is not None:
            raw = "system" if value is None else ("on" if value else "off")
            try:
                self._storage.set_setting(self.KEY, raw)
            except Exception as e:
                logger.debug("保存动效偏好失败: %s", e)
        self.preference_changed.emit(self.reduced)
        reset_all_scales()

    @property
    def system_reduces(self) -> bool:
        """系统当前是否要求减少动效"""
        return self._system_reduces

    @property
    def override(self) -> Optional[bool]:
        """
        用户覆盖。True=强制开启，False=强制关闭，None=跟随系统。
        """
        return self._override

    @property
    def reduced(self) -> bool:
        """最终是否应当减少动效"""
        if self._override is None:
            return self._system_reduces
        return not self._override

    def refresh_system(self):
        """重新读取系统偏好（用户在系统设置里改了之后调用）"""
        self._system_reduces = not _windows_animations_enabled()
        self.preference_changed.emit(self.reduced)


_settings: Optional[MotionSettings] = None


def get_motion_settings() -> MotionSettings:
    """获取全局动效设置单例"""
    global _settings
    if _settings is None:
        _settings = MotionSettings()
    return _settings


def reduced_motion() -> bool:
    """当前是否应减少动效（所有动效的唯一开关）"""
    return get_motion_settings().reduced


def duration_ms(key: str) -> int:
    """
    取时长。减少动效时，除 tactile/instant 外一律压到 0。

    保留 tactile 的理由：按下反馈要「立刻」，它不是运动而是状态确认，
    即使开了减少动态效果也应该有 —— 用户需要知道点击被接收了。
    """
    base = DURATION.get(key, DURATION["base"])
    if reduced_motion() and key not in ("instant", "tactile"):
        return 0
    return base


def easing(name: str) -> QEasingCurve:
    """取缓动曲线"""
    return EasingCurve(EASE.get(name, EASE["out"]))


# 旧名别名，保持可读性
EasingCurve = QEasingCurve


# ── 通用动效构件 ────────────────────────────────────────────

# 缩放状态登记：用户可能在按钮正处于按下缩放时切换「减少动效」，
# 那会让按钮卡在 0.97 上再也不弹回来 —— 一个再也点不动的按钮。
# 登记所有用过缩放的控件，用户切档时统一复位。
_scaled_widgets = []


def register_scaled(widget: QObject):
    if widget not in _scaled_widgets:
        _scaled_widgets.append(widget)


def reset_all_scales():
    """把所有登记过的控件缩放复位到 1.0"""
    for w in list(_scaled_widgets):
        try:
            w.setProperty("scale", 1.0)
        except Exception:
            # 控件可能已被销毁
            try:
                _scaled_widgets.remove(w)
            except ValueError:
                pass


def _prop_name(prop) -> str:
    """
    把属性名统一成 str。

    QPropertyAnimation 接受 bytes，QObject.setProperty 只接受 str。
    这个差异很容易踩：降级路径上传 bytes 会抛 TypeError，
    而如果异常被吞掉，表现就是「关掉动效后界面卡在起始状态」。
    """
    if isinstance(prop, (bytes, bytearray)):
        return prop.decode("utf-8")
    return str(prop)


def animate_property(
    target: QObject,
    prop: bytes,
    start,
    end,
    *,
    duration: str = "base",
    ease: str = "out",
    parent: Optional[QObject] = None,
    finished=None,
) -> Optional[QPropertyAnimation]:
    """
    创建一个属性动画。减少动效时直接跳到终值并返回 None。

    返回 None 表示「没有动画发生」，调用方不需要特殊处理 ——
    终值已经就位了。这是让降级逻辑只写一遍的关键。
    """
    ms = duration_ms(duration)
    if ms <= 0:
        # 注意：setProperty 只接受 str，QPropertyAnimation 才接受 bytes。
        # 传 bytes 会抛 TypeError，属性静默不生效 —— 界面就卡在起始值。
        try:
            target.setProperty(_prop_name(prop), end)
        except Exception as e:
            logger.exception("降级设值 %r 失败: %s", prop, e)
        if finished:
            finished()
        return None

    anim = QPropertyAnimation(target, prop, parent or target)
    anim.setDuration(ms)
    anim.setEasingCurve(easing(ease))
    anim.setStartValue(start)
    anim.setEndValue(end)
    if finished:
        anim.finished.connect(finished)
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


def press_feedback(widget: QObject, scale: float = 0.97):
    """
    按下时的轻微缩放反馈。

    0.97 是有意选的：再深就显得「凹下去」，在桌面工具里读作廉价。

    减少动效时完全不做缩放。缩放是空间运动，按规范应当被切掉；
    按下的反馈并不会因此消失 —— 样式表的 :pressed 底色会立刻变化，
    用户依然知道「点到了」。这正是「用状态变化代替运动」的落法。
    """
    if reduced_motion():
        return None
    register_scaled(widget)
    return animate_property(
        widget, b"scale", 1.0, scale, duration="tactile", ease="out"
    )


def release_feedback(widget: QObject, scale: float = 0.97):
    """松开时弹回原位，用和按下同一档时长，避免黏滞感"""
    if reduced_motion():
        return None
    register_scaled(widget)
    return animate_property(
        widget, b"scale", scale, 1.0, duration="tactile", ease="out"
    )


def fade_in(widget: QObject, *, duration: str = "reveal", delay: int = 0,
             finished=None):
    """
    淡入。减少动效时 delay 归零并瞬时完成 —— 焦点、进度、加载这些
    功能性信号必须继续存在，只是不再「动」。
    """
    widget.setGraphicsEffect(None)
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)

    ms = duration_ms(duration)

    def _done():
        widget.setGraphicsEffect(None)
        if finished:
            finished()

    if ms <= 0:
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(None)
        if finished:
            finished()
        return None

    anim = QPropertyAnimation(effect, b"opacity", effect)
    anim.setDuration(ms)
    anim.setEasingCurve(easing("out"))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.finished.connect(_done)
    if delay:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(delay, anim.start)
    else:
        anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


def rise_in(widget: QObject, *, duration: str = "space", delay: int = 0,
            distance: int = 8, finished=None):
    """
    轻微上移 + 淡入，用于低频的内容抵达（新卡片、空状态）。

    距离刻意很小（8px）。桌面工具不需要「登场」，
    元素应该像本来就在那儿，只是刚刚出现。
    """
    if reduced_motion():
        if finished:
            finished()
        return None

    start_pos = QPoint(0, distance)
    animate_property(
        widget, b"pos", start_pos, QPoint(0, 0),
        duration=duration, ease="out_quart",
    )
    return fade_in(widget, duration=duration, delay=delay, finished=finished)


def collapse_out(widget: QObject, *, on_done=None, height: Optional[int] = None):
    """
    折叠消失 —— 用于删除卡片这类「这东西没了」的确认。

    离开比进入快（约 150ms vs 300ms）：用户已经知道它要走了，
    慢慢退场是在浪费他的时间。
    """
    if height is None:
        height = widget.height()

    def _finish():
        widget.hide()
        if on_done:
            on_done()

    ms = duration_ms("tactile") or 100
    anim = QPropertyAnimation(widget, b"maximumHeight", widget)
    anim.setDuration(ms)
    anim.setEasingCurve(easing("in_out"))
    anim.setStartValue(height)
    anim.setEndValue(0)
    anim.finished.connect(_finish)
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


def expand_height(widget: QObject, *, duration: str = "space"):
    """
    展开容器到自然高度。

    折叠/展开比删除更需要动效：空间在变大变小，眼睛要跟着走，
    瞬变会让人丢失「刚才那块东西去哪了」。

    高度动画确实会触发布局重排，但展开是低频操作（用户主动点的），
    这点代价换来的空间连续性是值得的。日常滚动路径不碰它。
    """
    if reduced_motion():
        widget.setMaximumHeight(16777215)   # QWIDGETSIZE_MAX
        widget.show()
        return None

    natural = widget.sizeHint().height()
    widget.setMaximumHeight(0)
    widget.show()

    anim = QPropertyAnimation(widget, b"maximumHeight", widget)
    anim.setDuration(duration_ms(duration))
    anim.setEasingCurve(easing("out_quart"))
    anim.setStartValue(0)
    anim.setEndValue(max(natural, 1))

    def _done():
        # 交还尺寸控制权，否则内容变化后高度会被钉死
        widget.setMaximumHeight(16777215)

    anim.finished.connect(_done)
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


def collapse_height(widget: QObject, *, duration: str = "base", on_done=None):
    """
    折叠容器到 0 高度并隐藏。

    比展开快一档：收起是「我不需要它了」，动作已经完成，
    让用户等动画看完是多余的。
    """
    start = widget.sizeHint().height()

    def _finish():
        widget.hide()
        widget.setMaximumHeight(16777215)
        if on_done:
            on_done()

    if reduced_motion():
        widget.hide()
        if on_done:
            on_done()
        return None

    anim = QPropertyAnimation(widget, b"maximumHeight", widget)
    anim.setDuration(duration_ms("tactile") or 100)
    anim.setEasingCurve(easing("in_out"))
    anim.setStartValue(start)
    anim.setEndValue(0)
    anim.finished.connect(_finish)
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


def flash(widget: QObject, *, duration: str = "reveal"):
    """
    一次性短促强调 —— 用于「刚发生了这件事」。

    用缩放而不是颜色闪烁：颜色闪要动整个控件背景，视觉很吵；
    轻微放大再回落更安静，也更容易被余光捕捉到。
    """
    if reduced_motion():
        return None

    from PySide6.QtCore import QSequentialAnimationGroup

    group = QSequentialAnimationGroup(widget)

    grow = QPropertyAnimation(widget, b"scale", group)
    grow.setDuration(duration_ms("tactile") or 100)
    grow.setEasingCurve(easing("out"))
    grow.setStartValue(1.0)
    grow.setEndValue(1.03)

    settle = QPropertyAnimation(widget, b"scale", group)
    settle.setDuration(duration_ms("tactile") or 100)
    settle.setEasingCurve(easing("in_out"))
    settle.setStartValue(1.03)
    settle.setEndValue(1.0)

    group.addAnimation(grow)
    group.addAnimation(settle)
    group.start(QAbstractAnimation.DeleteWhenStopped)
    return group


def pop_in(widget: QObject, *, duration: str = "menu", scale_from: float = 0.96,
           offset=(0, 4)):
    """
    菜单/弹出层入场：从触发点方向轻微长出来。

    位移很小（4px）——菜单是贴着光标弹出的，往哪儿「来」应该
    指向它的来源，而不是从屏幕中央飞过来。缩放从 0.96 起步而不是 0：
    从 0 开始读作「弹出」，菜单该读作「浮现」。
    """
    if reduced_motion():
        return None

    origin = widget.pos()
    animate_property(
        widget, b"pos",
        origin + QPoint(offset[0], offset[1]), origin,
        duration=duration, ease="out_quart",
    )

    from PySide6.QtWidgets import QGraphicsOpacityEffect

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    anim = QPropertyAnimation(effect, b"opacity", effect)
    anim.setDuration(duration_ms(duration))
    anim.setEasingCurve(easing("out"))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


def shake(widget: QObject, *, distance: int = 6, cycles: int = 3):
    """
    错误反馈：短促横向抖动。

    刻意做得克制且很快 —— 错误动效必须「有用且不抢戏」。
    持续摇晃、变红、闪烁都是把用户的注意力从「怎么修」拉到「看我」。

    抖动本身不携带信息，错误信息由旁边的文字承担；这里只负责
    把视线引到那个文字上。
    """
    if reduced_motion():
        return None

    from PySide6.QtCore import QSequentialAnimationGroup

    group = QSequentialAnimationGroup(widget)
    origin = widget.pos()
    for i in range(cycles):
        direction = -1 if i % 2 == 0 else 1
        step = QPropertyAnimation(widget, b"pos", group)
        step.setDuration(duration_ms("instant") or 45)
        step.setEasingCurve(easing("in_out"))
        step.setStartValue(origin)
        step.setEndValue(origin + QPoint(direction * distance, 0))
        group.addAnimation(step)

    back = QPropertyAnimation(widget, b"pos", group)
    back.setDuration(duration_ms("tactile") or 100)
    back.setEasingCurve(easing("out"))
    back.setStartValue(origin + QPoint(-distance if cycles % 2 else 0, 0))
    back.setEndValue(origin)
    group.addAnimation(back)

    group.start(QAbstractAnimation.DeleteWhenStopped)
    return group


def stagger_delays(count: int, step: int = 20, jitter: int = 5) -> list[int]:
    """
    生成错峰延迟。

    带 ±jitter 是刻意的：完全均匀的延迟看起来像机器生成的，
    人眼对这种规律异常敏感。总数封顶，避免长列表末尾等太久。
    """
    import random

    delays = []
    for i in range(min(count, 12)):  # 最多只错峰前 12 个
        delays.append(i * step + random.randint(-jitter, jitter))
    return [max(0, d) for d in delays]
