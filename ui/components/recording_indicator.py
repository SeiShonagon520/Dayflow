"""
Dayflow Windows - 交互式录制状态胶囊组件 (Recording Indicator Pill)
呈现现代状态药丸形态、微发光脉冲呼吸动画与实时等宽计时
"""
from datetime import datetime
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import QTimer, Qt, Signal
from ui.themes import get_theme_manager, get_theme, with_alpha
from ui.motion import reduced_motion


class RecordingIndicator(QWidget):
    """录制状态胶囊组件 - 交互式药丸形态与呼吸灯"""
    
    clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._paused = False
        self._start_time = None
        self._elapsed_seconds = 0
        self._blink_state = True
        
        self.setCursor(Qt.PointingHandCursor)
        self._setup_ui()
        
        # 脉冲闪烁动画定时器
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        
        # 时长更新定时器
        self._duration_timer = QTimer(self)
        self._duration_timer.timeout.connect(self._update_duration)
        
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(6, 4, 6, 4)
        root_layout.setSpacing(0)
        
        # 药丸胶囊容器
        self.pill_frame = QFrame()
        self.pill_frame.setObjectName("recordingPill")
        pill_layout = QHBoxLayout(self.pill_frame)
        pill_layout.setContentsMargins(12, 6, 14, 6)
        pill_layout.setSpacing(8)
        
        # 状态指示点
        self.dot = QLabel("●")
        self.dot.setAlignment(Qt.AlignCenter)
        pill_layout.addWidget(self.dot)
        
        # 状态文字与时长
        self.status_label = QLabel("未录制")
        self.status_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        pill_layout.addWidget(self.status_label)
        
        root_layout.addWidget(self.pill_frame)
    
    def _format_duration(self, seconds: int) -> str:
        """格式化时长为 HH:MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _update_duration(self):
        """更新录制时长显示"""
        if self._recording and not self._paused and self._start_time:
            elapsed = (datetime.now() - self._start_time).total_seconds()
            self._elapsed_seconds = int(elapsed)
            duration_str = self._format_duration(self._elapsed_seconds)
            self.status_label.setText(f"REC {duration_str}")
    
    def set_recording(self, recording: bool, paused: bool = False):
        """设置录制状态"""
        self._recording = recording
        self._paused = paused
        
        if recording and not paused:
            if self._start_time is None:
                self._start_time = datetime.now()
                self._elapsed_seconds = 0
            
            # 减少动效时不启动呼吸定时器：省掉一个 800ms 的无限循环
            if reduced_motion():
                self._blink_timer.stop()
            else:
                self._blink_timer.start(800)
            self._duration_timer.start(1000)
            
        elif recording and paused:
            self._blink_timer.stop()
            self._duration_timer.stop()
            
        else:
            self._start_time = None
            self._elapsed_seconds = 0
            self._blink_timer.stop()
            self._duration_timer.stop()
            
        self.apply_theme()
    
    def _blink(self):
        """
        录制指示点的呼吸脉冲。

        这是唯一一个「自己会动」的界面元素，所以规矩特别多：
          · 必须有可见的停止方式 —— 点药丸暂停录制即可停止，不是失控循环
          · 减少动效时完全停：改成常亮，不再明暗交替
          · 用缓动渐变而不是硬切，硬切读作闪烁，对光敏用户不友好
        """
        t = get_theme()
        if not (self._recording and not self._paused):
            return

        if reduced_motion():
            # 减少动效：常亮。状态已经由颜色和 REC 文案表达了，
            # 呼吸只是锦上添花，不该成为唯一的「在录制」线索。
            self.dot.setStyleSheet(
                f"color: {t.error}; font-size: 11px; opacity: 1.0;"
            )
            return

        self._blink_state = not self._blink_state
        # 0.45 ~ 1.0 之间渐变，比原来的 0.3 更柔和
        opacity = "1.0" if self._blink_state else "0.45"
        self.dot.setStyleSheet(
            f"color: {t.error}; font-size: 11px; opacity: {opacity};"
        )
    
    def apply_theme(self):
        """根据当前状态与主题更新胶囊视觉样式"""
        t = get_theme()
        
        if self._recording and not self._paused:
            # 录制中 - 状态色实心药丸
            signal = t.error
            duration_str = self._format_duration(self._elapsed_seconds)
            self.status_label.setText(f"REC {duration_str}")
            self.setToolTip("点击暂停录制")
            
        elif self._recording and self._paused:
            # 已暂停 - 警示色
            signal = t.warning
            duration_str = self._format_duration(self._elapsed_seconds)
            self.status_label.setText(f"PAUSED {duration_str}")
            self.setToolTip("点击恢复录制")
            
        else:
            # 空闲未录制 - 静默灰
            signal = t.text_muted
            self.status_label.setText("未录制")
            self.setToolTip("录制已停止")
        
        # Apple 语法：药丸 = 可交互/可状态。用极淡的 signal 底 + 1px signal 边
        self.pill_frame.setStyleSheet(f"""
            QFrame#recordingPill {{
                background-color: {with_alpha(signal, 0.10)};
                border: 1px solid {with_alpha(signal, 0.32)};
                border-radius: 9999px;
            }}
            QFrame#recordingPill:hover {{
                border-color: {signal};
            }}
        """)
        
        self.dot.setStyleSheet(f"""
            color: {signal};
            font-size: 11px;
        """)
        
        self.status_label.setStyleSheet(f"""
            color: {signal};
            font-size: 12px;
            font-weight: 600;
            font-family: "Cascadia Code", "Consolas", "Segoe UI Variable Text", sans-serif;
        """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
    
    def get_elapsed_time(self) -> str:
        """获取当前录制时长字符串"""
        return self._format_duration(self._elapsed_seconds)
