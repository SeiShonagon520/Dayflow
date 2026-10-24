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



# 导入抽离的 UI 组件
from ui.components.title_bar import TitleBarButton, CustomTitleBar
from ui.components.sidebar_button import SidebarButton
from ui.components.recording_indicator import RecordingIndicator
from ui.components.collapsible_section import CollapsibleSection
from ui.components.scale_feedback import ScaleFeedbackMixin, FeedbackButton
from ui.components.spinner import SpinnerDot
from ui.motion import press_feedback, release_feedback, rise_in, get_motion_settings
from ui.daily_report_dialog import DailyReportDialog
from ui.settings_view import SettingsPanel

__all__ = [
    "MainWindow",
    "SettingsPanel",
    "DailyReportDialog",
    "TitleBarButton",
    "CustomTitleBar",
    "SidebarButton",
    "RecordingIndicator",
    "CollapsibleSection",
]


def apply_dwm_window_attributes(hwnd: int, is_dark: bool = True):
    """为 Windows 11 启用 DWM 原生圆角与沉浸式暗色标题支持"""
    try:
        import ctypes
        from ctypes import c_int, byref
        
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            byref(c_int(DWMWCP_ROUND)),
            ctypes.sizeof(c_int)
        )
        
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark_flag = c_int(1 if is_dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(dark_flag),
            ctypes.sizeof(c_int)
        )
    except Exception:
        pass


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
        
        # 启用 Windows 11 DWM 原生圆角与暗色效果
        t = get_theme()
        apply_dwm_window_attributes(int(self.winId()), is_dark=(t.name == "dark"))
        
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
        
        # 录制状态指示器（现代交互胶囊）
        self.recording_indicator = RecordingIndicator()
        self.recording_indicator.clicked.connect(self._on_recording_pill_clicked)
        sidebar_layout.addWidget(self.recording_indicator)
        
        # 录制控制按钮（主 CTA）
        self._record_spinner = None
        self.record_btn = FeedbackButton("开始录制")
        self.record_btn.setCursor(Qt.PointingHandCursor)
        self.record_btn.setFixedHeight(44)
        self.record_btn.clicked.connect(self._toggle_recording)
        sidebar_layout.addWidget(self.record_btn)
        
        # 暂停按钮
        self.pause_btn = FeedbackButton("⏸ 暂停")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setFixedHeight(36)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.pause_btn.setEnabled(False)
        sidebar_layout.addWidget(self.pause_btn)
        
        # GitHub 链接
        self.github_btn = FeedbackButton("⭐ GitHub")
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
        self.timeline_view.card_restored.connect(self._on_card_restored)
        self.timeline_view.start_recording_requested.connect(self._start_recording_from_empty)
        self.timeline_view.refresh_requested.connect(self._refresh_timeline)
        self.timeline_view.daily_report_clicked.connect(self._generate_daily_report)
        self.stack.addWidget(self.timeline_view)

        # 日报页面
        self.report_view = DailyReportView(self.storage)
        self.report_view.generate_report_requested.connect(self._generate_daily_report)
        self.stack.addWidget(self.report_view)

        # 统计页面
        self.stats_panel = StatsPanel(self.storage)
        self.stats_panel.date_clicked.connect(self._on_stats_date_clicked)
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
        
        # 画一个 Action Blue 圆形背景（Apple 单一强调色）
        painter.setBrush(QBrush(QColor(get_theme().accent)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 56, 56)
        
        # 画一个白色的时钟图案
        painter.setPen(QPen(QColor("#FFFFFF"), 4))
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
        if index == self.stack.currentIndex():
            return
        self.stack.setCurrentIndex(index)
        self.nav_timeline.setChecked(index == 0)
        self.nav_report.setChecked(index == 1)
        self.nav_stats.setChecked(index == 2)
        self.nav_settings.setChecked(index == 3)

        # 切换到统计页面时刷新数据
        if index == 2:
            self.stats_panel.refresh()

        # 页面切换动效：新页面轻微上移淡入，说明「内容换了」而不是
        # 「窗口闪了一下」。不做横向滑动 —— 四个页面是平级关系，
        # 滑动会暗示它们有先后顺序，那是假的。
        page = self.stack.currentWidget()
        if page is not None:
            rise_in(page, duration="space", distance=10)
    
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
            # 文案不变，只加指示器 —— 换文案会让按钮宽度收缩，
            # 右侧控件被顶得挪位置，布局在等待期间抖一下
            self._set_record_button_loading(True)
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
    
    def _on_recording_pill_clicked(self):
        """点击录制状态胶囊快捷操作"""
        if self.recording_manager and self.recording_manager.is_recording:
            self._toggle_pause()
        else:
            self._toggle_recording()
    
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
            # 进度回调在调度线程里被调用，必须切回主线程才能碰 UI
            self.analysis_manager = AnalysisManager(
                self.storage,
                progress_callback=self._on_analysis_progress,
            )
        
        self.analysis_manager.start_scheduler()
        logger.info("分析调度器已启动")

    def _on_analysis_progress(self, done: int, total: int):
        """
        分析进度回调（运行在调度线程）。

        Qt 控件只能在主线程操作，这里把信号排队回主线程。
        分析每分钟才推进几个批次，节流一下避免刷新风暴。
        """
        from PySide6.QtCore import QMetaObject, Qt as _Qt, Q_ARG

        if getattr(self, "_last_progress_emit", None) == (done, total):
            return
        self._last_progress_emit = (done, total)

        QMetaObject.invokeMethod(
            self,
            "_apply_analysis_progress",
            _Qt.QueuedConnection,
            Q_ARG(int, done),
            Q_ARG(int, total),
        )

    @Slot(int, int)
    def _apply_analysis_progress(self, done: int, total: int):
        """把进度应用到时间轴（主线程）"""
        try:
            self.timeline_view.set_analysis_progress(done, total)
        except Exception as e:
            logger.debug(f"更新分析进度显示失败: {e}")

    def _stop_analysis(self):
        """停止分析调度器"""
        if self.analysis_manager:
            self.analysis_manager.stop_scheduler()
            logger.info("分析调度器已停止")
    
    @Slot()
    def _on_recording_stopped(self):
        """录制停止后的 UI 更新（在主线程中调用）"""
        self._stopping = False  # 重置停止标志
        self._set_record_button_loading(False)
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
                    color: #FFFFFF;
                    border: none;
                    border-radius: 9999px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {t.error};
                }}
                QPushButton:focus {{
                    border: 2px solid {t.accent_focus};
                    background-color: {t.error};
                }}
            """)
        else:
            self.record_btn.setText("● 开始录制")
            self.record_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t.accent};
                    color: #FFFFFF;
                    border: none;
                    border-radius: 9999px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {t.accent_hover};
                }}
                QPushButton:focus {{
                    border: 2px solid {t.accent_focus};
                    background-color: {t.accent_hover};
                }}
            """)
    
    def _set_record_button_loading(self, loading: bool):
        """
        停止录制过程中的等待态。

        关键约束：按钮宽度不能变。原来的做法把文案换成「停止中...」，
        宽度随之收缩，右侧控件会被顶得挪位置 —— 布局在等待期间抖一下。
        这里保持原文案不变，只在文字左侧叠一个指示器。

        指示器是手动定位的子控件，不能给按钮加 layout：QPushButton 一旦
        有了 layout，它就不再自己居中绘制文字，指示器会把文字挤到一边。
        """
        if loading:
            if self.record_btn.isEnabled():
                self.record_btn.setEnabled(False)
            self.record_btn.setToolTip("正在保存数据并结束录制，请稍候")
            if self._record_spinner is None:
                self._record_spinner = SpinnerDot(self.record_btn, "#FFFFFF", 14)
            self._record_spinner.setFixedSize(14, 14)
            self._record_spinner.show()
            self._record_spinner.raise_()
            self._position_record_spinner()
            self._record_spinner.start()
        else:
            if self._record_spinner is not None:
                self._record_spinner.stop()
                self._record_spinner.hide()
                self._record_spinner.setParent(None)
                self._record_spinner = None
            if not self.record_btn.isEnabled():
                self.record_btn.setEnabled(True)
            self.record_btn.setToolTip("")

    def _position_record_spinner(self):
        """把指示器放到按钮文字左侧，保持按钮整体居中不变"""
        if self._record_spinner is None:
            return
        btn = self.record_btn
        metrics = btn.fontMetrics()
        text_w = metrics.horizontalAdvance(btn.text())
        cx = btn.width() / 2.0
        dot = self._record_spinner.width()
        x = int(cx - text_w / 2.0 - dot - 8)
        y = int((btn.height() - dot) / 2.0)
        self._record_spinner.move(max(6, x), y)
    
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
        
        # 同步 Windows 11 DWM 标题与边框暗色模式
        apply_dwm_window_attributes(int(self.winId()), is_dark=(t.name == "dark"))
    
    def _on_stats_date_clicked(self, date: datetime):
        """点击统计页面的打卡方格，跳转至时间轴并查看当日详情"""
        self.timeline_view.set_date(date)
        cards = self.storage.get_cards_for_date(date)
        self.timeline_view.set_cards(cards)
        self._switch_page(0)
    
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
            # 失败要说清发生了什么、下一步做什么
            QMessageBox.warning(
                self, "删除失败",
                "这条活动记录没能从数据库中删除。\n\n"
                "可能是数据库正被占用。关闭其他 Dayflow 窗口后重试，"
                "或查看日志了解详情。"
            )
    
    def _on_card_restored(self, card: ActivityCard):
        """
        撤销删除：把记录写回数据库。

        只更新界面是不够的 —— 刷新一次数据就会发现卡片又消失了，
        那比不支持撤销更糟。
        """
        try:
            self.storage.save_card(card)
            logger.info(f"卡片已恢复: {card.id}")
        except Exception as e:
            logger.error(f"恢复卡片失败: {e}")
            # 恢复失败必须告诉用户，否则界面和数据库会不一致
            QMessageBox.warning(
                self, "恢复失败",
                f"「{card.title or '这条记录'}」没能恢复到数据库。\n\n"
                "刷新后它会再次消失。原因见日志。"
            )
    
    def _start_recording_from_empty(self):
        """空状态里的「开始录制」"""
        if self.recording_manager and self.recording_manager.is_recording:
            self._switch_page(0)
            self._sync_recording_ui_state()
            return
        self._toggle_recording()
    
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
