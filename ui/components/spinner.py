"""
Dayflow Windows - 加载指示器

用于「操作正在进行中」的等待态。三种可选形态里选了点阵脉冲：
比旋转环轻，比骨架屏安静，适合嵌在按钮里而不抢视觉。

约束（来自 button 规范）：
  · 按钮进入加载态时宽度不能变，否则旁边的东西会跳
  · 文案保持原样，加载指示只做补充 —— 用户需要知道系统听见了
  · 必须能被取消/结束：动画随控件销毁而停
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ui.motion import reduced_motion


class SpinnerDot(QWidget):
    """三点脉冲加载指示器"""

    DOTS = 3
    CYCLE_MS = 900
    DOT_MS = 300

    def __init__(self, parent=None, color: str = "#FFFFFF", size: int = 14):
        super().__init__(parent)
        self._color = QColor(color)
        self._phase = 0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        """开始脉冲。减少动效时不启动 —— 静态点阵仍表明「在处理」。"""
        self._phase = 0
        self.update()
        if reduced_motion():
            return
        self._timer.start(self.DOT_MS)

    def stop(self):
        self._timer.stop()
        self.update()

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def _tick(self):
        self._phase = (self._phase + 1) % self.DOTS
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        w = self.width()
        h = self.height()
        d = max(2.0, min(w, h) / 4.0)
        gap = d * 0.7
        total = self.DOTS * d + (self.DOTS - 1) * gap
        x = (w - total) / 2.0
        y = (h - d) / 2.0

        base = QColor(self._color)
        for i in range(self.DOTS):
            color = QColor(base)
            if reduced_motion():
                # 减少动效：三个点同亮，不做明暗循环
                color.setAlpha(255)
            else:
                # 当前点最亮，相邻点次之，其余淡出
                delta = (i - self._phase) % self.DOTS
                alpha = {0: 255, 1: 150, 2: 70}[delta]
                color.setAlpha(alpha)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x, y, d, d))
            x += d + gap
        painter.end()
