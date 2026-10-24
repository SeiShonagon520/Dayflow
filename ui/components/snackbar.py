"""
Dayflow Windows - 可撤销操作提示条（Snackbar）

删除一条活动记录是可恢复的，所以不该用「确定要删除吗？」把用户拦下来 ——
应该先做掉，再给一条退路。这是「撤销优于确认」原则的落法。

确认框只留给真正不可逆的操作：清空数据库、覆盖文件、付费。
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from ui.motion import animate_property, reduced_motion
from ui.components.scale_feedback import FeedbackButton


class Snackbar(QFrame):
    """
    底部浮出的操作提示条。

    必须是 QFrame 而不是 QWidget：QSS 只给内置的绘制角色（QFrame 等）
    上背景色，自定义 QWidget 子类即使写对了选择器也不会被绘制。

    规则：
      · 不阻断操作 —— 出现期间界面照常可用
      · 自带明确出口（「撤销」按钮），不用记住快捷键
      · 超时消失，且消失前不会被后来的 snackbar 顶掉
      · 尊重减少动效：只淡入淡出，不做位移
    """

    closed = Signal()

    DEFAULT_TIMEOUT = 6000
    ENTER_DURATION = 220
    EXIT_DURATION = 160

    def __init__(self, parent=None):
        super().__init__(parent)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self._undo_cb = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._positioned = False

    def _build(self, message: str, action_text: str, on_action):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 12, 12)
        lay.setSpacing(16)

        self.message_label = QLabel(message)
        self.message_label.setObjectName("snackbarText")
        lay.addWidget(self.message_label)
        lay.addStretch()

        if action_text and on_action:
            self.action_btn = FeedbackButton(action_text)
            self.action_btn.setObjectName("snackbarAction")
            self.action_btn.setCursor(Qt.PointingHandCursor)
            self.action_btn.setFixedHeight(30)
            self.action_btn.clicked.connect(self._on_action)
            lay.addWidget(self.action_btn)

        self._style()

    def _style(self):
        from ui.themes import get_theme
        t = get_theme()
        # 必须给 Snackbar 本身一个 objectName，并让 QFrame#snackbarRoot 命中。
        # 之前用裸 QWidget 选择器写背景色，QSS 不会给自定义 QWidget 子类
        # 绘制背景 —— 结果整个提示条什么都不画，只剩子控件的文字。
        self.setObjectName("snackbarRoot")
        self.setStyleSheet(f"""
            QFrame#snackbarRoot {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border_hover};
                border-radius: 14px;
            }}
            QLabel#snackbarText {{
                color: {t.text_primary};
                font-size: 14px;
                background: transparent;
                border: none;
            }}
            QPushButton#snackbarAction {{
                background-color: transparent;
                color: {t.accent};
                border: none;
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton#snackbarAction:hover {{
                background-color: {t.accent_light};
            }}
            QPushButton#snackbarAction:focus {{
                background-color: {t.accent_light};
                border: 2px solid {t.accent_focus};
                padding: 3px 11px;
            }}
        """)

    def show_message(self, message: str, action_text: str = "",
                      on_action=None, timeout: int = DEFAULT_TIMEOUT):
        """显示提示条。重复调用会复用同一个实例，不会叠出多条。"""
        # 重建内容
        for child in self.findChildren(QWidget):
            child.deleteLater()
        while self.layout() is not None and self.layout().count():
            self.layout().takeAt(0)

        self._undo_cb = on_action
        self._build(message, action_text, on_action)
        self.adjustSize()

        self.setVisible(True)
        self._reposition()

        self._fade(0.0, 1.0, self.ENTER_DURATION)
        if not reduced_motion():
            animate_property(self, b"pos",
                             self.pos() + QPoint(0, 12), self.pos(),
                             duration="menu", ease="out")
        self._timer.start(timeout)

    def _on_action(self):
        cb, self._undo_cb = self._undo_cb, None
        if cb:
            try:
                cb()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("撤销操作失败: %s", e)
        self.dismiss()

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        # 贴在父容器底部居中，留出足够边距避免压住最后一张卡片
        self.adjustSize()
        margin = 16
        x = max(margin, (parent.width() - self.width()) // 2)
        y = max(margin, parent.height() - self.height() - 40)
        self.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self._reposition()

    def _fade(self, start: float, end: float, ms: int):
        if ms <= 0:
            self._opacity.setOpacity(end)
            return None
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        return anim

    def dismiss(self):
        """收起提示条"""
        self._timer.stop()
        if not self.isVisible():
            return
        self._fade(self._opacity.opacity(), 0.0, self.EXIT_DURATION)
        QTimer.singleShot(self.EXIT_DURATION, self._finish_hide)

    def _finish_hide(self):
        self.setVisible(False)
        self.closed.emit()
