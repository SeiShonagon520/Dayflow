"""
Dayflow Windows - 现代侧边栏浮动导航按钮组件
采用全圆角浮动卡片交互与精致高亮视觉
"""
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt
from ui.themes import get_theme_manager, get_theme, with_alpha
from ui.motion import press_feedback, release_feedback
from ui.components.scale_feedback import ScaleFeedbackMixin


class SidebarButton(ScaleFeedbackMixin, QPushButton):
    """侧边栏导航按钮 - 现代浮动圆角交互"""
    
    def __init__(self, text: str, icon_text: str = "", parent=None):
        super().__init__(parent)
        self._init_scale_feedback()
        self.setText(f"  {icon_text}   {text}" if icon_text else f"  {text}")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(42)
        self.apply_theme()
        
        # 监听主题变化
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def paintEvent(self, event):
        if not self._paint_scaled(event):
            super().paintEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            press_feedback(self, 0.97)
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        release_feedback(self, 0.97)
        super().mouseReleaseEvent(event)
    
    def apply_theme(self):
        t = get_theme()
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {t.text_muted};
                border: 1px solid transparent;
                border-radius: 8px;
                text-align: left;
                padding-left: 14px;
                font-size: 13.5px;
                font-weight: 500;
                margin: 2px 10px;
                font-family: "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", sans-serif;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
                color: {t.text_primary};
            }}
            QPushButton:checked {{
                background-color: {t.accent_light};
                color: {t.accent};
                border: 1px solid {with_alpha(t.accent, 0.28)};
                font-weight: 600;
            }}
            QPushButton:focus {{
                border: 2px solid {t.accent_focus};
                background-color: {t.bg_hover};
                color: {t.text_primary};
            }}
            QPushButton:checked:focus {{
                border: 2px solid {t.accent_focus};
                background-color: {t.accent_light};
                color: {t.accent};
            }}
        """)
