"""
Dayflow Windows - 主窗口
现代化 Windows 11 风格界面
"""
import logging
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame,
    QLineEdit, QMessageBox, QSystemTrayIcon, QMenu,
    QApplication, QSizePolicy, QSpacerItem, QFileDialog,
    QScrollArea
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QSize
from PySide6.QtGui import QIcon, QAction, QFont, QColor, QPalette

import config
from ui.timeline_view import TimelineView
from ui.stats_view import StatsPanel
from ui.themes import get_theme_manager, get_theme
from core.types import ActivityCard
from database.storage import StorageManager

logger = logging.getLogger(__name__)


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
                border-radius: 10px;
                text-align: left;
                padding-left: 14px;
                font-size: 14px;
                font-weight: 500;
                margin: 2px 8px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
                color: {t.text_primary};
            }}
            QPushButton:checked {{
                background-color: {t.accent};
                color: #FFFFFF;
                font-weight: 600;
            }}
        """)


class RecordingIndicator(QWidget):
    """录制状态指示器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
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
        
        # 闪烁动画
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_state = True
        
        self._apply_idle_theme()
    
    def _apply_idle_theme(self):
        if not self._recording:
            t = get_theme()
            self.dot.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
            self.status_label.setStyleSheet(f"color: {t.text_muted}; font-size: 12px;")
    
    def set_recording(self, recording: bool, paused: bool = False):
        self._recording = recording
        t = get_theme()
        
        if recording and not paused:
            self.dot.setStyleSheet(f"color: {t.error}; font-size: 10px;")
            self.status_label.setText("录制中")
            self.status_label.setStyleSheet(f"color: {t.error}; font-size: 12px;")
            self._blink_timer.start(800)
        elif recording and paused:
            self.dot.setStyleSheet(f"color: {t.warning}; font-size: 10px;")
            self.status_label.setText("已暂停")
            self.status_label.setStyleSheet(f"color: {t.warning}; font-size: 12px;")
            self._blink_timer.stop()
        else:
            self.dot.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
            self.status_label.setText("未录制")
            self.status_label.setStyleSheet(f"color: {t.text_muted}; font-size: 12px;")
            self._blink_timer.stop()
    
    def _blink(self):
        t = get_theme()
        self._blink_state = not self._blink_state
        if self._blink_state:
            self.dot.setStyleSheet(f"color: {t.error}; font-size: 10px;")
        else:
            self.dot.setStyleSheet("color: transparent; font-size: 10px;")


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
        layout.setSpacing(16)
        
        # 页面标题
        self.page_title = QLabel("⚙️ 设置")
        self.page_title.setMinimumHeight(40)
        layout.addWidget(self.page_title)
        
        # === API Key 设置 ===
        api_frame, api_layout = self._create_card(layout)
        self._create_title("🔑 API Key", api_layout)
        
        api_desc = QLabel("请输入您的心流 API Key 以启用云端分析功能")
        api_desc.setObjectName("cardDesc")
        api_desc.setWordWrap(True)
        self._descs.append(api_desc)
        api_layout.addWidget(api_desc)
        
        api_url = QLabel("API 地址: https://apis.iflow.cn/v1")
        api_url.setObjectName("cardDesc")
        self._descs.append(api_url)
        api_layout.addWidget(api_url)
        
        # API Key 输入框
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("输入 API Key...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setMinimumHeight(44)
        api_layout.addWidget(self.api_key_input)
        
        # 按钮行
        key_row = QHBoxLayout()
        key_row.setSpacing(10)
        
        self.save_btn = QPushButton("保存")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setFixedSize(80, 40)
        self.save_btn.clicked.connect(self._save_api_key)
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
        
        data_row.addStretch()
        data_layout.addLayout(data_row)
        
        # === 邮件推送设置 ===
        email_frame, email_layout = self._create_card(layout)
        self._create_title("📧 邮件推送", email_layout)
        self._create_desc("每日 12:00 和 22:00 自动发送效率报告", email_layout)
        
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
        
        # === 关于 ===
        about_frame, about_layout = self._create_card(layout)
        self._create_title("ℹ️ 关于 Dayflow", about_layout)
        
        about_text = QLabel("Windows 版本 1.2.0\n智能时间追踪与生产力分析工具")
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
        
        # 页面标题
        self.page_title.setStyleSheet(f"""
            font-size: 22px;
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
        
        # API Key 输入框
        self.api_key_input.setStyleSheet(f"""
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
        """)
        
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
    
    def _load_settings(self):
        api_key = self.storage.get_setting("api_key", "")
        if api_key:
            self.api_key_input.setText(api_key)
        
        # 加载主题设置
        theme = self.storage.get_setting("theme", "dark")
        self._update_theme_button(theme == "dark")
        
        # 加载邮件设置
        self.email_sender_input.setText(self.storage.get_setting("email_sender", ""))
        self.email_auth_input.setText(self.storage.get_setting("email_auth", ""))
        self.email_receiver_input.setText(self.storage.get_setting("email_receiver", ""))
        email_enabled = self.storage.get_setting("email_enabled", "false") == "true"
        self.email_enable_btn.setChecked(email_enabled)
        self._update_email_button()
    
    def _save_api_key(self):
        api_key = self.api_key_input.text().strip()
        self.storage.set_setting("api_key", api_key)
        config.API_KEY = api_key
        self.api_key_saved.emit(api_key)
        QMessageBox.information(self, "成功", "API Key 已保存")
    
    def _test_connection(self):
        """测试 API 连接"""
        import asyncio
        from core.llm_provider import DayflowBackendProvider
        
        api_key = self.api_key_input.text().strip()
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
            provider = DayflowBackendProvider(api_key=api_key)
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
        
        # 验证
        if enabled and (not sender or not auth or not receiver):
            QMessageBox.warning(self, "配置不完整", "请填写完整的邮箱信息")
            return
        
        # 保存
        self.storage.set_setting("email_sender", sender)
        self.storage.set_setting("email_auth", auth)
        self.storage.set_setting("email_receiver", receiver)
        self.storage.set_setting("email_enabled", "true" if enabled else "false")
        
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


class MainWindow(QMainWindow):
    """Dayflow 主窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 初始化组件
        self.storage = StorageManager()
        self.recording_manager = None
        self.analysis_manager = None
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
    
    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle(config.WINDOW_TITLE)
        self.setMinimumSize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)
        self.resize(1100, 700)
        
        # 设置窗口图标
        self.setWindowIcon(self._create_tray_icon())
    
    def _setup_ui(self):
        """构建 UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ===== 侧边栏 =====
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 20, 12, 20)
        sidebar_layout.setSpacing(4)
        
        # Logo
        self.logo = QLabel("🌊 Dayflow")
        sidebar_layout.addWidget(self.logo)
        
        # 导航按钮
        self.nav_timeline = SidebarButton("时间轴", "📊")
        self.nav_timeline.setChecked(True)
        self.nav_timeline.clicked.connect(lambda: self._switch_page(0))
        sidebar_layout.addWidget(self.nav_timeline)
        
        self.nav_stats = SidebarButton("统计", "📈")
        self.nav_stats.clicked.connect(lambda: self._switch_page(1))
        sidebar_layout.addWidget(self.nav_stats)
        
        self.nav_settings = SidebarButton("设置", "⚙️")
        self.nav_settings.clicked.connect(lambda: self._switch_page(2))
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
        
        main_layout.addWidget(self.sidebar)
        
        # ===== 主内容区 =====
        self.stack = QStackedWidget()
        
        # 时间轴页面
        self.timeline_view = TimelineView()
        self.timeline_view.card_selected.connect(self._on_card_selected)
        self.timeline_view.date_changed.connect(self._on_date_changed)
        self.timeline_view.export_requested.connect(self._on_export_requested)
        self.stack.addWidget(self.timeline_view)
        
        # 统计页面
        self.stats_panel = StatsPanel(self.storage)
        self.stack.addWidget(self.stats_panel)
        
        # 设置页面
        self.settings_panel = SettingsPanel(self.storage)
        self.settings_panel.api_key_saved.connect(self._on_api_key_saved)
        self.stack.addWidget(self.settings_panel)
        
        main_layout.addWidget(self.stack)
    
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
        
        # 初始化邮件调度器
        self._init_email_scheduler()
    
    def _load_data(self):
        """加载数据"""
        # 加载 API Key
        api_key = self.storage.get_setting("api_key", "")
        if api_key:
            config.API_KEY = api_key
        
        # 加载今日时间轴
        self._refresh_timeline()
    
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
        self.nav_stats.setChecked(index == 1)
        self.nav_settings.setChecked(index == 2)
        
        # 切换到统计页面时刷新数据
        if index == 1:
            self.stats_panel.refresh()
    
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
            self.pause_btn.setEnabled(True)
            self.tray_pause_action.setEnabled(True)
    
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
            self.recording_indicator.set_recording(True)
            logger.info("录制已继续")
        else:
            # 暂停录制
            self.recording_manager.pause_recording()
            self.pause_btn.setText("▶ 继续")
            self.tray_pause_action.setText("▶ 继续录制")
            self.recording_indicator.set_recording(False)
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
        # TODO: 显示卡片详情
    
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
    
    def _show_window(self):
        """显示主窗口"""
        self.show()
        self.raise_()
        self.activateWindow()
    
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
        
        QApplication.quit()
    
    def closeEvent(self, event):
        """窗口关闭事件 - 最小化到托盘或退出"""
        if self._quitting:
            # 真正退出，接受关闭事件
            event.accept()
        else:
            # 最小化到托盘
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Dayflow",
                "应用已最小化到系统托盘",
                QSystemTrayIcon.Information,
                2000
            )
    
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
        self.email_scheduler = EmailScheduler(email_service, report_generator)
        
        logger.info("邮件调度器已初始化")
    
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
