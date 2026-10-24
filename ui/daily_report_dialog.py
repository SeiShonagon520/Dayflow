"""
Dayflow Windows - 日报预览与导出对话框
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextBrowser, QApplication, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt
from ui.themes import get_theme, get_markdown_stylesheet
from ui.components.motion_dialog import MotionDialog
from ui.components.scale_feedback import FeedbackButton


class DailyReportDialog(MotionDialog):
    """日报展示对话框"""

    def __init__(self, date_str: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"📋 工作日报 - {date_str}")
        self.setMinimumSize(680, 520)
        self.resize(760, 620)
        self.setModal(True)
        self._content = content
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # 内容区
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.document().setDefaultStyleSheet(get_markdown_stylesheet())
        self.text_browser.setMarkdown(self._content)
        layout.addWidget(self.text_browser)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        copy_btn = FeedbackButton("📋 复制到剪贴板")
        copy_btn.setFixedHeight(34)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(copy_btn)

        export_btn = FeedbackButton("💾 导出为文件")
        export_btn.setFixedHeight(34)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_to_file)
        btn_layout.addWidget(export_btn)

        close_btn = FeedbackButton("关闭")
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

    def _apply_theme(self):
        t = get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t.bg_primary};
            }}
            QTextBrowser {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 10px;
                padding: 16px;
            }}
            QPushButton {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 0 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
                border-color: {t.accent};
            }}
        """)
        self.text_browser.document().setDefaultStyleSheet(get_markdown_stylesheet(t))
