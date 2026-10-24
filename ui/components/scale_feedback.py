"""
Dayflow Windows - 可缩放控件混入

给任意 QWidget 提供一个可动画的 `scale` 属性。没有它，
QPropertyAnimation 就没有可驱动的属性，按下反馈只能退化成换色。

scale 只影响绘制（paintEvent 里做变换），不触发布局重排 ——
这是「只动 transform」原则在 Qt 里的落法。
"""
from __future__ import annotations

from PySide6.QtCore import Property, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QPushButton, QStyle, QStyleOption


class ScaleFeedbackMixin:
    """
    为控件加上可动画的按压缩放。

    用法：
        class MyButton(ScaleFeedbackMixin, QPushButton):
            def paintEvent(self, e):
                if not self._draw_scaled(e):
                    super().paintEvent(e)
    """

    def _init_scale_feedback(self):
        self._scale = 1.0
        self._scale_timer = None

    def _get_scale(self) -> float:
        return self._scale

    def _set_scale(self, value: float):
        value = max(0.9, min(1.0, float(value)))
        if abs(value - self._scale) < 0.001:
            return
        self._scale = value
        self.update()

    scale = Property(float, _get_scale, _set_scale)

    def _paint_scaled(self, event) -> bool:
        """
        在子类 paintEvent 开头调用。

        返回 True 表示已接管绘制（缩放生效），子类应直接 return；
        返回 False 表示缩放为 1.0，交给子类原本的绘制逻辑。
        """
        if abs(self._scale - 1.0) < 0.001:
            return False

        opt = QStyleOption()
        opt.initFrom(self)
        opt.rect = self.rect()

        # 以中心为锚点缩放
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        s = self._scale
        dx = cx * (1.0 - s)
        dy = cy * (1.0 - s)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(dx, dy)
        painter.scale(s, s)
        painter.translate(-cx, -cy)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, painter, self)
        painter.end()
        return True

    def _scale_paint_event(self, event, fallback):
        """统一的 paintEvent 包装，供子类复用"""
        if self._paint_scaled(event):
            return
        fallback()


class FeedbackButton(ScaleFeedbackMixin, QPushButton):
    """
    带按压缩放反馈的 QPushButton。

    Dayflow 里所有按钮都应该用这个而不是裸 QPushButton ——
    统一反馈、统一降级，不会出现「有的按钮有反馈有的没有」。
    """

    press_scale = 0.97

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_scale_feedback()

    def paintEvent(self, event):
        if not self._paint_scaled(event):
            super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            from ui.motion import press_feedback
            press_feedback(self, self.press_scale)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        from ui.motion import release_feedback
        release_feedback(self, self.press_scale)
        super().mouseReleaseEvent(event)

