"""
Dayflow - 日期范围选择对话框
用于 Web Dashboard 导出功能
"""
from datetime import date, timedelta

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QDateEdit, QPushButton, QFrame
)
from PySide6.QtCore import Signal, QDate, Qt
from PySide6.QtGui import QFont

from ui.themes import get_theme
from ui.components.motion_dialog import MotionDialog
from ui.components.scale_feedback import FeedbackButton


class DateRangeDialog(MotionDialog):
    """日期范围选择对话框"""
    
    # 信号：选择完成后发出 (start_date, end_date)
    range_selected = Signal(date, date)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择日期范围")
        self.setFixedSize(400, 280)
        self.setModal(True)
        
        self._setup_ui()
        self._connect_signals()
        
        # 默认选择今日
        self._on_preset_changed(0)
    
    def _setup_ui(self):
        """设置界面"""
        t = get_theme()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 标题
        title = QLabel("📊 导出生产力报告")
        title.setFont(QFont("", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 说明
        desc = QLabel("选择要导出的日期范围，将生成 HTML 格式的报告")
        desc.setStyleSheet(f"color: {t.text_muted};")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background: {t.divider};")
        layout.addWidget(line)
        
        # 预设选项
        preset_layout = QHBoxLayout()
        preset_label = QLabel("快速选择:")
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["今日", "昨日", "本周", "上周", "本月", "自定义"])
        self.preset_combo.setMinimumWidth(150)
        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()
        layout.addLayout(preset_layout)
        
        # 日期选择器
        date_layout = QHBoxLayout()
        
        start_layout = QVBoxLayout()
        start_label = QLabel("开始日期")
        start_label.setStyleSheet("color: #888; font-size: 12px;")
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate())
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        start_layout.addWidget(start_label)
        start_layout.addWidget(self.start_date)
        
        end_layout = QVBoxLayout()
        end_label = QLabel("结束日期")
        end_label.setStyleSheet("color: #888; font-size: 12px;")
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        end_layout.addWidget(end_label)
        end_layout.addWidget(self.end_date)
        
        date_layout.addLayout(start_layout)
        date_layout.addSpacing(20)
        date_layout.addLayout(end_layout)
        layout.addLayout(date_layout)
        
        layout.addStretch()
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.reject)
        
        export_btn = FeedbackButton("导出报告")
        export_btn.setMinimumWidth(100)
        # Apple 主 CTA：单一 Action Blue 实心药丸，无渐变
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.accent};
                color: #FFFFFF;
                border: none;
                border-radius: 9999px;
                padding: 9px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {t.accent_hover};
            }}
            QPushButton:focus {{
                border: 2px solid {t.accent_focus};
                padding: 8px 19px;
            }}
        """)
        export_btn.clicked.connect(self._on_export)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)
    
    def _connect_signals(self):
        """连接信号"""
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
    
    def _on_preset_changed(self, index: int):
        """预设选项变化"""
        today = date.today()
        
        if index == 0:  # 今日
            start = end = today
        elif index == 1:  # 昨日
            start = end = today - timedelta(days=1)
        elif index == 2:  # 本周
            start = today - timedelta(days=today.weekday())
            end = today
        elif index == 3:  # 上周
            start = today - timedelta(days=today.weekday() + 7)
            end = start + timedelta(days=6)
        elif index == 4:  # 本月
            start = today.replace(day=1)
            end = today
        else:  # 自定义
            # 不修改日期，让用户自己选择
            self.start_date.setEnabled(True)
            self.end_date.setEnabled(True)
            return
        
        # 更新日期选择器
        self.start_date.setDate(QDate(start.year, start.month, start.day))
        self.end_date.setDate(QDate(end.year, end.month, end.day))
        
        # 非自定义模式下禁用日期选择器
        is_custom = (index == 5)
        self.start_date.setEnabled(is_custom)
        self.end_date.setEnabled(is_custom)
    
    def _on_export(self):
        """导出按钮点击"""
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        
        # 确保开始日期不晚于结束日期
        if start > end:
            start, end = end, start
        
        self.range_selected.emit(start, end)
        self.accept()
    
    def get_date_range(self) -> tuple[date, date]:
        """获取选择的日期范围"""
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        
        if start > end:
            start, end = end, start
        
        return start, end
