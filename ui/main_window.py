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
    QApplication, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QSize
from PySide6.QtGui import QIcon, QAction, QFont, QColor, QPalette

import config
from ui.timeline_view import TimelineView
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
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9CA3AF;
                border: none;
                border-radius: 8px;
                text-align: left;
                padding-left: 12px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #374151;
                color: #F3F4F6;
            }
            QPushButton:checked {
                background-color: #4F46E5;
                color: #FFFFFF;
            }
        """)


class RecordingIndicator(QWidget):
    """录制状态指示器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # 指示点
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #6B7280; font-size: 10px;")
        layout.addWidget(self.dot)
        
        # 状态文字
        self.status_label = QLabel("未录制")
        self.status_label.setStyleSheet("""
            color: #9CA3AF;
            font-size: 12px;
        """)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # 闪烁动画
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_state = True
    
    def set_recording(self, recording: bool, paused: bool = False):
        self._recording = recording
        
        if recording and not paused:
            self.dot.setStyleSheet("color: #EF4444; font-size: 10px;")
            self.status_label.setText("录制中")
            self.status_label.setStyleSheet("color: #EF4444; font-size: 12px;")
            self._blink_timer.start(800)
        elif recording and paused:
            self.dot.setStyleSheet("color: #F59E0B; font-size: 10px;")
            self.status_label.setText("已暂停")
            self.status_label.setStyleSheet("color: #F59E0B; font-size: 12px;")
            self._blink_timer.stop()
        else:
            self.dot.setStyleSheet("color: #6B7280; font-size: 10px;")
            self.status_label.setText("未录制")
            self.status_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
            self._blink_timer.stop()
    
    def _blink(self):
        self._blink_state = not self._blink_state
        if self._blink_state:
            self.dot.setStyleSheet("color: #EF4444; font-size: 10px;")
        else:
            self.dot.setStyleSheet("color: transparent; font-size: 10px;")


