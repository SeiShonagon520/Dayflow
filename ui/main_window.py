"""
Dayflow Windows - 主窗口
现代化 Windows 11 风格界面
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame,
    QLineEdit, QMessageBox, QSystemTrayIcon, QMenu,
    QApplication, QSizePolicy, QSpacerItem, QFileDialog,
    QScrollArea, QProgressBar, QComboBox, QSpinBox, QTextBrowser,
    QDialog, QProgressDialog, QCheckBox
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QSize
from PySide6.QtGui import QIcon, QAction, QFont, QColor, QPalette

import config
from ui.timeline_view import TimelineView
from ui.stats_view import StatsPanel
from ui.daily_report_view import DailyReportView
from ui.themes import get_theme_manager, get_theme
from core.types import ActivityCard
from database.storage import StorageManager

logger = logging.getLogger(__name__)


class DailyReportDialog(QDialog):
    """日报展示对话框"""

    def __init__(self, date_str: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"📋 工作日报 - {date_str}")
        self.setMinimumSize(600, 500)
        self.resize(700, 600)
        self.setModal(True)
        self._content = content
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 内容区
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setMarkdown(self._content)
        layout.addWidget(self.text_browser)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        copy_btn = QPushButton("📋 复制到剪贴板")
        copy_btn.setFixedHeight(34)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(copy_btn)

        export_btn = QPushButton("💾 导出为文件")
        export_btn.setFixedHeight(34)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_to_file)
        btn_layout.addWidget(export_btn)

        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(34)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _copy_to_clipboard(self):
        QApplication.clipboard().setText(self._content)
        QMessageBox.information(self, "成功", "日报内容已复制到剪贴板")

    def _export_to_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出日报", f"日报_{self.windowTitle().split(' - ')[-1]}.md",
            "Markdown 文件 (*.md);;文本文件 (*.txt)"
        )
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self._content)
            QMessageBox.information(self, "成功", f"日报已导出到：{file_path}")


class TitleBarButton(QPushButton):
    """标题栏按钮"""
    
    def __init__(self, text: str, hover_color: str = None, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self._hover_color = hover_color or "#3d3d3d"
        self._is_close = False
        self.apply_theme()
    
    def set_close_button(self, is_close: bool):
        """设置为关闭按钮样式"""
        self._is_close = is_close
        self._hover_color = "#e81123" if is_close else "#3d3d3d"
        self.apply_theme()
    
    def apply_theme(self):
        t = get_theme()
        hover_bg = self._hover_color
        hover_text = "white" if self._is_close else t.text_primary
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
        """)


class CustomTitleBar(QWidget):
    """自定义标题栏 - VS Code 风格"""
    
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


