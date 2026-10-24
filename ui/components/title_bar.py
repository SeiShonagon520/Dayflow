"""
Dayflow Windows - 自定义标题栏组件
支持无边框拖拽、最小化到托盘、最小化、最大化、关闭及主题响应
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from ui.themes import get_theme_manager, get_theme
from ui.motion import press_feedback, release_feedback
from ui.components.scale_feedback import ScaleFeedbackMixin


class TitleBarButton(ScaleFeedbackMixin, QPushButton):
    """标题栏按钮"""
    
    def __init__(self, text: str, hover_color: str = None, parent=None):
        super().__init__(parent)
        self._init_scale_feedback()
        self.setText(text)
        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._hover_color = hover_color
        self._is_close = False
        self.apply_theme()
    
    def paintEvent(self, event):
        if not self._paint_scaled(event):
            super().paintEvent(event)
    
    def mousePressEvent(self, event):
        # 标题栏按钮是高频点击目标，按下反馈要立刻
        if event.button() == Qt.LeftButton:
            press_feedback(self, 0.92)
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        release_feedback(self, 0.92)
        super().mouseReleaseEvent(event)
    
    def set_close_button(self, is_close: bool):
        """设置为关闭按钮样式"""
        self._is_close = is_close
        self._hover_color = "#E81123" if is_close else None
        self.apply_theme()
    
    def apply_theme(self):
        t = get_theme()
        # 关闭按钮用系统红，其余用中性 hover —— 悬停底色不硬编码
        hover_bg = self._hover_color or t.bg_hover
        hover_text = "#FFFFFF" if self._is_close else t.text_primary
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {t.text_secondary};
                font-size: 12px;
                font-family: "Segoe MDL2 Assets", "Segoe UI Symbol", sans-serif;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                color: {hover_text};
            }}
            QPushButton:focus {{
                background-color: {t.bg_hover};
                color: {hover_text};
                border: 2px solid {t.accent_focus};
                border-radius: 6px;
            }}
        """)


class CustomTitleBar(QWidget):
    """自定义标题栏 - Windows 11 / VS Code 风格"""
    
    minimize_to_tray = Signal()
    minimize_window = Signal()
    maximize_window = Signal()
    close_window = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self._dragging = False
        self._drag_pos = None
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        
        # 左侧：图标和标题
        self.icon_label = QLabel("⏱️")
        self.icon_label.setFixedWidth(24)
        layout.addWidget(self.icon_label)
        
        self.title_label = QLabel("Dayflow")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # 右侧：窗口控制按钮
        # 最小化到托盘
        self.tray_btn = TitleBarButton("↓")
        self.tray_btn.setToolTip("最小化到托盘")
        self.tray_btn.clicked.connect(self.minimize_to_tray.emit)
        layout.addWidget(self.tray_btn)
        
        # 最小化
        self.min_btn = TitleBarButton("─")
        self.min_btn.setToolTip("最小化")
        self.min_btn.clicked.connect(self.minimize_window.emit)
        layout.addWidget(self.min_btn)
        
        # 最大化/还原
        self.max_btn = TitleBarButton("□")
        self.max_btn.setToolTip("最大化")
        self.max_btn.clicked.connect(self.maximize_window.emit)
        layout.addWidget(self.max_btn)
        
        # 关闭
        self.close_btn = TitleBarButton("×")
        self.close_btn.set_close_button(True)
        self.close_btn.setToolTip("关闭")
        self.close_btn.clicked.connect(self.close_window.emit)
        layout.addWidget(self.close_btn)
    
    def update_maximize_button(self, is_maximized: bool):
        """更新最大化按钮图标"""
        if is_maximized:
            self.max_btn.setText("❐")
            self.max_btn.setToolTip("还原")
        else:
            self.max_btn.setText("□")
            self.max_btn.setToolTip("最大化")
    
    def apply_theme(self):
        t = get_theme()
        self.setStyleSheet(f"background-color: {t.bg_secondary};")
        self.icon_label.setStyleSheet(f"font-size: 14px;")
        self.title_label.setStyleSheet(f"""
            color: {t.text_secondary};
            font-size: 12px;
            font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
            padding-left: 4px;
        """)
        # 更新按钮主题
        self.tray_btn.apply_theme()
        self.min_btn.apply_theme()
        self.max_btn.apply_theme()
        self.close_btn.apply_theme()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if self._dragging and self._drag_pos:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._drag_pos = None
    
    def mouseDoubleClickEvent(self, event):
        """双击最大化/还原"""
        if event.button() == Qt.LeftButton:
            self.maximize_window.emit()