class SettingsPanel(QWidget):
    """设置面板"""
    
    api_key_saved = Signal(str)
    
    def __init__(self, storage: StorageManager, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 标题
        title = QLabel("设置")
        title.setStyleSheet("""
            font-size: 24px;
            font-weight: 700;
            color: #F9FAFB;
        """)
        layout.addWidget(title)
        
        # API Key 设置
        api_frame = QFrame()
        api_frame.setStyleSheet("""
            QFrame {
                background-color: #1F2937;
                border: 1px solid #374151;
                border-radius: 12px;
            }
        """)
        api_layout = QVBoxLayout(api_frame)
        api_layout.setContentsMargins(20, 20, 20, 20)
        api_layout.setSpacing(12)
        
        api_title = QLabel("API Key")
        api_title.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: #F3F4F6;
        """)
        api_layout.addWidget(api_title)
        
        api_desc = QLabel("请输入您的心流 API Key 以启用云端分析功能\n在 控制台 获取密钥，API 地址: https://apis.iflow.cn/v1")
        api_desc.setStyleSheet("""
            font-size: 13px;
            color: #9CA3AF;
        """)
        api_layout.addWidget(api_desc)
        
        # API Key 输入
        key_row = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("输入 API Key...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setStyleSheet("""
            QLineEdit {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 12px 16px;
                color: #F9FAFB;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #4F46E5;
            }
        """)
        key_row.addWidget(self.api_key_input)
        
        save_btn = QPushButton("保存")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedSize(80, 44)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4F46E5;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #4338CA;
            }
            QPushButton:pressed {
                background-color: #3730A3;
            }
        """)
        save_btn.clicked.connect(self._save_api_key)
        key_row.addWidget(save_btn)
        
        # 测试连接按钮
        test_btn = QPushButton("测试连接")
        test_btn.setCursor(Qt.PointingHandCursor)
        test_btn.setFixedSize(90, 44)
        test_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #047857;
            }
            QPushButton:pressed {
                background-color: #065F46;
            }
            QPushButton:disabled {
                background-color: #6B7280;
            }
        """)
        test_btn.clicked.connect(self._test_connection)
        self.test_btn = test_btn
        key_row.addWidget(test_btn)
        
        api_layout.addLayout(key_row)
        
        # 测试结果显示
        self.test_result_label = QLabel("")
        self.test_result_label.setWordWrap(True)
        self.test_result_label.setStyleSheet("""
            font-size: 13px;
            color: #9CA3AF;
            padding: 8px 0;
        """)
        self.test_result_label.hide()
        api_layout.addWidget(self.test_result_label)
        
        layout.addWidget(api_frame)
        
        # 录制设置
        record_frame = QFrame()
        record_frame.setStyleSheet("""
            QFrame {
                background-color: #1F2937;
                border: 1px solid #374151;
                border-radius: 12px;
            }
        """)
        record_layout = QVBoxLayout(record_frame)
        record_layout.setContentsMargins(20, 20, 20, 20)
        record_layout.setSpacing(8)
        
        record_title = QLabel("录制设置")
        record_title.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: #F3F4F6;
        """)
        record_layout.addWidget(record_title)
        
        record_info = QLabel(f"帧率: {config.RECORD_FPS} FPS  |  切片时长: {config.CHUNK_DURATION_SECONDS} 秒")
        record_info.setStyleSheet("""
            font-size: 13px;
            color: #9CA3AF;
        """)
        record_layout.addWidget(record_info)
        
        layout.addWidget(record_frame)
        
        # 关于
        about_frame = QFrame()
        about_frame.setStyleSheet("""
            QFrame {
                background-color: #1F2937;
                border: 1px solid #374151;
                border-radius: 12px;
            }
        """)
        about_layout = QVBoxLayout(about_frame)
        about_layout.setContentsMargins(20, 20, 20, 20)
        about_layout.setSpacing(8)
        
        about_title = QLabel("关于 Dayflow")
        about_title.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: #F3F4F6;
        """)
        about_layout.addWidget(about_title)
        
        about_info = QLabel("Windows 版本 1.0.0\n智能时间追踪与生产力分析")
        about_info.setStyleSheet("""
            font-size: 13px;
            color: #9CA3AF;
        """)
        about_layout.addWidget(about_info)
        
        layout.addWidget(about_frame)
        
        layout.addStretch()
    
    def _load_settings(self):
        api_key = self.storage.get_setting("api_key", "")
        if api_key:
            self.api_key_input.setText(api_key)
    
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


class MainWindow(QMainWindow):
    """Dayflow 主窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 初始化组件
        self.storage = StorageManager()
        self.recording_manager = None
        self.analysis_manager = None
        
        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._setup_timers()
        self._load_data()
    
    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle(config.WINDOW_TITLE)
        self.setMinimumSize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)
        self.resize(1100, 700)
        
        # 深色主题
        self.setStyleSheet("""
            QMainWindow {
                background-color: #111827;
            }
            QWidget {
                font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
            }
        """)
    
    def _setup_ui(self):
        """构建 UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ===== 侧边栏 =====
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #1F2937;
                border-right: 1px solid #374151;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 20, 12, 20)
        sidebar_layout.setSpacing(4)
        
        # Logo
        logo = QLabel("🌊 Dayflow")
        logo.setStyleSheet("""
            font-size: 20px;
            font-weight: 700;
            color: #F9FAFB;
            padding: 8px 12px;
            margin-bottom: 16px;
        """)
        sidebar_layout.addWidget(logo)
        
        # 导航按钮
        self.nav_timeline = SidebarButton("时间轴", "📊")
        self.nav_timeline.setChecked(True)
        self.nav_timeline.clicked.connect(lambda: self._switch_page(0))
        sidebar_layout.addWidget(self.nav_timeline)
        
        self.nav_settings = SidebarButton("设置", "⚙️")
        self.nav_settings.clicked.connect(lambda: self._switch_page(1))
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
        self._update_record_button(False)
        sidebar_layout.addWidget(self.record_btn)
        
        main_layout.addWidget(sidebar)
        
        # ===== 主内容区 =====
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #111827;")
        
        # 时间轴页面
        self.timeline_view = TimelineView()
        self.timeline_view.card_selected.connect(self._on_card_selected)
        self.stack.addWidget(self.timeline_view)
        
        # 设置页面
        self.settings_panel = SettingsPanel(self.storage)
        self.settings_panel.api_key_saved.connect(self._on_api_key_saved)
        self.stack.addWidget(self.settings_panel)
        
        main_layout.addWidget(self.stack)
    
    def _setup_tray(self):
        """设置系统托盘"""
        self.tray_icon = QSystemTrayIcon(self)
        # self.tray_icon.setIcon(QIcon("icon.png"))  # 需要图标文件
        
        tray_menu = QMenu()
        
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        self.tray_record_action = QAction("开始录制", self)
        self.tray_record_action.triggered.connect(self._toggle_recording)
        tray_menu.addAction(self.tray_record_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("退出", self)
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
        self.nav_settings.setChecked(index == 1)
    
    def _toggle_recording(self):
        """切换录制状态"""
        if self.recording_manager is None:
            from core.recorder import RecordingManager
            self.recording_manager = RecordingManager(self.storage)
        
        if self.recording_manager.is_recording:
            self.recording_manager.stop_recording()
            self._stop_analysis()
            self._update_record_button(False)
            self.recording_indicator.set_recording(False)
            self.tray_record_action.setText("开始录制")
        else:
            # 检查 API Key
            if not config.API_KEY:
                QMessageBox.warning(
                    self, 
                    "提示", 
                    "请先在设置中配置 API Key"
                )
                self._switch_page(1)
                return
            
            self.recording_manager.start_recording()
            self._start_analysis()
            self._update_record_button(True)
            self.recording_indicator.set_recording(True)
            self.tray_record_action.setText("停止录制")
    
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
    
    def _update_record_button(self, recording: bool):
        """更新录制按钮状态"""
        if recording:
            self.record_btn.setText("停止录制")
            self.record_btn.setStyleSheet("""
                QPushButton {
                    background-color: #DC2626;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #B91C1C;
                }
            """)
        else:
            self.record_btn.setText("开始录制")
            self.record_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4F46E5;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #4338CA;
                }
            """)
    
    def _on_card_selected(self, card: ActivityCard):
        """卡片被点击"""
        logger.info(f"卡片被点击: {card.title}")
        # TODO: 显示卡片详情
    
    def _on_api_key_saved(self, api_key: str):
        """API Key 保存后"""
        logger.info("API Key 已更新")
    
    def _on_tray_activated(self, reason):
        """托盘图标被点击"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()
    
    def _quit_app(self):
        """退出应用"""
        # 停止录制
        if self.recording_manager and self.recording_manager.is_recording:
            self.recording_manager.stop_recording()
        
        # 停止分析
        self._stop_analysis()
        
        QApplication.quit()
    
    def closeEvent(self, event):
        """窗口关闭事件 - 最小化到托盘"""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Dayflow",
            "应用已最小化到系统托盘",
            QSystemTrayIcon.Information,
            2000
        )