class SidebarButton(QPushButton):
    """侧边栏按钮"""
    
    def __init__(self, text: str, icon_text: str = "", parent=None):
        super().__init__(parent)
        self.setText(f"  {icon_text}  {text}" if icon_text else f"  {text}")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)
        self.apply_theme()
        
        # 监听主题变化
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def apply_theme(self):
        t = get_theme()
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {t.text_muted};
                border: none;
                border-radius: 0px 10px 10px 0px;
                text-align: left;
                padding-left: 14px;
                font-size: 14px;
                font-weight: 500;
                margin: 2px 8px 2px 0px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
                color: {t.text_primary};
            }}
            QPushButton:checked {{
                background-color: {t.accent_light};
                color: {t.accent};
                border-left: 3px solid {t.accent};
                padding-left: 11px;
                font-weight: 600;
            }}
        """)


class RecordingIndicator(QWidget):
    """录制状态指示器 - 带实时时长显示"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._paused = False
        self._start_time = None
        self._elapsed_seconds = 0
        self._setup_ui()
        get_theme_manager().theme_changed.connect(self._apply_idle_theme)
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # 指示点
        self.dot = QLabel("●")
        layout.addWidget(self.dot)
        
        # 状态文字
        self.status_label = QLabel("未录制")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # 闪烁动画（脉冲效果）
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_state = True
        
        # 时长更新定时器
        self._duration_timer = QTimer(self)
        self._duration_timer.timeout.connect(self._update_duration)
        
        self._apply_idle_theme()
    
    def _format_duration(self, seconds: int) -> str:
        """格式化时长为 HH:MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _update_duration(self):
        """更新录制时长显示"""
        if self._recording and not self._paused and self._start_time:
            from datetime import datetime
            elapsed = (datetime.now() - self._start_time).total_seconds()
            self._elapsed_seconds = int(elapsed)
            duration_str = self._format_duration(self._elapsed_seconds)
            self.status_label.setText(f"录制中 {duration_str}")
    
    def _apply_idle_theme(self):
        if not self._recording:
            t = get_theme()
            self.dot.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
            self.status_label.setStyleSheet(f"color: {t.text_muted}; font-size: 12px;")
    
    def set_recording(self, recording: bool, paused: bool = False):
        from datetime import datetime
        
        self._recording = recording
        self._paused = paused
        t = get_theme()
        
        if recording and not paused:
            # 开始录制
            if self._start_time is None:
                self._start_time = datetime.now()
                self._elapsed_seconds = 0
            
            self.dot.setStyleSheet(f"color: {t.error}; font-size: 10px;")
            self.status_label.setText("录制中 00:00:00")
            self.status_label.setStyleSheet(f"color: {t.error}; font-size: 12px; font-weight: 600;")
            self._blink_timer.start(800)
            self._duration_timer.start(1000)
            
        elif recording and paused:
            # 暂停
            duration_str = self._format_duration(self._elapsed_seconds)
            self.dot.setStyleSheet(f"color: {t.warning}; font-size: 10px;")
            self.status_label.setText(f"已暂停 {duration_str}")
            self.status_label.setStyleSheet(f"color: {t.warning}; font-size: 12px;")
            self._blink_timer.stop()
            self._duration_timer.stop()
            
        else:
            # 停止
            self._start_time = None
            self._elapsed_seconds = 0
            self.dot.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
            self.status_label.setText("未录制")
            self.status_label.setStyleSheet(f"color: {t.text_muted}; font-size: 12px;")
            self._blink_timer.stop()
            self._duration_timer.stop()
    
    def _blink(self):
        """脉冲动画"""
        t = get_theme()
        self._blink_state = not self._blink_state
        if self._blink_state:
            self.dot.setStyleSheet(f"color: {t.error}; font-size: 10px;")
        else:
            self.dot.setStyleSheet(f"color: {t.error}; font-size: 10px; opacity: 0.3;")
    
    def get_elapsed_time(self) -> str:
        """获取当前录制时长字符串"""
        return self._format_duration(self._elapsed_seconds)


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


class SettingsPanel(QWidget):
    """设置面板"""
    
    api_key_saved = Signal(str)
    email_success = Signal()  # 邮件发送成功信号
    email_error = Signal(str)  # 邮件发送失败信号
    
    def __init__(self, storage: StorageManager, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._frames = []  # 存储需要主题化的 frame
        self._titles = []  # 存储标题
        self._descs = []   # 存储描述文字
        self._setup_ui()
        self._load_settings()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
        
        # 连接邮件信号
        self.email_success.connect(self._show_email_success)
        self.email_error.connect(self._show_email_error)
    
    def _create_card(self, layout) -> QFrame:
        """创建设置卡片"""
        frame = QFrame()
        frame.setObjectName("settingsCard")
        self._frames.append(frame)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(20, 16, 20, 16)
        frame_layout.setSpacing(10)
        layout.addWidget(frame)
        return frame, frame_layout
    
    def _create_title(self, text: str, layout) -> QLabel:
        """创建卡片标题"""
        label = QLabel(text)
        label.setObjectName("cardTitle")
        label.setMinimumHeight(24)
        self._titles.append(label)
        layout.addWidget(label)
        return label
    
    def _create_desc(self, text: str, layout) -> QLabel:
        """创建描述文字"""
        label = QLabel(text)
        label.setObjectName("cardDesc")
        label.setWordWrap(True)
        label.setMinimumHeight(20)
        self._descs.append(label)
        layout.addWidget(label)
        return label
    
    def _setup_ui(self):
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建滚动区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        
        # 滚动区域内容
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(20)  # 增加卡片间距
        
        # 页面标题
        self.page_title = QLabel("⚙️ 设置")
        self.page_title.setMinimumHeight(40)
        layout.addWidget(self.page_title)
        
        # === API 设置 ===
        api_frame, api_layout = self._create_card(layout)
        self._create_title("🔑 API 设置", api_layout)
        
        api_desc = QLabel("支持 OpenAI 兼容接口（心流API、OpenAI、DeepSeek、本地模型等）")
        api_desc.setObjectName("cardDesc")
        api_desc.setWordWrap(True)
        self._descs.append(api_desc)
        api_layout.addWidget(api_desc)
        
        # API URL 输入框
        api_url_label = QLabel("API 地址")
        api_url_label.setObjectName("cardDesc")
        self._descs.append(api_url_label)
        api_layout.addWidget(api_url_label)
        
        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("https://api.openai.com/v1")
        self.api_url_input.setMinimumHeight(40)
        api_layout.addWidget(self.api_url_input)
        
        # API Key 输入框
        api_key_label = QLabel("API Key")
        api_key_label.setObjectName("cardDesc")
        self._descs.append(api_key_label)
        api_layout.addWidget(api_key_label)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setMinimumHeight(40)
        api_layout.addWidget(self.api_key_input)
        
        # 模型名称输入框
        model_label = QLabel("模型名称（需支持视觉）")
        model_label.setObjectName("cardDesc")
        self._descs.append(model_label)
        api_layout.addWidget(model_label)
        
        self.api_model_input = QLineEdit()
        self.api_model_input.setPlaceholderText("gpt-4o / qwen-vl-plus / deepseek-chat")
        self.api_model_input.setMinimumHeight(40)
        api_layout.addWidget(self.api_model_input)
        
        # 按钮行
        key_row = QHBoxLayout()
        key_row.setSpacing(10)
        
        self.save_btn = QPushButton("保存配置")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setFixedSize(100, 40)
        self.save_btn.clicked.connect(self._save_api_config)
        key_row.addWidget(self.save_btn)
        
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setCursor(Qt.PointingHandCursor)
        self.test_btn.setFixedSize(100, 40)
        self.test_btn.clicked.connect(self._test_connection)
        key_row.addWidget(self.test_btn)
        
        key_row.addStretch()
        api_layout.addLayout(key_row)
        
        # 测试结果
        self.test_result_label = QLabel("")
        self.test_result_label.setWordWrap(True)
        self.test_result_label.setMinimumHeight(24)
        self.test_result_label.hide()
        api_layout.addWidget(self.test_result_label)
        
        # === 外观 + 录制设置（合并为一行两列）===
        settings_row = QHBoxLayout()
        settings_row.setSpacing(16)
        
        # 外观设置
        theme_frame = QFrame()
        theme_frame.setObjectName("settingsCard")
        self._frames.append(theme_frame)
        theme_layout = QVBoxLayout(theme_frame)
        theme_layout.setContentsMargins(20, 16, 20, 16)
        theme_layout.setSpacing(10)
        
        self._create_title("🎨 外观", theme_layout)
        
        theme_content = QHBoxLayout()
        self.theme_label = QLabel("主题模式")
        self.theme_label.setObjectName("cardDesc")
        self._descs.append(self.theme_label)
        theme_content.addWidget(self.theme_label)
        theme_content.addStretch()
        
        self.theme_toggle = QPushButton("🌙 暗色")
        self.theme_toggle.setCursor(Qt.PointingHandCursor)
        self.theme_toggle.setFixedSize(90, 34)
        self.theme_toggle.clicked.connect(self._toggle_theme)
        theme_content.addWidget(self.theme_toggle)
        theme_layout.addLayout(theme_content)
        
        settings_row.addWidget(theme_frame)
        
        # 录制设置
        record_frame = QFrame()
        record_frame.setObjectName("settingsCard")
        self._frames.append(record_frame)
        record_layout = QVBoxLayout(record_frame)
        record_layout.setContentsMargins(20, 16, 20, 16)
        record_layout.setSpacing(10)
        
        self._create_title("🎬 录制", record_layout)
        record_desc = QLabel(f"帧率: {config.RECORD_FPS} FPS | 切片: {config.CHUNK_DURATION_SECONDS}秒")
        record_desc.setObjectName("cardDesc")
        self._descs.append(record_desc)
        record_layout.addWidget(record_desc)

        monitor_row = QHBoxLayout()
        monitor_label = QLabel("录制显示器")
        monitor_label.setObjectName("cardDesc")
        self._descs.append(monitor_label)
        monitor_row.addWidget(monitor_label)
        monitor_row.addStretch()

        self.monitor_combo = QComboBox()
        self.monitor_combo.setMinimumHeight(34)
        self.monitor_combo.setMinimumWidth(150)
        self._populate_monitor_options()
        monitor_row.addWidget(self.monitor_combo)
        record_layout.addLayout(monitor_row)

        # 缓存上限
        cache_row = QHBoxLayout()
        cache_label = QLabel("缓存上限")
        cache_label.setObjectName("cardDesc")
        self._descs.append(cache_label)
        cache_row.addWidget(cache_label)
        cache_row.addStretch()

        self.cache_limit_spin = QSpinBox()
        self.cache_limit_spin.setRange(1, 100)
        self.cache_limit_spin.setValue(config.CHUNKS_MAX_SIZE_GB)
        self.cache_limit_spin.setSuffix(" GB")
        self.cache_limit_spin.setMinimumHeight(34)
        self.cache_limit_spin.setMinimumWidth(100)
        cache_row.addWidget(self.cache_limit_spin)
        record_layout.addLayout(cache_row)

        # 自定义录制路径
        path_row = QHBoxLayout()
        path_label = QLabel("录制路径")
        path_label.setObjectName("cardDesc")
        self._descs.append(path_label)
        path_row.addWidget(path_label)

        self.custom_path_input = QLineEdit()
        self.custom_path_input.setPlaceholderText("留空使用默认路径")
        self.custom_path_input.setReadOnly(True)
        self.custom_path_input.setMinimumHeight(34)
        path_row.addWidget(self.custom_path_input)

        self.path_browse_btn = QPushButton("浏览...")
        self.path_browse_btn.setCursor(Qt.PointingHandCursor)
        self.path_browse_btn.setFixedHeight(34)
        self.path_browse_btn.clicked.connect(self._browse_chunks_dir)
        path_row.addWidget(self.path_browse_btn)
        record_layout.addLayout(path_row)

        # 空闲自动暂停
        idle_row = QHBoxLayout()
        self.idle_pause_check = QCheckBox("空闲自动暂停")
        self.idle_pause_check.setChecked(config.IDLE_PAUSE_ENABLED)
        self.idle_pause_check.stateChanged.connect(self._on_idle_pause_toggled)
        idle_row.addWidget(self.idle_pause_check)
        idle_row.addStretch()

        self.idle_timeout_spin = QSpinBox()
        self.idle_timeout_spin.setRange(1, 120)
        self.idle_timeout_spin.setValue(config.IDLE_PAUSE_TIMEOUT_SECONDS // 60)
        self.idle_timeout_spin.setSuffix(" 分钟")
        self.idle_timeout_spin.setMinimumHeight(34)
        self.idle_timeout_spin.setMinimumWidth(100)
        self.idle_timeout_spin.setEnabled(config.IDLE_PAUSE_ENABLED)
        idle_row.addWidget(self.idle_timeout_spin)
        record_layout.addLayout(idle_row)

        self.monitor_save_btn = QPushButton("保存录制设置")
        self.monitor_save_btn.setCursor(Qt.PointingHandCursor)
        self.monitor_save_btn.setFixedHeight(36)
        self.monitor_save_btn.clicked.connect(self._save_recording_settings)
        record_layout.addWidget(self.monitor_save_btn)
        
        settings_row.addWidget(record_frame)
        layout.addLayout(settings_row)
        
        # === 数据管理 ===
        data_frame, data_layout = self._create_card(layout)
        self._create_title("💾 数据管理", data_layout)
        self._create_desc("导出或导入您的所有活动数据", data_layout)
        
        data_row = QHBoxLayout()
        data_row.setSpacing(10)
        
        self.export_btn = QPushButton("📤 导出数据")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setFixedHeight(38)
        self.export_btn.clicked.connect(self._export_data)
        data_row.addWidget(self.export_btn)
        
        self.import_btn = QPushButton("📥 导入数据")
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.setFixedHeight(38)
        self.import_btn.clicked.connect(self._import_data)
        data_row.addWidget(self.import_btn)
        
        self.dashboard_btn = QPushButton("📊 导出仪表盘")
        self.dashboard_btn.setCursor(Qt.PointingHandCursor)
        self.dashboard_btn.setFixedHeight(38)
        self.dashboard_btn.clicked.connect(self._export_dashboard)
        data_row.addWidget(self.dashboard_btn)
        
        data_row.addStretch()
        data_layout.addLayout(data_row)
        
        # === 邮件推送设置 ===
        email_frame, email_layout = self._create_card(layout)
        self._create_title("📧 邮件推送", email_layout)
        self._create_desc("自动发送效率报告到您的邮箱", email_layout)
        
        # 启用开关行
        enable_row = QHBoxLayout()
        self.email_enable_label = QLabel("启用推送")
        self.email_enable_label.setObjectName("cardDesc")
        self._descs.append(self.email_enable_label)
        enable_row.addWidget(self.email_enable_label)
        enable_row.addStretch()
        
        self.email_enable_btn = QPushButton("已关闭")
        self.email_enable_btn.setCheckable(True)
        self.email_enable_btn.setCursor(Qt.PointingHandCursor)
        self.email_enable_btn.setFixedSize(72, 30)
        self.email_enable_btn.clicked.connect(self._toggle_email)
        enable_row.addWidget(self.email_enable_btn)
        email_layout.addLayout(enable_row)
        
        # 发送时间配置
        send_time_label = QLabel("发送时间（可配置多个，用逗号分隔，如 12:00,22:00）")
        send_time_label.setObjectName("inputLabel")
        self._descs.append(send_time_label)
        email_layout.addWidget(send_time_label)
        
        self.email_send_times_input = QLineEdit()
        self.email_send_times_input.setPlaceholderText("12:00,22:00")
        self.email_send_times_input.setMinimumHeight(40)
        email_layout.addWidget(self.email_send_times_input)
        
        # 邮箱输入区域（使用网格布局更紧凑）
        email_grid = QVBoxLayout()
        email_grid.setSpacing(8)
        
        # 发送邮箱
        sender_label = QLabel("发送邮箱")
        sender_label.setObjectName("inputLabel")
        self._descs.append(sender_label)
        email_grid.addWidget(sender_label)
        
        self.email_sender_input = QLineEdit()
        self.email_sender_input.setPlaceholderText("123456789@qq.com")
        self.email_sender_input.setMinimumHeight(40)
        email_grid.addWidget(self.email_sender_input)
        
        # 授权码
        auth_label = QLabel("授权码（在 QQ 邮箱设置中获取，非密码）")
        auth_label.setObjectName("inputLabel")
        self._descs.append(auth_label)
        email_grid.addWidget(auth_label)
        
        self.email_auth_input = QLineEdit()
        self.email_auth_input.setPlaceholderText("16位授权码")
        self.email_auth_input.setEchoMode(QLineEdit.Password)
        self.email_auth_input.setMinimumHeight(40)
        email_grid.addWidget(self.email_auth_input)
        
        # 接收邮箱
        receiver_label = QLabel("接收邮箱")
        receiver_label.setObjectName("inputLabel")
        self._descs.append(receiver_label)
        email_grid.addWidget(receiver_label)
        
        self.email_receiver_input = QLineEdit()
        self.email_receiver_input.setPlaceholderText("your_email@qq.com")
        self.email_receiver_input.setMinimumHeight(40)
        email_grid.addWidget(self.email_receiver_input)
        
        email_layout.addLayout(email_grid)
        
        # 按钮行
        email_btn_row = QHBoxLayout()
        email_btn_row.setSpacing(10)
        
        self.email_save_btn = QPushButton("保存配置")
        self.email_save_btn.setCursor(Qt.PointingHandCursor)
        self.email_save_btn.setFixedHeight(38)
        self.email_save_btn.clicked.connect(self._save_email_config)
        email_btn_row.addWidget(self.email_save_btn)
        
        self.email_test_btn = QPushButton("📨 测试发送")
        self.email_test_btn.setCursor(Qt.PointingHandCursor)
        self.email_test_btn.setFixedHeight(38)
        self.email_test_btn.clicked.connect(self._send_test_email)
        email_btn_row.addWidget(self.email_test_btn)
        
        email_btn_row.addStretch()
        email_layout.addLayout(email_btn_row)
        
        # 测试结果
        self.email_result_label = QLabel("")
        self.email_result_label.setWordWrap(True)
        self.email_result_label.setMinimumHeight(20)
        self.email_result_label.hide()
        email_layout.addWidget(self.email_result_label)
        
        # === 开机启动 ===
        autostart_frame, autostart_layout = self._create_card(layout)
        self._create_title("🚀 开机启动", autostart_layout)
        
        autostart_desc = QLabel("开机时自动启动 Dayflow 并最小化到系统托盘")
        autostart_desc.setObjectName("cardDesc")
        self._descs.append(autostart_desc)
        autostart_layout.addWidget(autostart_desc)
        
        # 开机启动按钮
        autostart_btn_row = QHBoxLayout()
        autostart_btn_row.setSpacing(10)
        
        self.autostart_btn = QPushButton("⚪ 未启用")
        self.autostart_btn.setCursor(Qt.PointingHandCursor)
        self.autostart_btn.setFixedHeight(38)
        self.autostart_btn.setCheckable(True)
        self.autostart_btn.clicked.connect(self._toggle_autostart)
        autostart_btn_row.addWidget(self.autostart_btn)
        
        self.autostart_status = QLabel("")
        self.autostart_status.setObjectName("cardDesc")
        self._descs.append(self.autostart_status)
        autostart_btn_row.addWidget(self.autostart_status)
        
        autostart_btn_row.addStretch()
        autostart_layout.addLayout(autostart_btn_row)
        
        # 初始化自启动状态
        self._init_autostart_status()
        
        # === 软件更新 ===
        update_frame, update_layout = self._create_card(layout)
        self._create_title("🔄 软件更新", update_layout)
        self.update_version_label = QLabel(f"当前版本: v{config.VERSION}")
        self.update_version_label.setObjectName("cardDesc")
        self._descs.append(self.update_version_label)
        update_layout.addWidget(self.update_version_label)
        
        # 更新按钮行
        update_btn_row = QHBoxLayout()
        update_btn_row.setSpacing(10)
        
        self.check_update_btn = QPushButton("🔍 检查更新")
        self.check_update_btn.setCursor(Qt.PointingHandCursor)
        self.check_update_btn.setFixedHeight(38)
        self.check_update_btn.clicked.connect(self._check_update)
        update_btn_row.addWidget(self.check_update_btn)
        
        self.update_status_label = QLabel("")
        self.update_status_label.setObjectName("cardDesc")
        self._descs.append(self.update_status_label)
        update_btn_row.addWidget(self.update_status_label)
        
        update_btn_row.addStretch()
        update_layout.addLayout(update_btn_row)
        
        # 下载进度条（初始隐藏）
        self.update_progress = QProgressBar()
        self.update_progress.setMinimum(0)
        self.update_progress.setMaximum(100)
        self.update_progress.setFixedHeight(20)
        self.update_progress.hide()
        update_layout.addWidget(self.update_progress)
        
        # 更新操作按钮（初始隐藏）
        self.update_action_row = QHBoxLayout()
        self.update_action_row.setSpacing(10)
        
        self.download_btn = QPushButton("⬇️ 下载更新")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setFixedHeight(38)
        self.download_btn.clicked.connect(self._start_download)
        self.download_btn.hide()
        self.update_action_row.addWidget(self.download_btn)
        
        self.install_btn = QPushButton("🚀 立即安装")
        self.install_btn.setCursor(Qt.PointingHandCursor)
        self.install_btn.setFixedHeight(38)
        self.install_btn.clicked.connect(self._install_update)
        self.install_btn.hide()
        self.update_action_row.addWidget(self.install_btn)
        
        self.update_action_row.addStretch()
        update_layout.addLayout(self.update_action_row)
        
        # === 日志查看 ===
        log_frame, log_layout = self._create_card(layout)
        self._create_title("📋 运行日志", log_layout)
        
        log_desc = QLabel("查看应用运行日志，便于排查问题")
        log_desc.setObjectName("cardDesc")
        self._descs.append(log_desc)
        log_layout.addWidget(log_desc)
        
        # 日志按钮行
        log_btn_row = QHBoxLayout()
        log_btn_row.setSpacing(10)
        
        self.view_log_btn = QPushButton("📄 查看日志")
        self.view_log_btn.setCursor(Qt.PointingHandCursor)
        self.view_log_btn.setFixedHeight(38)
        self.view_log_btn.clicked.connect(self._toggle_log_view)
        log_btn_row.addWidget(self.view_log_btn)
        
        self.refresh_log_btn = QPushButton("🔄 刷新")
        self.refresh_log_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_log_btn.setFixedHeight(38)
        self.refresh_log_btn.clicked.connect(self._refresh_log)
        self.refresh_log_btn.hide()
        log_btn_row.addWidget(self.refresh_log_btn)
        
        self.open_log_folder_btn = QPushButton("📂 打开日志目录")
        self.open_log_folder_btn.setCursor(Qt.PointingHandCursor)
        self.open_log_folder_btn.setFixedHeight(38)
        self.open_log_folder_btn.clicked.connect(self._open_log_folder)
        log_btn_row.addWidget(self.open_log_folder_btn)
        
        log_btn_row.addStretch()
        log_layout.addLayout(log_btn_row)
        
        # 日志显示区域（初始隐藏）
        from PySide6.QtWidgets import QTextEdit
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(300)
        self.log_text.hide()
        self.log_text.setPlaceholderText("点击「查看日志」加载日志内容...")
        log_layout.addWidget(self.log_text)
        
        # === 关于 ===
        about_frame, about_layout = self._create_card(layout)
        self._create_title("ℹ️ 关于 Dayflow", about_layout)
        
        about_text = QLabel(f"Windows 版本 {config.VERSION}\n智能时间追踪与生产力分析工具")
        about_text.setObjectName("cardDesc")
        about_text.setWordWrap(True)
        self._descs.append(about_text)
        about_layout.addWidget(about_text)
        
        # 底部留白
        layout.addSpacing(20)
        
        # 设置滚动区域
        self.scroll.setWidget(scroll_content)
        main_layout.addWidget(self.scroll)
    
    def apply_theme(self):
        """应用主题"""
        t = get_theme()
        
        # 滚动区域
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {t.bg_primary};
                border: none;
            }}
            QScrollBar:vertical {{
                width: 8px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {t.scrollbar};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t.scrollbar_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        
        # 页面标题 - 28px, 700
        self.page_title.setStyleSheet(f"""
            font-size: 28px;
            font-weight: 700;
            color: {t.text_primary};
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            padding: 4px 0;
        """)
        
        # 所有卡片
        for frame in self._frames:
            frame.setStyleSheet(f"""
                QFrame#settingsCard {{
                    background-color: {t.bg_secondary};
                    border: 1px solid {t.border};
                    border-radius: 12px;
                }}
            """)
        
        # 标题
        for title in self._titles:
            title.setStyleSheet(f"""
                font-size: 15px;
                font-weight: 600;
                color: {t.text_primary};
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                padding: 2px 0;
            """)
        
        # 描述文字
        for desc in self._descs:
            desc.setStyleSheet(f"""
                font-size: 13px;
                color: {t.text_secondary};
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                padding: 2px 0;
            """)
        
        # API 输入框样式
        api_input_style = f"""
            QLineEdit {{
                background-color: {t.bg_tertiary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
                color: {t.text_primary};
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QLineEdit:focus {{
                border-color: {t.accent};
            }}
        """
        self.api_url_input.setStyleSheet(api_input_style)
        self.api_key_input.setStyleSheet(api_input_style)
        self.api_model_input.setStyleSheet(api_input_style)
        
        # 主要按钮（保存）
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.accent};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {t.accent_hover};
            }}
        """)
        
        # 测试按钮
        self.test_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.success};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:disabled {{
                background-color: {t.text_muted};
            }}
        """)
        
        # 主题切换按钮
        self.theme_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 8px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
            }}
        """)

        combo_style = f"""
            QComboBox {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QComboBox:focus {{
                border-color: {t.accent};
            }}
            QComboBox QAbstractItemView {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                selection-background-color: {t.accent};
            }}
        """
        if hasattr(self, 'monitor_combo'):
            self.monitor_combo.setStyleSheet(combo_style)
        
        # 数据管理按钮
        data_btn_style = f"""
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 8px;
                font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
                border-color: {t.accent};
            }}
        """
        self.export_btn.setStyleSheet(data_btn_style)
        self.import_btn.setStyleSheet(data_btn_style)
        self.dashboard_btn.setStyleSheet(data_btn_style)
        if hasattr(self, 'monitor_save_btn'):
            self.monitor_save_btn.setStyleSheet(data_btn_style)
        
        # 邮件输入框样式
        email_input_style = f"""
            QLineEdit {{
                background-color: {t.bg_tertiary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
                color: {t.text_primary};
            }}
            QLineEdit:focus {{
                border-color: {t.accent};
            }}
        """
        self.email_sender_input.setStyleSheet(email_input_style)
        self.email_auth_input.setStyleSheet(email_input_style)
        self.email_receiver_input.setStyleSheet(email_input_style)
        
        # 邮件启用按钮
        if self.email_enable_btn.isChecked():
            self.email_enable_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.success};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 600;
                }}
            """)
        else:
            self.email_enable_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.bg_tertiary};
                    color: {t.text_muted};
                    border: 1px solid {t.border};
                    border-radius: 6px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {t.bg_hover};
                }}
            """)
        
        # 邮件按钮
        self.email_save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.accent};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: {t.accent_hover};
            }}
        """)
        self.email_test_btn.setStyleSheet(data_btn_style)
        
        # 日志按钮样式
        log_btn_style = f"""
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 8px;
                font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
                border-color: {t.accent};
            }}
        """
        self.view_log_btn.setStyleSheet(log_btn_style)
        self.refresh_log_btn.setStyleSheet(log_btn_style)
        self.open_log_folder_btn.setStyleSheet(log_btn_style)
        
        # 日志文本框样式
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 12px;
                font-size: 12px;
                font-family: "Consolas", "Monaco", "Microsoft YaHei", monospace;
                line-height: 1.5;
            }}
        """)

    def _browse_chunks_dir(self):
        """浏览并选择录制视频存放路径"""
        current_dir = self.custom_path_input.text() or str(config.CHUNKS_DIR)
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择录制视频存放路径", current_dir
        )
        if dir_path:
            self.custom_path_input.setText(dir_path)

    def _populate_monitor_options(self):
        """填充显示器选项。"""
        self.monitor_combo.clear()
        self.monitor_combo.addItem("全部屏幕", -1)
        screens = QApplication.screens()
        if not screens:
            return

        for idx, screen in enumerate(screens):
            geom = screen.geometry()
            label = f"显示器 {idx + 1} ({geom.width()}x{geom.height()})"
            self.monitor_combo.addItem(label, idx)

    def _save_recording_settings(self):
        """保存录制相关配置。"""
        output_idx = self.monitor_combo.currentData()
        if output_idx is None:
            output_idx = 0
        self.storage.set_setting("record_output_idx", str(output_idx))

        # 保存缓存上限
        cache_limit = self.cache_limit_spin.value()
        self.storage.set_setting("chunks_max_size_gb", str(cache_limit))
        config.CHUNKS_MAX_SIZE_GB = cache_limit

        # 保存自定义录制路径
        new_path = self.custom_path_input.text().strip()
        old_path_setting = self.storage.get_setting("custom_chunks_dir", "")

        if new_path != old_path_setting:
            self.storage.set_setting("custom_chunks_dir", new_path)

            # 路径变更时迁移文件
            old_dir = config.CHUNKS_DIR
            new_dir = Path(new_path) if new_path else config.APP_DATA_DIR / "chunks"

            if old_dir.exists() and old_dir != new_dir:
                new_dir.mkdir(parents=True, exist_ok=True)
                try:
                    for f in old_dir.iterdir():
                        if f.is_file():
                            dest = new_dir / f.name
                            shutil.move(str(f), str(dest))
                    # 迁移完成后删除旧目录（如果为空）
                    try:
                        old_dir.rmdir()
                    except OSError:
                        pass
                    logger.info(f"录制文件已迁移到: {new_dir}")
                except Exception as e:
                    logger.error(f"文件迁移失败: {e}")
                    QMessageBox.warning(self, "迁移失败", f"文件迁移失败: {e}")
                    return

            # 更新运行时配置
            config.CHUNKS_DIR = new_dir
            config.CUSTOM_CHUNKS_DIR = new_path

        # 保存空闲检测设置
        idle_enabled = self.idle_pause_check.isChecked()
        idle_timeout_min = self.idle_timeout_spin.value()
        self.storage.set_setting("idle_pause_enabled", "1" if idle_enabled else "0")
        self.storage.set_setting("idle_pause_timeout_min", str(idle_timeout_min))
        config.IDLE_PAUSE_ENABLED = idle_enabled
        config.IDLE_PAUSE_TIMEOUT_SECONDS = idle_timeout_min * 60

        QMessageBox.information(self, "成功", "录制设置已保存")

    def _on_idle_pause_toggled(self, state):
        """空闲暂停开关切换"""
        self.idle_timeout_spin.setEnabled(state == Qt.Checked)

    def _load_settings(self):
        # 加载 API 设置
        api_url = self.storage.get_setting("api_url", config.API_BASE_URL)
        api_key = self.storage.get_setting("api_key", "")
        api_model = self.storage.get_setting("api_model", config.API_MODEL)
        
        self.api_url_input.setText(api_url)
        self.api_key_input.setText(api_key)
        self.api_model_input.setText(api_model)
        
        # 加载主题设置
        theme = self.storage.get_setting("theme", "dark")
        self._update_theme_button(theme == "dark")

        # 加载录制显示器设置
        saved_output_idx = self.storage.get_setting("record_output_idx", "0")
        try:
            saved_output_idx = int(saved_output_idx)
        except ValueError:
            saved_output_idx = 0
        combo_index = self.monitor_combo.findData(saved_output_idx)
        if combo_index >= 0:
            self.monitor_combo.setCurrentIndex(combo_index)

        # 加载缓存上限设置
        saved_cache_limit = self.storage.get_setting("chunks_max_size_gb", str(config.CHUNKS_MAX_SIZE_GB))
        try:
            self.cache_limit_spin.setValue(int(saved_cache_limit))
        except ValueError:
            self.cache_limit_spin.setValue(config.CHUNKS_MAX_SIZE_GB)

        # 加载自定义录制路径
        saved_custom_dir = self.storage.get_setting("custom_chunks_dir", "")
        self.custom_path_input.setText(saved_custom_dir)

        # 加载空闲检测设置
        saved_idle_enabled = self.storage.get_setting("idle_pause_enabled", "1" if config.IDLE_PAUSE_ENABLED else "0")
        self.idle_pause_check.setChecked(saved_idle_enabled == "1")
        saved_idle_timeout = self.storage.get_setting("idle_pause_timeout_min", str(config.IDLE_PAUSE_TIMEOUT_SECONDS // 60))
        try:
            self.idle_timeout_spin.setValue(int(saved_idle_timeout))
        except ValueError:
            self.idle_timeout_spin.setValue(config.IDLE_PAUSE_TIMEOUT_SECONDS // 60)

        # 加载邮件设置
        self.email_sender_input.setText(self.storage.get_setting("email_sender", ""))
        self.email_auth_input.setText(self.storage.get_setting("email_auth", ""))
        self.email_receiver_input.setText(self.storage.get_setting("email_receiver", ""))
        email_enabled = self.storage.get_setting("email_enabled", "false") == "true"
        self.email_enable_btn.setChecked(email_enabled)
        self._update_email_button()
        
        # 加载邮件发送时间配置
        send_times = self.storage.get_setting("email_send_times", "12:00,22:00")
        self.email_send_times_input.setText(send_times)
    
    def _save_api_config(self):
        """保存 API 配置"""
        api_url = self.api_url_input.text().strip() or config.API_BASE_URL
        api_key = self.api_key_input.text().strip()
        api_model = self.api_model_input.text().strip() or config.API_MODEL
        
        self.storage.set_setting("api_url", api_url)
        self.storage.set_setting("api_key", api_key)
        self.storage.set_setting("api_model", api_model)
        
        # 更新运行时配置
        config.API_BASE_URL = api_url
        config.API_KEY = api_key
        config.API_MODEL = api_model
        
        self.api_key_saved.emit(api_key)
        QMessageBox.information(self, "成功", "API 配置已保存")
    
    def _test_connection(self):
        """测试 API 连接"""
        import asyncio
        from core.llm_provider import DayflowBackendProvider
        
        api_url = self.api_url_input.text().strip() or config.API_BASE_URL
        api_key = self.api_key_input.text().strip()
        api_model = self.api_model_input.text().strip() or config.API_MODEL
        
        if not api_key:
            self._show_test_result(False, "请先输入 API Key")
            return
        
        # 禁用按钮，显示加载状态
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")
        self.test_result_label.setText("正在连接...")
        self.test_result_label.setStyleSheet("font-size: 13px; color: #9CA3AF; padding: 8px 0;")
        self.test_result_label.show()
        
        # 在后台线程执行测试
        import threading
        def run_test():
            provider = DayflowBackendProvider(
                api_base_url=api_url,
                api_key=api_key,
                model=api_model
            )
            loop = asyncio.new_event_loop()
            try:
                success, message = loop.run_until_complete(provider.test_connection())
            finally:
                loop.run_until_complete(provider.close())
                loop.close()
            
            # 回到主线程更新 UI
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self, "_show_test_result",
                Qt.QueuedConnection,
                Q_ARG(bool, success),
                Q_ARG(str, message)
            )
        
        thread = threading.Thread(target=run_test, daemon=True)
        thread.start()
    
    @Slot(bool, str)
    def _show_test_result(self, success: bool, message: str):
        """显示测试结果"""
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        self.test_result_label.show()
        
        if success:
            self.test_result_label.setStyleSheet("""
                font-size: 13px;
                color: #10B981;
                padding: 8px 0;
            """)
            self.test_result_label.setText(f"✓ {message}")
        else:
            self.test_result_label.setStyleSheet("""
                font-size: 13px;
                color: #EF4444;
                padding: 8px 0;
            """)
            self.test_result_label.setText(f"✗ {message}")
    
    def _toggle_theme(self):
        """切换主题"""
        from ui.themes import get_theme_manager
        from PySide6.QtWidgets import QApplication
        
        # 禁用更新以避免闪烁
        self.window().setUpdatesEnabled(False)
        QApplication.processEvents()
        
        theme_manager = get_theme_manager()
        theme_manager.toggle_theme()
        
        is_dark = theme_manager.is_dark
        self.storage.set_setting("theme", "dark" if is_dark else "light")
        self._update_theme_button(is_dark)
        
        # 重新启用更新
        self.window().setUpdatesEnabled(True)
    
    def _update_theme_button(self, is_dark: bool):
        """更新主题按钮显示"""
        if is_dark:
            self.theme_toggle.setText("🌙 暗色")
        else:
            self.theme_toggle.setText("☀️ 亮色")
    
    def _export_dashboard(self):
        """导出仪表盘 HTML 报告"""
        from ui.date_range_dialog import DateRangeDialog
        from core.dashboard_exporter import DashboardExporter
        
        dialog = DateRangeDialog(self)
        
        def on_export(start_date, end_date):
            try:
                exporter = DashboardExporter(self.storage)
                path = exporter.export_and_open(start_date, end_date)
                QMessageBox.information(
                    self, "导出成功", 
                    f"仪表盘已导出并在浏览器中打开\n\n文件位置:\n{path}"
                )
            except Exception as e:
                logger.error(f"导出仪表盘失败: {e}")
                QMessageBox.critical(self, "导出失败", f"导出仪表盘时出错: {e}")
        
        dialog.range_selected.connect(on_export)
        dialog.exec()
    
    def _export_data(self):
        """导出数据"""
        import json
        import shutil
        from pathlib import Path
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出数据",
            f"dayflow_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON 文件 (*.json)"
        )
        
        if not file_path:
            return
        
        try:
            # 获取所有数据
            data = {
                "version": "1.2.0",
                "exported_at": datetime.now().isoformat(),
                "cards": [],
                "settings": {}
            }
            
            # 导出所有卡片（获取最近一年的数据）
            with self.storage._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM timeline_cards ORDER BY start_time DESC")
                for row in cursor.fetchall():
                    card_data = {
                        "id": row["id"],
                        "category": row["category"],
                        "title": row["title"],
                        "summary": row["summary"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "app_sites_json": row["app_sites_json"],
                        "distractions_json": row["distractions_json"],
                        "productivity_score": row["productivity_score"]
                    }
                    data["cards"].append(card_data)
                
                # 导出设置
                cursor = conn.execute("SELECT key, value FROM settings")
                for row in cursor.fetchall():
                    if row["key"] != "api_key":  # 不导出敏感信息
                        data["settings"][row["key"]] = row["value"]
            
            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(
                self, "导出成功", 
                f"已导出 {len(data['cards'])} 条活动记录\n保存到: {file_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出数据时出错: {e}")
    
    def _import_data(self):
        """导入数据"""
        import json
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入数据",
            "",
            "JSON 文件 (*.json)"
        )
        
        if not file_path:
            return
        
        reply = QMessageBox.question(
            self, "确认导入",
            "导入数据会与现有数据合并，重复的记录会被跳过。\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            imported_count = 0
            skipped_count = 0
            
            with self.storage._get_connection() as conn:
                for card in data.get("cards", []):
                    # 检查是否已存在（根据时间判断）
                    cursor = conn.execute(
                        "SELECT id FROM timeline_cards WHERE start_time = ? AND end_time = ?",
                        (card["start_time"], card["end_time"])
                    )
                    if cursor.fetchone():
                        skipped_count += 1
                        continue
                    
                    # 插入新记录
                    conn.execute("""
                        INSERT INTO timeline_cards 
                        (category, title, summary, start_time, end_time, 
                         app_sites_json, distractions_json, productivity_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        card["category"],
                        card["title"],
                        card["summary"],
                        card["start_time"],
                        card["end_time"],
                        card.get("app_sites_json", "[]"),
                        card.get("distractions_json", "[]"),
                        card.get("productivity_score", 0)
                    ))
                    imported_count += 1
                
                # 导入设置（可选）
                for key, value in data.get("settings", {}).items():
                    if key not in ["api_key", "theme"]:  # 保留用户当前设置
                        conn.execute(
                            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                            (key, value)
                        )
            
            QMessageBox.information(
                self, "导入完成",
                f"成功导入 {imported_count} 条记录\n跳过 {skipped_count} 条重复记录"
            )
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入数据时出错: {e}")
    
    def _toggle_email(self):
        """切换邮件推送状态"""
        self._update_email_button()
    
    def _update_email_button(self):
        """更新邮件开关按钮状态"""
        t = get_theme()
        if self.email_enable_btn.isChecked():
            self.email_enable_btn.setText("已开启")
            self.email_enable_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.success};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 600;
                }}
            """)
        else:
            self.email_enable_btn.setText("已关闭")
            self.email_enable_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.bg_tertiary};
                    color: {t.text_muted};
                    border: 1px solid {t.border};
                    border-radius: 6px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {t.bg_hover};
                }}
            """)
    
    def _save_email_config(self):
        """保存邮件配置"""
        sender = self.email_sender_input.text().strip()
        auth = self.email_auth_input.text().strip()
        receiver = self.email_receiver_input.text().strip()
        enabled = self.email_enable_btn.isChecked()
        send_times = self.email_send_times_input.text().strip() or "12:00,22:00"
        
        # 验证发送时间格式
        try:
            times_list = []
            for t in send_times.split(","):
                t = t.strip()
                if t:
                    parts = t.split(":")
                    hour = int(parts[0])
                    minute = int(parts[1]) if len(parts) > 1 else 0
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        raise ValueError(f"无效时间: {t}")
                    times_list.append(f"{hour:02d}:{minute:02d}")
            send_times = ",".join(times_list) if times_list else "12:00,22:00"
        except Exception as e:
            QMessageBox.warning(self, "时间格式错误", f"发送时间格式不正确: {e}\n请使用 HH:MM 格式，多个时间用逗号分隔")
            return
        
        # 验证
        if enabled and (not sender or not auth or not receiver):
            QMessageBox.warning(self, "配置不完整", "请填写完整的邮箱信息")
            return
        
        # 保存
        self.storage.set_setting("email_sender", sender)
        self.storage.set_setting("email_auth", auth)
        self.storage.set_setting("email_receiver", receiver)
        self.storage.set_setting("email_enabled", "true" if enabled else "false")
        self.storage.set_setting("email_send_times", send_times)
        
        QMessageBox.information(self, "成功", "邮件配置已保存")
    
    def _send_test_email(self):
        """发送测试邮件"""
        sender = self.email_sender_input.text().strip()
        auth = self.email_auth_input.text().strip()
        receiver = self.email_receiver_input.text().strip()
        
        if not sender or not auth or not receiver:
            QMessageBox.warning(self, "配置不完整", "请先填写完整的邮箱信息")
            return
        
        # 显示加载状态
        self.email_test_btn.setEnabled(False)
        self.email_test_btn.setText("发送中...")
        self.email_result_label.setText("正在发送测试邮件...")
        self.email_result_label.setStyleSheet("font-size: 13px; color: #9CA3AF; padding: 8px 0;")
        self.email_result_label.show()
        
        # 在后台线程发送
        import threading
        def send():
            try:
                from core.email_service import EmailConfig, EmailService, ReportGenerator
                
                email_config = EmailConfig(
                    sender_email=sender,
                    auth_code=auth,
                    receiver_email=receiver,
                    enabled=True
                )
                service = EmailService(email_config)
                generator = ReportGenerator(self.storage)
                
                from datetime import datetime
                subject = f"🧪 Dayflow 测试邮件 - {datetime.now().strftime('%H:%M')}"
                html = generator.generate_daily_report()
                
                success, error_msg = service.send_report(subject, html)
                
                # 使用信号回到主线程更新 UI
                if success:
                    self.email_success.emit()
                else:
                    self.email_error.emit(error_msg)
                    
            except Exception as e:
                self.email_error.emit(str(e))
        
        threading.Thread(target=send, daemon=True).start()
    
    def _show_email_success(self):
        """显示邮件发送成功"""
        self.email_test_btn.setEnabled(True)
        self.email_test_btn.setText("📨 测试发送")
        t = get_theme()
        self.email_result_label.setText("✅ 测试邮件发送成功！请检查收件箱")
        self.email_result_label.setStyleSheet(f"font-size: 13px; color: {t.success}; padding: 4px 0;")
    
    def _show_email_error(self, error: str):
        """显示邮件发送失败"""
        self.email_test_btn.setEnabled(True)
        self.email_test_btn.setText("📨 测试发送")
        t = get_theme()
        self.email_result_label.setText(f"❌ {error}")
        self.email_result_label.setStyleSheet(f"font-size: 13px; color: {t.error}; padding: 4px 0;")
    
    @Slot(bool)
    def _on_test_email_result(self, success: bool):
        """测试邮件结果回调"""
        self.email_test_btn.setEnabled(True)
        self.email_test_btn.setText("📨 发送测试邮件")
        
        t = get_theme()
        if success:
            self.email_result_label.setText("✅ 测试邮件发送成功！请检查收件箱")
            self.email_result_label.setStyleSheet(f"font-size: 13px; color: {t.success}; padding: 8px 0;")
        else:
            self.email_result_label.setText("❌ 发送失败，请检查邮箱配置")
            self.email_result_label.setStyleSheet(f"font-size: 13px; color: {t.error}; padding: 8px 0;")
    
    @Slot(str)
    def _on_test_email_error(self, error: str):
        """测试邮件错误回调"""
        self.email_test_btn.setEnabled(True)
        self.email_test_btn.setText("📨 发送测试邮件")
        
        t = get_theme()
        self.email_result_label.setText(f"❌ 发送失败: {error}")
        self.email_result_label.setStyleSheet(f"font-size: 13px; color: {t.error}; padding: 8px 0;")
    
    # ========== 软件更新相关方法 ==========
    
    def _check_update(self):
        """检查更新"""
        from core.updater import UpdateManager
        
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("检查中...")
        self.update_status_label.setText("正在检查...")
        t = get_theme()
        self.update_status_label.setStyleSheet(f"font-size: 13px; color: {t.text_secondary};")
        
        # 初始化更新管理器
        if not hasattr(self, 'update_manager'):
            self.update_manager = UpdateManager()
        
        import threading
        def check():
            info = self.update_manager.check_update()
            # 回到主线程
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self, "_on_check_update_result",
                Qt.QueuedConnection,
                Q_ARG(bool, info.has_update),
                Q_ARG(str, info.latest_version),
                Q_ARG(str, info.release_notes)
            )
        
        threading.Thread(target=check, daemon=True).start()
    
    @Slot(bool, str, str)
    def _on_check_update_result(self, has_update: bool, latest_version: str, release_notes: str):
        """检查更新结果回调"""
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("🔍 检查更新")
        t = get_theme()
        
        if has_update:
            self.update_status_label.setText(f"发现新版本: v{latest_version}")
            self.update_status_label.setStyleSheet(f"font-size: 13px; color: {t.success}; font-weight: 600;")
            self.download_btn.show()
            self._latest_version = latest_version
            self._release_notes = release_notes
        else:
            self.update_status_label.setText("已是最新版本 ✓")
            self.update_status_label.setStyleSheet(f"font-size: 13px; color: {t.text_secondary};")
            self.download_btn.hide()
    
    def _start_download(self):
        """开始下载更新"""
        self.download_btn.setEnabled(False)
        self.download_btn.setText("下载中...")
        self.update_progress.setValue(0)
        self.update_progress.show()
        
        def on_progress(percent):
            # 回到主线程更新进度
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self.update_progress, "setValue",
                Qt.QueuedConnection,
                Q_ARG(int, int(percent))
            )
        
        def on_complete(success, error):
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self, "_on_download_complete",
                Qt.QueuedConnection,
                Q_ARG(bool, success),
                Q_ARG(str, error)
            )
        
        self.update_manager.start_download(
            on_progress=on_progress,
            on_complete=on_complete
        )
    
    @Slot(bool, str)
    def _on_download_complete(self, success: bool, error: str):
        """下载完成回调"""
        self.download_btn.setEnabled(True)
        self.download_btn.setText("⬇️ 下载更新")
        t = get_theme()
        
        if success:
            self.update_progress.setValue(100)
            self.update_status_label.setText("下载完成，点击安装")
            self.update_status_label.setStyleSheet(f"font-size: 13px; color: {t.success}; font-weight: 600;")
            self.download_btn.hide()
            self.install_btn.show()
        else:
            self.update_progress.hide()
            self.update_status_label.setText(f"下载失败")
            self.update_status_label.setStyleSheet(f"font-size: 13px; color: {t.error};")
            self._show_download_failed_dialog(error)
    
    def _show_download_failed_dialog(self, error: str):
        """显示下载失败对话框"""
        from core.updater import UpdateManager
        
        msg = QMessageBox(self)
        msg.setWindowTitle("下载失败")
        msg.setText(f"自动下载失败：{error}")
        msg.setInformativeText("您可以尝试手动下载：")
        
        github_btn = msg.addButton("GitHub 下载", QMessageBox.ActionRole)
        mirror_btn = msg.addButton("镜像下载(国内加速)", QMessageBox.ActionRole)
        msg.addButton("取消", QMessageBox.RejectRole)
        
        msg.exec()
        
        if msg.clickedButton() == github_btn:
            QDesktopServices.openUrl(QUrl(UpdateManager.get_github_release_url()))
        elif msg.clickedButton() == mirror_btn:
            QDesktopServices.openUrl(QUrl(UpdateManager.get_mirror_release_url()))
    
    def _install_update(self):
        """安装更新"""
        reply = QMessageBox.question(
            self,
            "安装更新",
            f"即将安装 v{self._latest_version}\n\n程序将自动重启，是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.update_manager.apply_update():
                # 退出应用，让 updater 接管
                QApplication.quit()
            else:
                QMessageBox.warning(
                    self,
                    "安装失败",
                    "无法启动更新程序，请手动下载安装最新版本。"
                )
    
    def _toggle_log_view(self):
        """切换日志显示"""
        if self.log_text.isVisible():
            self.log_text.hide()
            self.refresh_log_btn.hide()
            self.view_log_btn.setText("📄 查看日志")
        else:
            self._refresh_log()
            self.log_text.show()
            self.refresh_log_btn.show()
            self.view_log_btn.setText("📄 收起日志")
    
    def _refresh_log(self):
        """刷新日志内容"""
        log_file = config.APP_DATA_DIR / "dayflow.log"
        
        if not log_file.exists():
            self.log_text.setPlainText("📭 暂无日志文件")
            return
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                # 读取最后 500 行
                lines = f.readlines()
                last_lines = lines[-500:] if len(lines) > 500 else lines
                content = ''.join(last_lines)
            
            self.log_text.setPlainText(content)
            # 滚动到底部
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
        except Exception as e:
            self.log_text.setPlainText(f"❌ 读取日志失败: {e}")
    
    def _open_log_folder(self):
        """打开日志所在目录"""
        import subprocess
        log_dir = config.APP_DATA_DIR
        
        if log_dir.exists():
            # Windows 打开文件夹
            subprocess.run(['explorer', str(log_dir)])
        else:
            QMessageBox.warning(self, "提示", f"日志目录不存在:\n{log_dir}")
    
    def _init_autostart_status(self):
        """初始化自启动状态"""
        from core.autostart import is_autostart_enabled, is_frozen
        
        if not is_frozen():
            # 开发模式
            self.autostart_btn.setEnabled(False)
            self.autostart_btn.setText("⚪ 仅 EXE 可用")
            self.autostart_status.setText("开发模式下不可用")
        else:
            enabled = is_autostart_enabled()
            self.autostart_btn.setChecked(enabled)
            self._update_autostart_button()
    
    def _toggle_autostart(self):
        """切换开机启动状态"""
        from core.autostart import is_autostart_enabled, enable_autostart, disable_autostart
        
        currently_enabled = is_autostart_enabled()
        
        if currently_enabled:
            # 禁用
            success, msg = disable_autostart()
        else:
            # 启用
            success, msg = enable_autostart()
        
        if success:
            self._update_autostart_button()
            self.autostart_status.setText(msg)
            self.autostart_status.setStyleSheet("color: #10B981; font-size: 13px;")
        else:
            # 恢复按钮状态
            self.autostart_btn.setChecked(currently_enabled)
            self.autostart_status.setText(msg)
            self.autostart_status.setStyleSheet("color: #EF4444; font-size: 13px;")
    
    def _update_autostart_button(self):
        """更新自启动按钮显示"""
        from core.autostart import is_autostart_enabled
        
        t = get_theme()
        enabled = is_autostart_enabled()
        self.autostart_btn.setChecked(enabled)
        
        if enabled:
            self.autostart_btn.setText("🟢 已启用")
            self.autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.success};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 0 20px;
                }}
                QPushButton:hover {{
                    opacity: 0.9;
                }}
            """)
        else:
            self.autostart_btn.setText("⚪ 未启用")
            self.autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.bg_tertiary};
                    color: {t.text_primary};
                    border: 1px solid {t.border};
                    border-radius: 8px;
                    font-size: 13px;
                    padding: 0 20px;
                }}
                QPushButton:hover {{
                    background-color: {t.bg_hover};
                    border-color: {t.accent};
                }}
            """)


class MainWindow(QMainWindow):
    """Dayflow 主窗口"""
    
    def __init__(self):
        super().__init__()

        # 初始化组件
        self.storage = StorageManager()
        self.recording_manager = None
        self.analysis_manager = None

        # 从数据库同步运行时配置
        self._sync_config_from_db()
        self._stopping = False  # 防止重复点击停止按钮
        self._quitting = False  # 标记是否正在退出应用
        
        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._setup_timers()
        self._load_data()
        
        # 应用主题
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)

    def _sync_config_from_db(self):
        """从数据库读取配置，同步到运行时 config 模块"""
        # 自定义录制路径
        custom_dir = self.storage.get_setting("custom_chunks_dir", "")
        if custom_dir:
            config.CUSTOM_CHUNKS_DIR = custom_dir
            config.CHUNKS_DIR = Path(custom_dir)
            config.CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

        # 缓存上限
        cache_limit = self.storage.get_setting("chunks_max_size_gb", str(config.CHUNKS_MAX_SIZE_GB))
        try:
            config.CHUNKS_MAX_SIZE_GB = int(cache_limit)
        except ValueError:
            pass

        # 空闲检测设置
        idle_enabled = self.storage.get_setting("idle_pause_enabled", "1" if config.IDLE_PAUSE_ENABLED else "0")
        config.IDLE_PAUSE_ENABLED = (idle_enabled == "1")
        idle_timeout = self.storage.get_setting("idle_pause_timeout_min", str(config.IDLE_PAUSE_TIMEOUT_SECONDS // 60))
        try:
            config.IDLE_PAUSE_TIMEOUT_SECONDS = int(idle_timeout) * 60
        except ValueError:
            pass

    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle(config.WINDOW_TITLE)
        self.setMinimumSize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)
        self.resize(1100, 700)
        
        # 设置无边框窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        
        # 设置窗口图标
        self.setWindowIcon(self._create_tray_icon())
    
    def _setup_ui(self):
        """构建 UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        # 整体垂直布局：标题栏 + 内容区
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # 自定义标题栏
        self.title_bar = CustomTitleBar(self)
        self.title_bar.minimize_to_tray.connect(self._minimize_to_tray)
        self.title_bar.minimize_window.connect(self.showMinimized)
        self.title_bar.maximize_window.connect(self._toggle_maximize)
        self.title_bar.close_window.connect(self.close)
        root_layout.addWidget(self.title_bar)
        
        # 内容区容器
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content_widget)
        
        # ===== 侧边栏 =====
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 20)
        sidebar_layout.setSpacing(4)
        
        # Logo
        self.logo = QLabel("🌊 Dayflow")
        sidebar_layout.addWidget(self.logo)
        
        # 导航按钮
        self.nav_timeline = SidebarButton("时间轴", "📊")
        self.nav_timeline.setChecked(True)
        self.nav_timeline.clicked.connect(lambda: self._switch_page(0))
        sidebar_layout.addWidget(self.nav_timeline)

        self.nav_report = SidebarButton("日报", "📋")
        self.nav_report.clicked.connect(lambda: self._switch_page(1))
        sidebar_layout.addWidget(self.nav_report)

        self.nav_stats = SidebarButton("统计", "📈")
        self.nav_stats.clicked.connect(lambda: self._switch_page(2))
        sidebar_layout.addWidget(self.nav_stats)

        self.nav_settings = SidebarButton("设置", "⚙️")
        self.nav_settings.clicked.connect(lambda: self._switch_page(3))
        sidebar_layout.addWidget(self.nav_settings)
        
        sidebar_layout.addStretch()
        
        # 录制状态指示器
        self.recording_indicator = RecordingIndicator()
        sidebar_layout.addWidget(self.recording_indicator)
        
        # 录制控制按钮
        self.record_btn = QPushButton("开始录制")
        self.record_btn.setCursor(Qt.PointingHandCursor)
        self.record_btn.setFixedHeight(44)
        self.record_btn.clicked.connect(self._toggle_recording)
        sidebar_layout.addWidget(self.record_btn)
        
        # 暂停按钮
        self.pause_btn = QPushButton("⏸ 暂停")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setFixedHeight(36)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.pause_btn.setEnabled(False)
        sidebar_layout.addWidget(self.pause_btn)
        
        # GitHub 链接
        self.github_btn = QPushButton("⭐ GitHub")
        self.github_btn.setCursor(Qt.PointingHandCursor)
        self.github_btn.setFixedHeight(32)
        self.github_btn.setToolTip("在 GitHub 上查看项目")
        self.github_btn.clicked.connect(self._open_github)
        sidebar_layout.addWidget(self.github_btn)
        
        content_layout.addWidget(self.sidebar)
        
        # ===== 主内容区 =====
        self.stack = QStackedWidget()
        
        # 时间轴页面
        self.timeline_view = TimelineView()
        self.timeline_view.card_selected.connect(self._on_card_selected)
        self.timeline_view.date_changed.connect(self._on_date_changed)
        self.timeline_view.export_requested.connect(self._on_export_requested)
        self.timeline_view.card_updated.connect(self._on_card_updated)
        self.timeline_view.card_deleted.connect(self._on_card_deleted)
        self.timeline_view.daily_report_clicked.connect(self._generate_daily_report)
        self.stack.addWidget(self.timeline_view)

        # 日报页面
        self.report_view = DailyReportView(self.storage)
        self.report_view.generate_report_requested.connect(self._generate_daily_report)
        self.stack.addWidget(self.report_view)

        # 统计页面
        self.stats_panel = StatsPanel(self.storage)
        self.stack.addWidget(self.stats_panel)

        # 设置页面
        self.settings_panel = SettingsPanel(self.storage)
        self.settings_panel.api_key_saved.connect(self._on_api_key_saved)
        self.stack.addWidget(self.settings_panel)
        
        content_layout.addWidget(self.stack)
    
    def _create_tray_icon(self) -> QIcon:
        """创建托盘图标"""
        from PySide6.QtGui import QPixmap, QPainter, QBrush, QPen
        from PySide6.QtCore import QRect
        
        # 创建 64x64 的图标
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 画一个蓝色圆形背景
        painter.setBrush(QBrush(QColor("#4F46E5")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 56, 56)
        
        # 画一个白色的时钟图案
        painter.setPen(QPen(QColor("white"), 4))
        painter.drawEllipse(14, 14, 36, 36)
        
        # 时钟指针
        painter.drawLine(32, 32, 32, 20)  # 分针
        painter.drawLine(32, 32, 42, 32)  # 时针
        
        painter.end()
        
        return QIcon(pixmap)
    
    def _setup_tray(self):
        """设置系统托盘"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # 创建托盘图标
        tray_icon = self._create_tray_icon()
        self.tray_icon.setIcon(tray_icon)
        self.tray_icon.setToolTip("Dayflow - 智能时间追踪")
        
        tray_menu = QMenu()
        
        # 显示窗口
        show_action = QAction("📱 显示窗口", self)
        show_action.triggered.connect(self._show_window)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        # 录制控制
        self.tray_record_action = QAction("▶ 开始录制", self)
        self.tray_record_action.triggered.connect(self._toggle_recording)
        tray_menu.addAction(self.tray_record_action)
        
        # 暂停控制
        self.tray_pause_action = QAction("⏸ 暂停录制", self)
        self.tray_pause_action.triggered.connect(self._toggle_pause)
        self.tray_pause_action.setEnabled(False)
        tray_menu.addAction(self.tray_pause_action)
        
        tray_menu.addSeparator()
        
        # 退出
        quit_action = QAction("❌ 退出", self)
        quit_action.triggered.connect(self._quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
    
    def _setup_timers(self):
        """设置定时器"""
        # 刷新时间轴定时器
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_timeline)
        self.refresh_timer.start(30000)  # 每 30 秒刷新
        
        # 邮件定时检查器 - 每分钟检查一次
        self.email_timer = QTimer(self)
        self.email_timer.timeout.connect(self._check_email_schedule)
        self.email_timer.start(60000)  # 每 60 秒检查

        # 录制状态同步定时器 - 每 5 秒同步一次（处理空闲自动暂停的UI状态）
        self._state_sync_timer = QTimer(self)
        self._state_sync_timer.timeout.connect(self._sync_recording_ui_state)
        self._state_sync_timer.start(5000)

        # 初始化邮件调度器
        self._init_email_scheduler()
    
    def _load_data(self):
        """加载数据"""
        # 加载 API 配置
        api_url = self.storage.get_setting("api_url", "")
        api_key = self.storage.get_setting("api_key", "")
        api_model = self.storage.get_setting("api_model", "")
        
        if api_url:
            config.API_BASE_URL = api_url
        if api_key:
            config.API_KEY = api_key
        if api_model:
            config.API_MODEL = api_model
        
        # 加载今日时间轴
        self._refresh_timeline()

        # 延迟检查昨日日报（让 UI 先加载完成）
        QTimer.singleShot(3000, self._auto_generate_yesterday_report)
    
    def _refresh_timeline(self):
        """刷新时间轴"""
        today = datetime.now()
        cards = self.storage.get_cards_for_date(today)
        self.timeline_view.set_date(today)
        self.timeline_view.set_cards(cards)
    
    def _switch_page(self, index: int):
        """切换页面"""
        self.stack.setCurrentIndex(index)
        self.nav_timeline.setChecked(index == 0)
        self.nav_report.setChecked(index == 1)
        self.nav_stats.setChecked(index == 2)
        self.nav_settings.setChecked(index == 3)

        # 切换到统计页面时刷新数据
        if index == 2:
            self.stats_panel.refresh()
    
    def auto_start_recording(self):
        """自启动后自动开始录制（静默模式）"""
        # 从存储中重新加载 API Key，确保使用最新配置
        api_key = self.storage.get_setting("api_key", "")
        if api_key:
            config.API_KEY = api_key
        
        # 检查 API Key 是否已配置
        if not config.API_KEY:
            logger.warning("自启动时未检测到 API Key，跳过自动录制")
            # 静默启动时不弹窗，只在日志中记录
            return
        
        # 延迟一小段时间，确保窗口和组件已完全初始化
        QTimer.singleShot(1000, self._do_auto_start_recording)
    
    def _do_auto_start_recording(self):
        """执行自动开始录制"""
        try:
            if self.recording_manager is None:
                from core.recorder import RecordingManager
                self.recording_manager = RecordingManager(self.storage)
            
            # 如果已经在录制，则跳过
            if self.recording_manager.is_recording:
                logger.info("录制已在进行中，跳过自动启动")
                return
            
            logger.info("自启动后自动开始录制...")
            self.recording_manager.start_recording()
            self._start_analysis()
            self._update_record_button(True)
            self.recording_indicator.set_recording(True)
            self.tray_record_action.setText("⏹ 停止录制")
            self.tray_icon.setToolTip("Dayflow - 录制中...")
            self.pause_btn.setEnabled(True)
            self.tray_pause_action.setEnabled(True)
            
            # 显示托盘提示
            self.tray_icon.showMessage(
                "Dayflow",
                "已自动开始录制 ✓",
                QSystemTrayIcon.Information,
                2000
            )
            logger.info("自动录制已启动")
        except Exception as e:
            logger.error(f"自动开始录制失败: {e}")
    
    def _toggle_recording(self):
        """切换录制状态"""
        if self.recording_manager is None:
            from core.recorder import RecordingManager
            self.recording_manager = RecordingManager(self.storage)
        
        if self.recording_manager.is_recording:
            # 防止重复点击
            if self._stopping:
                logger.debug("已在停止中，忽略重复点击")
                return
            self._stopping = True
            
            # 立即更新 UI，让用户知道正在停止
            self.record_btn.setEnabled(False)
            self.record_btn.setText("停止中...")
            self.pause_btn.setEnabled(False)
            self.tray_record_action.setEnabled(False)
            
            # 显示提示消息
            self.tray_icon.showMessage(
                "Dayflow",
                "正在保存数据并结束录制，请稍候...",
                QSystemTrayIcon.Information,
                3000  # 显示 3 秒
            )
            
            # 在后台线程中执行停止操作
            import threading
            def stop_in_background():
                try:
                    self.recording_manager.stop_recording()
                    self._stop_analysis()
                except Exception as e:
                    logger.error(f"停止录制时出错: {e}")
                finally:
                    # 回到主线程更新 UI
                    from PySide6.QtCore import QMetaObject, Qt
                    QMetaObject.invokeMethod(self, "_on_recording_stopped", Qt.QueuedConnection)
            
            threading.Thread(target=stop_in_background, daemon=True).start()
        else:
            # 检查 API Key
            if not config.API_KEY:
                QMessageBox.warning(
                    self, 
                    "提示", 
                    "请先在设置中配置 API Key"
                )
                self._switch_page(2)
                return
            
            self.recording_manager.start_recording()
            self._start_analysis()
            self._update_record_button(True)
            self.recording_indicator.set_recording(True)
            self.tray_record_action.setText("⏹ 停止录制")
            self.tray_icon.setToolTip("Dayflow - 录制中...")
            self.pause_btn.setEnabled(True)
            self.tray_pause_action.setEnabled(True)
    
    def _sync_recording_ui_state(self):
        """同步录制UI状态（处理空闲自动暂停导致的UI不一致）"""
        if self.recording_manager is None or not self.recording_manager.is_recording:
            return

        is_paused = self.recording_manager.is_paused
        btn_says_paused = self.pause_btn.text() == "▶ 继续"

        if is_paused and not btn_says_paused:
            # 录制已被自动暂停，但按钮仍显示"暂停"
            self.pause_btn.setText("▶ 继续")
            self.tray_pause_action.setText("▶ 继续录制")
            self.recording_indicator.set_recording(True, paused=True)
            elapsed = self.recording_indicator.get_elapsed_time()
            if self.recording_manager.is_idle_paused:
                self.tray_icon.setToolTip(f"Dayflow - 空闲暂停 {elapsed}")
            else:
                self.tray_icon.setToolTip(f"Dayflow - 已暂停 {elapsed}")
        elif not is_paused and btn_says_paused:
            # 录制已自动恢复，但按钮仍显示"继续"
            self.pause_btn.setText("⏸ 暂停")
            self.tray_pause_action.setText("⏸ 暂停录制")
            self.recording_indicator.set_recording(True, paused=False)
            self.tray_icon.setToolTip("Dayflow - 录制中...")

    def _start_analysis(self):
        """启动分析调度器"""
        if self.analysis_manager is None:
            from core.analysis import AnalysisManager
            self.analysis_manager = AnalysisManager(self.storage)
        
        self.analysis_manager.start_scheduler()
        logger.info("分析调度器已启动")
    
    def _stop_analysis(self):
        """停止分析调度器"""
        if self.analysis_manager:
            self.analysis_manager.stop_scheduler()
            logger.info("分析调度器已停止")
    
    @Slot()
    def _on_recording_stopped(self):
        """录制停止后的 UI 更新（在主线程中调用）"""
        self._stopping = False  # 重置停止标志
        self.record_btn.setEnabled(True)
        self._update_record_button(False)
        self.recording_indicator.set_recording(False)
        self.tray_record_action.setEnabled(True)
        self.tray_record_action.setText("▶ 开始录制")
        self.tray_icon.setToolTip("Dayflow - 智能时间追踪")
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸ 暂停")
        self.tray_pause_action.setEnabled(False)
        self.tray_pause_action.setText("⏸ 暂停录制")
        
        # 显示完成提示
        self.tray_icon.showMessage(
            "Dayflow",
            "录制已停止，数据已保存 ✓",
            QSystemTrayIcon.Information,
            2000
        )
    
    def _toggle_pause(self):
        """切换暂停状态"""
        if self.recording_manager is None:
            return
        
        if self.recording_manager.is_paused:
            # 继续录制
            self.recording_manager.resume_recording()
            self.pause_btn.setText("⏸ 暂停")
            self.tray_pause_action.setText("⏸ 暂停录制")
            self.recording_indicator.set_recording(True, paused=False)
            self.tray_icon.setToolTip("Dayflow - 录制中...")
            logger.info("录制已继续")
        else:
            # 暂停录制
            self.recording_manager.pause_recording()
            self.pause_btn.setText("▶ 继续")
            self.tray_pause_action.setText("▶ 继续录制")
            self.recording_indicator.set_recording(True, paused=True)
            elapsed = self.recording_indicator.get_elapsed_time()
            self.tray_icon.setToolTip(f"Dayflow - 已暂停 {elapsed}")
            logger.info("录制已暂停")
    
    def _update_record_button(self, recording: bool):
        """更新录制按钮状态"""
        t = get_theme()
        if recording:
            self.record_btn.setText("⏹ 停止录制")
            self.record_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.error};
                    color: white;
                    border: none;
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: #FF6961;
                }}
            """)
        else:
            self.record_btn.setText("● 开始录制")
            self.record_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.accent};
                    color: white;
                    border: none;
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {t.accent_hover};
                }}
            """)
    
    def apply_theme(self):
        """应用主题到主窗口组件"""
        t = get_theme()
        
        # 侧边栏
        self.sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {t.bg_sidebar};
                border-right: 1px solid {t.border};
            }}
        """)
        
        # Logo
        self.logo.setStyleSheet(f"""
            font-size: 20px;
            font-weight: 700;
            color: {t.text_primary};
            padding: 8px 12px;
            margin-bottom: 16px;
        """)
        
        # 主内容区
        self.stack.setStyleSheet(f"background-color: {t.bg_primary};")
        
        # 暂停按钮
        self.pause_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: none;
                border-radius: 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
            }}
            QPushButton:disabled {{
                background-color: {t.bg_secondary};
                color: {t.text_muted};
            }}
        """)
        
        # GitHub 按钮
        self.github_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {t.text_muted};
                border: none;
                border-radius: 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {t.accent};
                background-color: {t.bg_hover};
            }}
        """)
        
        # 更新录制按钮（根据当前状态）
        is_recording = self.recording_manager and self.recording_manager.is_recording
        self._update_record_button(is_recording)
    
    def _open_github(self):
        """打开 GitHub 项目页面"""
        import webbrowser
        webbrowser.open("https://github.com/SeiShonagon520/Dayflow")
    
    def _on_card_selected(self, card: ActivityCard):
        """卡片被点击"""
        logger.info(f"卡片被点击: {card.title}")
        # 现在由 TimelineView 内部处理编辑对话框
    
    def _on_card_updated(self, card: ActivityCard):
        """卡片更新"""
        success = self.storage.update_card(
            card_id=card.id,
            category=card.category,
            title=card.title,
            summary=card.summary,
            productivity_score=card.productivity_score
        )
        if success:
            logger.info(f"卡片已更新: {card.id} - {card.title}")
        else:
            QMessageBox.warning(self, "更新失败", "无法保存修改，请重试")
    
    def _on_card_deleted(self, card_id: int):
        """卡片删除"""
        success = self.storage.delete_card(card_id)
        if success:
            logger.info(f"卡片已删除: {card_id}")
        else:
            QMessageBox.warning(self, "删除失败", "无法删除记录，请重试")
    
    def _on_api_key_saved(self, api_key: str):
        """API Key 保存后"""
        logger.info("API Key 已更新")
    
    def _on_date_changed(self, date: datetime):
        """日期切换时加载对应数据"""
        logger.info(f"切换到日期: {date.strftime('%Y-%m-%d')}")
        cards = self.storage.get_cards_for_date(date)
        self.timeline_view.set_cards(cards)
    
    def _on_export_requested(self, date: datetime, cards: list):
        """导出数据到 CSV"""
        import csv
        from PySide6.QtWidgets import QFileDialog
        
        if not cards:
            QMessageBox.information(self, "提示", "当前日期没有数据可导出")
            return
        
        # 选择保存路径
        default_name = f"dayflow_{date.strftime('%Y%m%d')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 CSV",
            default_name,
            "CSV 文件 (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                # 写入表头
                writer.writerow([
                    '开始时间', '结束时间', '时长(分钟)', 
                    '类别', '标题', '摘要', 
                    '应用程序', '生产力评分'
                ])
                
                # 写入数据
                for card in cards:
                    apps = ', '.join([app.name for app in card.app_sites]) if card.app_sites else ''
                    writer.writerow([
                        card.start_time.strftime('%Y-%m-%d %H:%M:%S') if card.start_time else '',
                        card.end_time.strftime('%Y-%m-%d %H:%M:%S') if card.end_time else '',
                        f"{card.duration_minutes:.1f}",
                        card.category or '',
                        card.title or '',
                        card.summary or '',
                        apps,
                        f"{card.productivity_score:.0f}"
                    ])
            
            QMessageBox.information(self, "成功", f"数据已导出到:\n{file_path}")
            logger.info(f"导出 CSV 成功: {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
            logger.error(f"导出 CSV 失败: {e}")

    def _generate_daily_report(self, date: datetime):
        """生成每日工作报告"""
        import threading

        date_str = date.strftime("%Y-%m-%d")

        # 检查缓存
        cached = self.storage.get_daily_report(date_str)
        if cached:
            self.report_view.show_report(date_str, cached)
            self._switch_page(1)
            dialog = DailyReportDialog(date_str, cached, self)
            dialog.exec()
            return

        # 获取当日活动卡片
        cards = self.storage.get_cards_for_date(date)
        if not cards:
            QMessageBox.information(self, "提示", f"{date_str} 没有活动记录数据")
            return

        # 显示进度对话框
        progress = QProgressDialog(f"正在为 {date_str} 生成工作报告...", None, 0, 0, self)
        progress.setWindowTitle("AI 分析中")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        def _do_generate():
            try:
                from core.llm_provider import generate_daily_report_sync
                result = generate_daily_report_sync(cards, date_str)
                self.storage.save_daily_report(date_str, result)
                QTimer.singleShot(0, lambda: self._show_daily_report(date_str, result))
            except Exception as e:
                logger.error(f"日报生成失败: {e}")
                QTimer.singleShot(0, lambda: self._show_report_error(str(e)))
            finally:
                QTimer.singleShot(0, progress.close)

        threading.Thread(target=_do_generate, daemon=True).start()

    def _show_daily_report(self, date_str: str, content: str):
        """展示日报"""
        if hasattr(self, '_report_loading'):
            self._report_loading.close()
        # 同时更新日报页面并切换过去
        self.report_view.show_report(date_str, content)
        self._switch_page(1)
        # 弹出对话框展示
        dialog = DailyReportDialog(date_str, content, self)
        dialog.exec()

    def _show_report_error(self, error: str):
        """展示日报生成错误"""
        if hasattr(self, '_report_loading'):
            self._report_loading.close()
        self.report_view.show_error(f"日报生成失败：{error}")
        QMessageBox.warning(self, "生成失败", f"日报生成失败：{error}")

    def _auto_generate_yesterday_report(self):
        """启动时自动检查并生成昨日日报"""
        from datetime import timedelta

        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

        # 检查是否已有缓存
        cached = self.storage.get_daily_report(date_str)
        if cached:
            return  # 已有缓存，跳过

        # 检查昨日是否有数据
        cards = self.storage.get_cards_for_date(yesterday)
        if not cards:
            return  # 无数据，跳过

        # 检查 API Key 是否配置
        api_key = self.storage.get_setting("api_key", config.API_KEY)
        if not api_key:
            return  # 未配置 API，跳过

        logger.info(f"自动为 {date_str} 生成工作报告...")

        import threading

        def _do_auto_generate():
            try:
                from core.llm_provider import generate_daily_report_sync
                result = generate_daily_report_sync(cards, date_str)
                self.storage.save_daily_report(date_str, result)
                QTimer.singleShot(0, lambda: self._show_daily_report(date_str, result))
            except Exception as e:
                logger.warning(f"自动日报生成失败: {e}")

        threading.Thread(target=_do_auto_generate, daemon=True).start()
    
    def _show_window(self):
        """显示主窗口"""
        self.show()
        self.raise_()
        self.activateWindow()
    
    def _minimize_to_tray(self):
        """最小化到系统托盘"""
        self.hide()
        self.tray_icon.showMessage(
            "Dayflow",
            "应用已最小化到系统托盘",
            QSystemTrayIcon.Information,
            2000
        )
    
    def _toggle_maximize(self):
        """切换最大化/还原"""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        # 更新标题栏按钮图标
        self.title_bar.update_maximize_button(self.isMaximized())
    
    def _on_tray_activated(self, reason):
        """托盘图标被点击"""
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_window()
        elif reason == QSystemTrayIcon.Trigger:
            # 单击也显示窗口
            self._show_window()
    
    def _quit_app(self):
        """退出应用"""
        self._quitting = True  # 标记正在退出
        
        # 停止录制
        if self.recording_manager and self.recording_manager.is_recording:
            self.recording_manager.stop_recording()
        
        # 停止分析
        self._stop_analysis()
        
        # 关闭数据库连接，确保数据写入
        if self.storage:
            self.storage.close()
        
        QApplication.quit()
    
    def closeEvent(self, event):
        """窗口关闭事件 - 直接最小化到系统托盘"""
        logger = logging.getLogger(__name__)
        logger.debug(f"closeEvent called, _quitting={self._quitting}")

        if self._quitting:
            # 真正退出，接受关闭事件
            logger.debug("Accepting close event (quitting application)")
            event.accept()
        else:
            # 直接最小化到系统托盘，不显示确认对话框
            logger.debug("Ignoring close event, minimizing to tray")
            event.ignore()
            self._minimize_to_tray()
    
    def _init_email_scheduler(self):
        """初始化邮件调度器"""
        from core.email_service import EmailConfig, EmailService, ReportGenerator, EmailScheduler
        
        # 加载配置
        email_config = EmailConfig(
            sender_email=self.storage.get_setting("email_sender", ""),
            auth_code=self.storage.get_setting("email_auth", ""),
            receiver_email=self.storage.get_setting("email_receiver", ""),
            enabled=self.storage.get_setting("email_enabled", "false") == "true"
        )
        
        email_service = EmailService(email_config)
        report_generator = ReportGenerator(self.storage)
        
        # 创建增强版 EmailScheduler，传入 storage 和 tray_icon
        self.email_scheduler = EmailScheduler(
            email_service=email_service,
            report_generator=report_generator,
            storage=self.storage,
            config_manager=getattr(self, 'config_manager', None),
            tray_icon=self.tray_icon
        )
        
        # 应用启动时检查错过的报告
        self.email_scheduler.on_app_start()
        
        logger.info("邮件调度器已初始化（增强版）")
    
    def _check_email_schedule(self):
        """检查是否需要发送定时邮件"""
        # 重新加载配置（以防用户修改）
        enabled = self.storage.get_setting("email_enabled", "false") == "true"
        if not enabled:
            return
        
        # 更新配置
        self.email_scheduler.email_service.config.sender_email = self.storage.get_setting("email_sender", "")
        self.email_scheduler.email_service.config.auth_code = self.storage.get_setting("email_auth", "")
        self.email_scheduler.email_service.config.receiver_email = self.storage.get_setting("email_receiver", "")
        self.email_scheduler.email_service.config.enabled = enabled
        
        # 检查并发送
        self.email_scheduler.check_and_send()
