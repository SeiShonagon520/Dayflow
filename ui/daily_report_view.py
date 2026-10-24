"""
Dayflow Windows - 日报视图
展示、生成和管理每日工作报告
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextBrowser, QDateEdit, QListWidget, QListWidgetItem,
    QMessageBox, QFileDialog, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QClipboard, QGuiApplication

from ui.themes import get_theme, get_theme_manager, get_markdown_stylesheet
from ui.components.scale_feedback import FeedbackButton
from database.storage import StorageManager

logger = logging.getLogger(__name__)


class DailyReportView(QWidget):
    """日报视图 - 浏览和管理每日工作报告"""

    generate_report_requested = Signal(datetime)

    def __init__(self, storage: StorageManager, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._current_date_str: Optional[str] = None
        self._setup_ui()
        self._load_report_dates()
        self.apply_theme()

        get_theme_manager().theme_changed.connect(self.apply_theme)

    def _setup_ui(self):
        """初始化界面"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # ===== 左侧：日期列表 =====
        left_frame = QFrame()
        left_frame.setObjectName("settingsCard")
        left_frame.setFixedWidth(220)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        left_title = QLabel("📋 日报历史")
        left_title.setObjectName("cardTitle")
        left_layout.addWidget(left_title)

        self.date_list = QListWidget()
        self.date_list.setFixedHeight(360)
        self.date_list.itemClicked.connect(self._on_date_selected)
        left_layout.addWidget(self.date_list)

        left_layout.addStretch()
        main_layout.addWidget(left_frame)

        # ===== 右侧：日报内容区 =====
        right_frame = QFrame()
        right_frame.setObjectName("settingsCard")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        toolbar_title = QLabel("📋 工作日报")
        toolbar_title.setObjectName("cardTitle")
        toolbar.addWidget(toolbar_title)
        toolbar.addStretch()

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate().addDays(-1))
        self.date_edit.setFixedHeight(34)
        self.date_edit.setFixedWidth(140)
        toolbar.addWidget(self.date_edit)

        self.generate_btn = QPushButton("✨ 生成日报")
        self.generate_btn.setFixedHeight(34)
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        toolbar.addWidget(self.generate_btn)

        right_layout.addLayout(toolbar)

        # 日报内容区
        self.report_browser = QTextBrowser()
        self.report_browser.setOpenExternalLinks(True)
        self.report_browser.setPlaceholderText(
            "选择左侧日期查看已生成的日报，或选择日期后点击「生成日报」。"
        )
        right_layout.addWidget(self.report_browser)

        # 底部操作栏
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)
        action_bar.addStretch()
        self._action_bar = action_bar

        # 命中区 40px：视觉高度 34 不变，靠布局留白把可点区域撑起来，
        # 这样按钮看起来依然紧凑，但手指/鼠标不需要精准点中。
        self.copy_btn = FeedbackButton("📋 复制内容")
        self.copy_btn.setFixedHeight(34)
        self.copy_btn.setMinimumWidth(104)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setToolTip("复制这篇日报的全文")
        self.copy_btn.clicked.connect(self._on_copy_clicked)
        self.copy_btn.setEnabled(False)
        action_bar.addWidget(self.copy_btn)

        self.export_btn = FeedbackButton("💾 导出文件")
        self.export_btn.setFixedHeight(34)
        self.export_btn.setMinimumWidth(104)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setToolTip("把这篇日报导出为 Markdown 文件")
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.export_btn.setEnabled(False)
        action_bar.addWidget(self.export_btn)

        # 操作结果提示：替换掉「点完弹个模态框」的做法
        self._status_label = QLabel("")
        self._status_label.setObjectName("cardDesc")
        self._status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._status_label.setVisible(False)
        action_bar.addWidget(self._status_label)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._status_label.setVisible)

        right_layout.addLayout(action_bar)

        main_layout.addWidget(right_frame, 1)

    def apply_theme(self):
        """应用主题"""
        t = get_theme()

        self.setStyleSheet(f"""
            QFrame#settingsCard {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 12px;
            }}
            QLabel#cardTitle {{
                color: {t.text_primary};
                font-size: 16px;
                font-weight: bold;
            }}
            QTextBrowser {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                line-height: 1.6;
            }}
            QListWidget {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background-color: {t.accent};
                color: white;
            }}
            QListWidget::item:hover {{
                background-color: {t.bg_tertiary};
            }}
            QDateEdit {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 4px 8px;
            }}
        """)
        # 注入现代高质感 Markdown 排版样式
        self.report_browser.document().setDefaultStyleSheet(get_markdown_stylesheet(t))

    def _load_report_dates(self):
        """加载已有日报的日期列表"""
        self.date_list.clear()
        try:
            dates = self._get_report_dates()
            for date_str in dates:
                item = QListWidgetItem(date_str)
                self.date_list.addItem(item)
        except Exception as e:
            logger.warning(f"加载日报日期列表失败: {e}")

    def _get_report_dates(self) -> List[str]:
        """从数据库获取所有已生成日报的日期"""
        import sqlite3
        dates = []
        try:
            conn = sqlite3.connect(str(self.storage.db_path), timeout=5.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT report_date FROM daily_reports ORDER BY report_date DESC"
            )
            for row in cursor.fetchall():
                dates.append(row["report_date"])
            conn.close()
        except Exception as e:
            logger.warning(f"查询日报日期失败: {e}")
        return dates

    def _on_date_selected(self, item: QListWidgetItem):
        """点击左侧日期列表"""
        date_str = item.text()
        self._load_report(date_str)
        # 同步日期选择器
        try:
            year, month, day = map(int, date_str.split("-"))
            self.date_edit.setDate(QDate(year, month, day))
        except ValueError:
            pass

    def _load_report(self, date_str: str):
        """加载指定日期的日报"""
        self._current_date_str = date_str
        content = self.storage.get_daily_report(date_str)

        if content:
            self.report_browser.setMarkdown(content)
            self.copy_btn.setEnabled(True)
            self.export_btn.setEnabled(True)
            self.copy_btn.setToolTip("复制这篇日报的全文")
            self.export_btn.setToolTip("把这篇日报导出为 Markdown 文件")
        else:
            self.report_browser.clear()
            # 空状态要说明「为什么空」和「接下来做什么」，
            # 不能只把按钮变灰让用户自己猜。
            self.report_browser.setHtml(self._empty_report_html(date_str))
            self.copy_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            # 禁用原因写在 tooltip 里：灰按钮本身不会自解释
            self.copy_btn.setToolTip(f"{date_str} 的日报尚未生成，无法复制")
            self.export_btn.setToolTip(f"{date_str} 的日报尚未生成，无法导出")

    def _empty_report_html(self, date_str: str) -> str:
        """日报为空时的引导内容"""
        from ui.themes import get_theme
        t = get_theme()
        return f"""
        <div style="color:{t.text_muted}; font-size:14px; line-height:1.7;
                    padding:32px; text-align:center;">
            <div style="font-size:32px; margin-bottom:12px;">📋</div>
            <div style="color:{t.text_primary}; font-size:15px; font-weight:600;
                        margin-bottom:8px;">{date_str} 还没有日报</div>
            <div>点击上方「生成日报」让 AI 汇总这一天的活动。<br/>
                 如果时间轴还是空的，先开始录制。</div>
        </div>
        """

    def _on_generate_clicked(self):
        """点击生成日报"""
        qdate = self.date_edit.date()
        date = datetime(qdate.year(), qdate.month(), qdate.day())
        self.generate_report_requested.emit(date)

    def _on_copy_clicked(self):
        """复制日报内容到剪贴板"""
        content = self.report_browser.toPlainText().strip()
        if not content:
            # 静默失败是最差的体验：点了没反应，用户会以为程序卡了
            QMessageBox.information(
                self, "没有可复制的内容",
                "当前这篇日报还没有内容。\n\n"
                "先点击「生成日报」，或从左侧选择一篇已有的日报。"
            )
            return
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(content)
        self._flash_status("已复制到剪贴板")

    def _flash_status(self, message: str):
        """在操作栏里短暂显示结果，替代弹模态框"""
        self._status_label.setText(message)
        self._status_label.setVisible(True)
        self._status_timer.start(2600)

    def _on_export_clicked(self):
        """导出日报为文件"""
        if not self._current_date_str:
            QMessageBox.information(
                self, "没有选择日报",
                "先从左侧选择一篇日报，或点击「生成日报」创建一篇。"
            )
            return

        content = self.report_browser.toPlainText().strip()
        if not content:
            QMessageBox.information(
                self, "没有可导出的内容",
                f"{self._current_date_str} 的日报还没有内容。\n\n"
                "先点击「生成日报」让 AI 汇总这一天的活动。"
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出日报", f"日报_{self._current_date_str}.md",
            "Markdown 文件 (*.md);;文本文件 (*.txt)"
        )
        if not file_path:
            # 用户主动取消，不是错误，不该弹任何提示
            return
        try:
            Path(file_path).write_text(content, encoding="utf-8")
            self._flash_status("已导出")
        except Exception as e:
            # 错误要说清发生了什么、下一步做什么
            QMessageBox.critical(
                self, "导出失败",
                f"无法写入文件：\n{file_path}\n\n"
                f"原因：{e}\n\n"
                "请确认路径有效且文件未被其他程序占用，或换一个位置再试。"
            )

    def show_report(self, date_str: str, content: str):
        """外部调用：展示日报内容"""
        self._current_date_str = date_str
        self.report_browser.setMarkdown(content)
        self.copy_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        # 刷新日期列表
        self._load_report_dates()
        # 高亮对应日期
        for i in range(self.date_list.count()):
            item = self.date_list.item(i)
            if item.text() == date_str:
                self.date_list.setCurrentItem(item)
                break

    def show_error(self, message: str):
        """外部调用：展示错误信息"""
        self.report_browser.setPlaceholderText(message)
        self.report_browser.clear()
        self.copy_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
