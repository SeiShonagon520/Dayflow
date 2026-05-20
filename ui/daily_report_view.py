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
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QClipboard, QGuiApplication

from ui.themes import get_theme, get_theme_manager
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

        self.copy_btn = QPushButton("📋 复制内容")
        self.copy_btn.setFixedHeight(34)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.clicked.connect(self._on_copy_clicked)
        self.copy_btn.setEnabled(False)
        action_bar.addWidget(self.copy_btn)

        self.export_btn = QPushButton("💾 导出文件")
        self.export_btn.setFixedHeight(34)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.export_btn.setEnabled(False)
        action_bar.addWidget(self.export_btn)

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
        else:
            self.report_browser.setPlaceholderText(f"{date_str} 的日报尚未生成。")
            self.report_browser.clear()
            self.copy_btn.setEnabled(False)
            self.export_btn.setEnabled(False)

    def _on_generate_clicked(self):
        """点击生成日报"""
        qdate = self.date_edit.date()
        date = datetime(qdate.year(), qdate.month(), qdate.day())
        self.generate_report_requested.emit(date)

    def _on_copy_clicked(self):
        """复制日报内容到剪贴板"""
        content = self.report_browser.toPlainText()
        if content:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(content)
            QMessageBox.information(self, "成功", "日报内容已复制到剪贴板")

    def _on_export_clicked(self):
        """导出日报为文件"""
        if not self._current_date_str:
            return

        content = self.report_browser.toPlainText()
        if not content:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出日报", f"日报_{self._current_date_str}.md",
            "Markdown 文件 (*.md);;文本文件 (*.txt)"
        )
        if file_path:
            try:
                Path(file_path).write_text(content, encoding="utf-8")
                QMessageBox.information(self, "成功", f"日报已导出到：{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "失败", f"导出失败：{e}")

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
