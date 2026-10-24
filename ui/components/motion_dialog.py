"""
Dayflow Windows - 动效对话框基类

给项目里的模态对话框提供统一的出现动效。对话框比按钮重得多，
所以入场稍微慢一点、位移更明显一点 —— 让用户看清「弹出来的是一层新东西」。

用法：
    class MyDialog(MotionDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            ...
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QDialog

from ui.motion import animate_property, duration_ms, easing, reduced_motion


class MotionDialog(QDialog):
    """带入场动效的对话框基类"""

    # 子类可覆盖：入场距离（像素）与时长档位
    enter_distance = 10
    enter_duration = "menu"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enter_anim = None
        self._origin = None

    def showEvent(self, event):
        super().showEvent(event)
        self._play_enter()

    def _play_enter(self):
        """
        播放入场：轻微上移 + 缩放。

        缩放从 0.96 起步而不是 0 —— 从 0 开始会读作「弹出」，
        桌面工具需要的是「浮现」，不是玩具。
        """
        if reduced_motion():
            return

        self._origin = self.pos()

        anim = animate_property(
            self, b"pos",
            self._origin + QPoint(0, self.enter_distance),
            self._origin,
            duration=self.enter_duration,
            ease="out_quart",
        )
        self._enter_anim = anim

    def keyPressEvent(self, event):
        # Esc 关闭是所有对话框的默认预期，顺手补上
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
