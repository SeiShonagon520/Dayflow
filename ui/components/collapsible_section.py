"""
Dayflow Windows - 可折叠面板容器组件
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel
from PySide6.QtCore import Qt
from ui.themes import get_theme_manager, get_theme


class CollapsibleSection(QWidget):
    """可折叠区域组件"""
    
    def __init__(self, title: str, summary: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._summary = summary
        self._collapsed = True  # 默认折叠
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 标题栏（可点击）
        self.header = QFrame()
        self.header.setCursor(Qt.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 14, 20, 14)
        
        # 折叠图标
        self.toggle_icon = QLabel("▶")
        header_layout.addWidget(self.toggle_icon)
        
        # 标题
        self.title_label = QLabel(self._title)
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # 摘要（折叠时显示）
        self.summary_label = QLabel(self._summary)
        header_layout.addWidget(self.summary_label)
        
        self.main_layout.addWidget(self.header)
        
        # 内容区域
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 0, 20, 16)
        self.content_layout.setSpacing(12)
        self.content.setVisible(False)  # 默认隐藏
        
        self.main_layout.addWidget(self.content)
        
        # 点击事件
        self.header.mousePressEvent = self._on_header_click
    
    def _on_header_click(self, event):
        self.toggle()
    
    def toggle(self):
        """切换折叠状态"""
        self._collapsed = not self._collapsed
        self.content.setVisible(not self._collapsed)
        self.toggle_icon.setText("▼" if not self._collapsed else "▶")
        self.summary_label.setVisible(self._collapsed)
    
    def set_summary(self, summary: str):
        """更新摘要"""
        self._summary = summary
        self.summary_label.setText(summary)
    
    def add_widget(self, widget: QWidget):
        """添加内容组件"""
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout):
        """添加布局"""
        self.content_layout.addLayout(layout)
    
    def apply_theme(self):
        t = get_theme()
        self.header.setStyleSheet(f"""
            QFrame {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 12px;
            }}
            QFrame:hover {{
                background-color: {t.bg_hover};
            }}
        """)
        self.toggle_icon.setStyleSheet(f"""
            font-size: 12px;
            color: {t.text_muted};
            padding-right: 8px;
        """)
        self.title_label.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {t.text_primary};
        """)
        self.summary_label.setStyleSheet(f"""
            font-size: 12px;
            color: {t.text_muted};
        """)
        self.content.setStyleSheet(f"""
            background-color: {t.bg_secondary};
            border: 1px solid {t.border};
            border-top: none;
            border-radius: 0 0 12px 12px;
            margin-top: -12px;
        """)
