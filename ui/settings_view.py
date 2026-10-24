"""
Dayflow Windows - 设置面板
包含 API 设置、显示器与录制偏好、邮件推送、存储管理、开机自启、主题切换与日志诊断
"""
import os
import sys
import shutil
import logging
import asyncio
import threading
import json
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QMessageBox, QScrollArea, QComboBox,
    QSpinBox, QCheckBox, QFileDialog, QApplication, QProgressDialog,
    QProgressBar, QTextEdit,
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QUrl, QMetaObject, Q_ARG
from PySide6.QtGui import QFont, QDesktopServices, QColor

import config
from database.storage import StorageManager
from ui.themes import get_theme_manager, get_theme, DARK_THEME, LIGHT_THEME
from ui.components.collapsible_section import CollapsibleSection
from ui.components.scale_feedback import FeedbackButton
from core.llm_provider import DayflowBackendProvider

logger = logging.getLogger(__name__)

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
        
        # 动效设置：三档循环（跟随系统 → 关闭 → 开启）
        motion_row = QHBoxLayout()
        motion_row.setSpacing(10)
        self.motion_label = QLabel("界面动效")
        self.motion_label.setObjectName("cardDesc")
        self._descs.append(self.motion_label)
        motion_row.addWidget(self.motion_label)
        motion_row.addStretch()
        
        self.motion_hint = QLabel("")
        self.motion_hint.setObjectName("cardDesc")
        self._descs.append(self.motion_hint)
        motion_row.addWidget(self.motion_hint)
        
        self.motion_toggle = FeedbackButton("跟随系统")
        self.motion_toggle.setCursor(Qt.PointingHandCursor)
        self.motion_toggle.setFixedSize(110, 34)
        self.motion_toggle.clicked.connect(self._cycle_motion_mode)
        motion_row.addWidget(self.motion_toggle)
        theme_layout.addLayout(motion_row)
        
        self._update_motion_button()
        
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
        self.test_result_label.setStyleSheet(f"font-size: 13px; color: {get_theme().text_muted}; padding: 8px 0;")
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
        from ui.motion import shake, rise_in
        
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        self.test_result_label.show()
        
        if success:
            self.test_result_label.setStyleSheet(f"""
                font-size: 13px;
                color: {get_theme().success};
                padding: 8px 0;
            """)
            self.test_result_label.setText(f"✓ {message}")
            # 成功给一个很轻的上浮：确认「系统听到了」，
            # 但不做庆祝动画 —— 测个连接不值得放礼花
            rise_in(self.test_result_label, duration="reveal", distance=4)
        else:
            self.test_result_label.setStyleSheet(f"""
                font-size: 13px;
                color: {get_theme().error};
                padding: 8px 0;
            """)
            self.test_result_label.setText(f"✗ {message}")
            # 失败抖一下，把视线引到文字上。信息本身由文字承担，
            # 抖动只负责「往这边看」，不重复表达错误
            shake(self.test_result_label, distance=4, cycles=2)
    
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
    
    def _cycle_motion_mode(self):
        """
        在三档动效偏好之间循环：跟随系统 → 关闭 → 开启 → 跟随系统。
        
        之所以给「强制开启」一档：有人系统里关了动效，只是因为不想看
        别的软件乱动；他们未必希望 Dayflow 也僵住。系统开关是默认值，
        不是不可违抗的命令。
        """
        from ui.motion import get_motion_settings
        settings = get_motion_settings()
        
        current = settings.override
        if current is None:
            settings.set_override(False)      # 跟随系统 → 关闭
        elif current is False:
            settings.set_override(True)       # 关闭 → 开启
        else:
            settings.set_override(None)       # 开启 → 跟随系统
        
        self._update_motion_button()
    
    def _update_motion_button(self):
        """更新动效按钮显示与说明文案"""
        from ui.motion import get_motion_settings
        settings = get_motion_settings()
        override = settings.override
        
        if override is None:
            label = "跟随系统"
            hint = ("系统当前：已开启" if not settings.system_reduces
                    else "系统当前：已关闭")
        elif override:
            label = "始终开启"
            hint = "忽略系统设置"
        else:
            label = "始终关闭"
            hint = "关闭全部过渡动画"
        
        self.motion_toggle.setText(label)
        self.motion_hint.setText(hint)
        self.motion_toggle.setToolTip(
            "减少动效会关闭页面切换、卡片入场与按压缩放等过渡动画，\n"
            "但按下反馈与状态提示仍会保留 —— 界面不会变得无法操作。"
        )
    
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
        self.email_result_label.setStyleSheet(f"font-size: 13px; color: {get_theme().text_muted}; padding: 8px 0;")
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
    
    def _set_email_result(self, success: bool, message: str, padding: str = "8px 0"):
        """
        邮件发送结果的统一出口。

        原本有四个几乎一样的处理器各自设文案和颜色，很容易漏掉动效
        或文案。合并到这里，成功给轻上浮、失败给短抖动，行为一致。
        """
        from ui.motion import shake, rise_in

        t = get_theme()
        if success:
            self.email_result_label.setStyleSheet(
                f"font-size: 13px; color: {t.success}; padding: {padding};")
            self.email_result_label.setText(f"✅ {message}")
            rise_in(self.email_result_label, duration="reveal", distance=4)
        else:
            self.email_result_label.setStyleSheet(
                f"font-size: 13px; color: {t.error}; padding: {padding};")
            self.email_result_label.setText(f"❌ {message}")
            shake(self.email_result_label, distance=4, cycles=2)
        self.email_result_label.show()

    def _show_email_success(self):
        """显示邮件发送成功"""
        self.email_test_btn.setEnabled(True)
        self.email_test_btn.setText("📨 测试发送")
        self._set_email_result(True, "测试邮件发送成功，请检查收件箱", "4px 0")

    def _show_email_error(self, error: str):
        """显示邮件发送失败"""
        self.email_test_btn.setEnabled(True)
        self.email_test_btn.setText("📨 测试发送")
        self._set_email_result(False, error, "4px 0")

    @Slot(bool)
    def _on_test_email_result(self, success: bool):
        """测试邮件结果回调"""
        self.email_test_btn.setEnabled(True)
        self.email_test_btn.setText("📨 发送测试邮件")
        if success:
            self._set_email_result(True, "测试邮件发送成功，请检查收件箱")
        else:
            self._set_email_result(False, "发送失败，请检查邮箱配置")

    @Slot(str)
    def _on_test_email_error(self, error: str):
        """测试邮件错误回调"""
        self.email_test_btn.setEnabled(True)
        self.email_test_btn.setText("📨 发送测试邮件")
        self._set_email_result(False, f"发送失败：{error}")
    
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
            self.autostart_status.setStyleSheet(f"color: {get_theme().success}; font-size: 13px;")
        else:
            # 恢复按钮状态
            self.autostart_btn.setChecked(currently_enabled)
            self.autostart_status.setText(msg)
            self.autostart_status.setStyleSheet(f"color: {get_theme().error}; font-size: 13px;")
    
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


