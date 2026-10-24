"""
Dayflow Windows - 时间轴视图组件
"""
from datetime import datetime, timedelta
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy, QProgressBar,
    QPushButton, QFileDialog, QLineEdit, QDialog, QComboBox,
    QSpinBox, QMenu, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve, QTimer, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPalette, QLinearGradient, QPainter, QBrush, QPen, QAction

from core.types import ActivityCard
from ui.components.scale_feedback import FeedbackButton
from ui.components.motion_dialog import MotionDialog
from ui.components.snackbar import Snackbar
from ui.motion import (
    rise_in, collapse_out, collapse_height, expand_height, flash,
    stagger_delays, animate_property,
)
from ui.themes import (
    get_theme_manager,
    get_theme,
    get_efficiency_color,
    get_category_color,
    with_alpha,
    RADIUS,
)


class CardEditDialog(MotionDialog):
    """卡片编辑对话框"""
    
    card_updated = Signal(object)  # 发送更新后的卡片
    card_deleted = Signal(int)     # 发送删除的卡片 ID
    
    # 可选类别列表
    CATEGORIES = ["工作", "学习", "编程", "会议", "娱乐", "社交", "休息", "其他"]
    
    def __init__(self, card: 'ActivityCard', parent=None):
        super().__init__(parent)
        self.card = card
        self.setWindowTitle("编辑活动")
        self.setMinimumWidth(450)
        self.setModal(True)
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 时间信息（只读）
        time_label = QLabel(self._format_time())
        time_label.setObjectName("timeInfo")
        layout.addWidget(time_label)
        
        # 类别选择
        cat_layout = QHBoxLayout()
        cat_label = QLabel("类别")
        cat_label.setFixedWidth(80)
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.CATEGORIES)
        # 设置当前类别
        if self.card.category in self.CATEGORIES:
            self.category_combo.setCurrentText(self.card.category)
        else:
            self.category_combo.setCurrentText("其他")
        cat_layout.addWidget(cat_label)
        cat_layout.addWidget(self.category_combo)
        layout.addLayout(cat_layout)
        
        # 标题输入
        title_layout = QHBoxLayout()
        title_label = QLabel("标题")
        title_label.setFixedWidth(80)
        self.title_input = QLineEdit(self.card.title or "")
        self.title_input.setPlaceholderText("活动标题")
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.title_input)
        layout.addLayout(title_layout)
        
        # 摘要输入
        summary_layout = QVBoxLayout()
        summary_label = QLabel("摘要")
        self.summary_input = QTextEdit()
        self.summary_input.setPlainText(self.card.summary or "")
        self.summary_input.setPlaceholderText("活动摘要描述")
        self.summary_input.setMaximumHeight(100)
        summary_layout.addWidget(summary_label)
        summary_layout.addWidget(self.summary_input)
        layout.addLayout(summary_layout)
        
        # 生产力评分
        score_layout = QHBoxLayout()
        score_label = QLabel("效率评分")
        score_label.setFixedWidth(80)
        self.score_spin = QSpinBox()
        self.score_spin.setRange(0, 100)
        self.score_spin.setValue(int(self.card.productivity_score))
        self.score_spin.setSuffix(" %")
        self.score_spin.setMinimumWidth(120)
        self.score_spin.setFixedHeight(40)  # 固定高度
        score_layout.addWidget(score_label)
        score_layout.addWidget(self.score_spin)
        score_layout.addStretch()
        layout.addLayout(score_layout)
        
        # 应用列表（只读）
        if self.card.app_sites:
            apps_label = QLabel("应用程序")
            apps_text = ", ".join([app.name for app in self.card.app_sites[:5]])
            if len(self.card.app_sites) > 5:
                apps_text += f" (+{len(self.card.app_sites) - 5})"
            apps_value = QLabel(apps_text)
            apps_value.setObjectName("appsInfo")
            apps_value.setWordWrap(True)
            layout.addWidget(apps_label)
            layout.addWidget(apps_value)
        
        layout.addStretch()
        
        # 按钮行
        btn_layout = QHBoxLayout()
        
        # 删除按钮
        self.delete_btn = QPushButton("🗑️ 删除")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self.delete_btn)
        
        btn_layout.addStretch()
        
        # 取消按钮
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        # 保存按钮
        self.save_btn = QPushButton("保存")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)
        
        layout.addLayout(btn_layout)
    
    def _format_time(self) -> str:
        """格式化时间范围"""
        if self.card.start_time and self.card.end_time:
            start = self.card.start_time.strftime("%Y-%m-%d %H:%M")
            end = self.card.end_time.strftime("%H:%M")
            duration = self.card.duration_minutes
            if duration >= 60:
                hours = int(duration // 60)
                mins = int(duration % 60)
                dur_str = f"{hours}h {mins}m" if mins else f"{hours}h"
            else:
                dur_str = f"{int(duration)}m"
            return f"🕐 {start} - {end} ({dur_str})"
        return ""
    
    def _on_save(self):
        """保存修改"""
        # 更新卡片对象
        self.card.category = self.category_combo.currentText()
        self.card.title = self.title_input.text().strip()
        self.card.summary = self.summary_input.toPlainText().strip()
        self.card.productivity_score = self.score_spin.value()
        
        self.card_updated.emit(self.card)
        self.accept()
    
    def _on_delete(self):
        """删除卡片"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除这条活动记录吗？\n\n「{self.card.title or '未命名活动'}」\n\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.card_deleted.emit(self.card.id)
            self.accept()
    
    def apply_theme(self):
        t = get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t.bg_primary};
            }}
            QLabel {{
                color: {t.text_primary};
                font-size: 14px;
            }}
            QLabel#timeInfo {{
                color: {t.text_muted};
                font-size: 13px;
                padding: 8px 0;
            }}
            QLabel#appsInfo {{
                color: {t.text_secondary};
                font-size: 12px;
                padding: 4px 0;
            }}
            QLineEdit, QTextEdit {{
                background-color: {t.bg_tertiary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 10px;
                color: {t.text_primary};
                font-size: 14px;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {t.accent};
            }}
            QComboBox {{
                background-color: {t.bg_tertiary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                color: {t.text_primary};
                font-size: 14px;
            }}
            QComboBox:hover {{
                border-color: {t.accent};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                selection-background-color: {t.accent_light};
            }}
            QSpinBox {{
                background-color: {t.bg_tertiary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 16px;
                color: {"#000000" if t.name == "light" else "#FFFFFF"};
                font-size: 14px;
                font-weight: 500;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                min-width: 80px;
            }}
            QSpinBox:focus {{
                border-color: {t.accent};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 20px;
            }}
        """)
        
        # 删除按钮 - 红色
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.error};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #FF6961;
            }}
        """)
        
        # 取消按钮
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
            }}
        """)
        
        # 保存按钮 - 强调色
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.accent};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {t.accent_hover};
            }}
        """)


class StatsSummaryWidget(QFrame):
    """统计汇总组件 - 显示时间分布（可折叠）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = {}  # category -> minutes
        self._total_minutes = 0
        self._collapsed = False
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        self.setObjectName("statsSummary")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        
        # 标题栏（可点击折叠）
        title_layout = QHBoxLayout()
        self.title_label = QLabel("📊 时间分布")
        title_layout.addWidget(self.title_label)
        
        self.total_label = QLabel("0h 0m")
        title_layout.addWidget(self.total_label)
        title_layout.addStretch()
        
        # 折叠按钮：28px 的可见尺寸对鼠标偏小，直接做成 40px 命中区。
        # 这个控件周围没有密集邻接，放大不会造成误点。
        self.collapse_btn = FeedbackButton("▼")
        self.collapse_btn.setFixedSize(40, 40)
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.setAccessibleName("折叠活动明细")
        self.collapse_btn.setToolTip("折叠")
        self.collapse_btn.clicked.connect(self._toggle_collapse)
        title_layout.addWidget(self.collapse_btn)
        
        layout.addLayout(title_layout)
        
        # 图表容器（用于折叠）- 详细列表
        self.chart_widget = QWidget()
        self.chart_container = QVBoxLayout(self.chart_widget)
        self.chart_container.setContentsMargins(0, 0, 0, 0)
        self.chart_container.setSpacing(8)
        layout.addWidget(self.chart_widget)
    
    def _toggle_collapse(self):
        """
        切换折叠状态。

        这里需要动效：空间在变大变小，眼睛得跟着走。
        瞬变会让用户丢失「刚才那块东西去哪了」。
        """
        self._collapsed = not self._collapsed
        self.collapse_btn.setText("▶" if self._collapsed else "▼")
        
        # 提示与可访问名称都要跟着翻转：图标变了，说法也得变
        label = "展开活动明细" if self._collapsed else "折叠活动明细"
        self.collapse_btn.setToolTip(label)
        self.collapse_btn.setAccessibleName(label)
        
        if self._collapsed:
            collapse_height(self.chart_widget)
        else:
            expand_height(self.chart_widget)
    
    def apply_theme(self):
        """应用主题"""
        t = get_theme()
        self.setStyleSheet(f"""
            QFrame#statsSummary {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 12px;
            }}
        """)
        self.title_label.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 600;
            color: {t.text_primary};
        """)
        self.total_label.setStyleSheet(f"""
            font-size: 13px;
            color: {t.text_muted};
        """)
        # 折叠按钮样式 - 更明显
        self.collapse_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
                border-color: {t.accent};
            }}
        """)
        
        # 重新生成图表以应用新主题
        if self._data:
            self._regenerate_bars()
    
    def _regenerate_bars(self):
        """重新生成所有柱状图"""
        # 清除现有柱状图
        while self.chart_container.count():
            item = self.chart_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self._data:
            return
        
        # 按时间排序并重新创建
        sorted_data = sorted(self._data.items(), key=lambda x: x[1], reverse=True)
        for category, minutes in sorted_data:
            self._add_bar(category, minutes)
    
    def set_data(self, cards: list):
        """根据卡片数据设置统计 - 优化版本"""
        # 统计各类别时间
        new_data = {}
        for card in cards:
            category = card.category or "其他"
            minutes = card.duration_minutes
            new_data[category] = new_data.get(category, 0) + minutes
        
        # 如果数据没变化，跳过更新
        if new_data == self._data:
            return
        
        self._data = new_data
        self._total_minutes = sum(self._data.values())
        
        # 更新总时间
        hours = int(self._total_minutes // 60)
        mins = int(self._total_minutes % 60)
        self.total_label.setText(f"共 {hours}h {mins}m")
        
        # 暂停更新以减少重绘
        self.chart_widget.setUpdatesEnabled(False)
        
        try:
            # 清除旧数据
            while self.chart_container.count():
                item = self.chart_container.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            if not self._data:
                t = get_theme()
                empty = QLabel("暂无数据")
                empty.setStyleSheet(f"color: {t.text_muted}; font-size: 13px;")
                self.chart_container.addWidget(empty)
                return
            
            # 按时间排序
            sorted_data = sorted(self._data.items(), key=lambda x: x[1], reverse=True)
            
            # 创建柱状图
            for category, minutes in sorted_data:
                self._add_bar(category, minutes)
        finally:
            self.chart_widget.setUpdatesEnabled(True)
    
    def _add_bar(self, category: str, minutes: float):
        """添加一个统计条"""
        t = get_theme()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        
        # 类别名 - 使用主题文字颜色
        cat_label = QLabel(category)
        cat_label.setFixedWidth(60)
        cat_label.setStyleSheet(f"""
            font-size: 12px;
            color: {t.text_primary};
        """)
        row_layout.addWidget(cat_label)
        
        # 进度条
        percentage = (minutes / self._total_minutes * 100) if self._total_minutes > 0 else 0
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(percentage))
        bar.setTextVisible(False)
        bar.setFixedHeight(12)
        
        color = get_category_color(category)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {t.bg_tertiary};
                border: none;
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 6px;
            }}
        """)
        row_layout.addWidget(bar, 1)
        
        # 时间
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        time_str = f"{hours}h {mins}m" if hours else f"{mins}m"
        time_label = QLabel(time_str)
        time_label.setFixedWidth(50)
        time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        time_label.setStyleSheet(f"""
            font-size: 12px;
            color: {t.text_muted};
        """)
        row_layout.addWidget(time_label)
        
        self.chart_container.addWidget(row)


class TimelineSpineWidget(QWidget):
    """时间轴左侧刻度与轨道连线组件"""
    
    def __init__(self, card: ActivityCard, parent=None):
        super().__init__(parent)
        self.card = card
        self.setFixedWidth(72)
        get_theme_manager().theme_changed.connect(self.update)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        t = get_theme()
        
        rail_x = 58.0
        h = float(self.height())
        node_y = 26.0
        
        # 1. 垂直轨道导线
        rail_pen = QPen(QColor(t.border), 2)
        painter.setPen(rail_pen)
        painter.drawLine(QPointF(rail_x, 0), QPointF(rail_x, h))
        
        # 2. 节点与卡片连接分支线
        branch_pen = QPen(QColor(t.border), 1.5)
        painter.setPen(branch_pen)
        painter.drawLine(QPointF(rail_x, node_y), QPointF(float(self.width()), node_y))
        
        # 3. 节点圆点 (类别对应颜色)
        cat_color = QColor(get_category_color(self.card.category))
        
        # 深度工作 (duration >= 60m) 外环光晕
        if self.card.duration_minutes >= 60:
            halo_pen = QPen(QColor("#FF6B6B"), 2)
            painter.setPen(halo_pen)
            painter.setBrush(QBrush(QColor(t.bg_primary)))
            painter.drawEllipse(QPointF(rail_x, node_y), 8.5, 8.5)
            
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(cat_color))
            painter.drawEllipse(QPointF(rail_x, node_y), 4.5, 4.5)
        else:
            painter.setPen(QPen(QColor(t.bg_primary), 2))
            painter.setBrush(QBrush(cat_color))
            painter.drawEllipse(QPointF(rail_x, node_y), 5.5, 5.5)
            
        # 4. 时间与时长文字
        if self.card.start_time:
            time_str = self.card.start_time.strftime("%H:%M")
            dur = self.card.duration_minutes
            if dur >= 60:
                h_dur = int(dur // 60)
                m_dur = int(dur % 60)
                dur_str = f"{h_dur}h{m_dur}m" if m_dur else f"{h_dur}h"
            else:
                dur_str = f"{int(dur)}m"
                
            # 时间：等宽加粗
            painter.setFont(QFont("Cascadia Code", 10, QFont.Bold))
            painter.setPen(QColor(t.text_primary))
            painter.drawText(QRectF(0, node_y - 18, rail_x - 12, 18), Qt.AlignRight | Qt.AlignVCenter, time_str)
            
            # 时长：弱化小字
            painter.setFont(QFont("Segoe UI Variable Text", 9))
            painter.setPen(QColor(t.text_muted))
            painter.drawText(QRectF(0, node_y + 2, rail_x - 12, 16), Qt.AlignRight | Qt.AlignVCenter, dur_str)


class TimelineGapSpineWidget(QWidget):
    """时间轴空闲时段左侧虚线轨道"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(72)
        get_theme_manager().theme_changed.connect(self.update)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        t = get_theme()
        
        rail_pen = QPen(QColor(t.border), 1.5, Qt.DashLine)
        painter.setPen(rail_pen)
        painter.drawLine(QPointF(58.0, 0), QPointF(58.0, float(self.height())))


class TimelineGapWidget(QWidget):
    """时间轴空闲 / 离开时段胶囊组件"""
    
    def __init__(self, start_time: datetime, end_time: datetime, gap_minutes: float, parent=None):
        super().__init__(parent)
        self.start_time = start_time
        self.end_time = end_time
        self.gap_minutes = gap_minutes
        self.setFixedHeight(36)
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
        
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 左侧虚线轨道
        self.spine = TimelineGapSpineWidget()
        layout.addWidget(self.spine)
        
        # 右侧胶囊卡片
        h = int(self.gap_minutes // 60)
        m = int(self.gap_minutes % 60)
        dur_str = f"{h}小时 {m}分钟" if h > 0 else f"{m}分钟"
        range_str = f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
        
        self.pill = QLabel(f"⏸️ 空闲 / 暂离 {dur_str}  ·  {range_str}")
        self.pill.setObjectName("gapPill")
        layout.addWidget(self.pill)
        layout.addStretch()
        
    def apply_theme(self):
        t = get_theme()
        is_dark = (t.name == "dark")
        bg = "rgba(255, 255, 255, 0.03)" if is_dark else "rgba(15, 23, 42, 0.03)"
        self.pill.setStyleSheet(f"""
            QLabel#gapPill {{
                background-color: {bg};
                border: 1px dashed {t.border};
                border-radius: 12px;
                color: {t.text_muted};
                font-size: 12px;
                padding: 4px 14px;
                font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
            }}
        """)


class CategoryFilterBar(QWidget):
    """分类筛选胶囊栏组件"""
    
    category_selected = Signal(str)  # 选中的类别名称，"" 表示全部
    
    CATEGORY_ICONS = {
        "全部": "✨",
        "工作": "📝",
        "学习": "📚",
        "编程": "💻",
        "会议": "👥",
        "娱乐": "🎮",
        "社交": "💬",
        "休息": "☕",
        "其他": "📦",
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts = {}
        self._current_category = ""
        self._buttons = {}
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
        
    def _setup_ui(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(24, 0, 24, 8)
        self.layout.setSpacing(8)
        self._rebuild_buttons()
        
    def _rebuild_buttons(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()
        
        categories = ["全部"]
        standard_cats = ["工作", "编程", "学习", "会议", "娱乐", "休息"]
        for cat in standard_cats:
            if cat not in categories:
                categories.append(cat)
        for cat in self._counts.keys():
            if cat and cat not in categories:
                categories.append(cat)
                
        for cat in categories:
            count = self._counts.get(cat, 0)
            if cat == "全部":
                count = sum(self._counts.values())
            icon = self.CATEGORY_ICONS.get(cat, "🏷️")
            label = f"{icon} {cat} ({count})" if count > 0 else f"{icon} {cat}"
            btn = FeedbackButton(label)
            btn.setCheckable(True)
            target = "" if cat == "全部" else cat
            btn.setChecked(self._current_category == target)
            btn.setCursor(Qt.PointingHandCursor)
            # 40px 命中区：药丸是高频点击目标，32px 在触控板上容易点偏
            btn.setFixedHeight(40)
            # 药丸只靠颜色表示选中，读屏用户无从判断；名称里带上数量和状态
            count_txt = f"，{count} 项" if count else "，暂无记录"
            btn.setAccessibleName(f"筛选 {cat}{count_txt}")
            btn.clicked.connect(lambda checked=False, c=cat: self._on_btn_clicked(c))
            self.layout.addWidget(btn)
            self._buttons[cat] = btn
            
        self.layout.addStretch()
        self.apply_theme()
        
    def _on_btn_clicked(self, category: str):
        target = "" if category == "全部" else category
        self._current_category = target
        for cat, btn in self._buttons.items():
            btn.setChecked(cat == category)
        self.category_selected.emit(target)
        self.apply_theme()
        
    def update_counts(self, cards: List[ActivityCard]):
        counts = {}
        for c in cards:
            cat = c.category or "其他"
            counts[cat] = counts.get(cat, 0) + 1
        self._counts = counts
        self._rebuild_buttons()
        
    def apply_theme(self):
        t = get_theme()
        for cat, btn in self._buttons.items():
            is_active = (self._current_category == ("" if cat == "全部" else cat))
            if is_active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {t.accent};
                        color: #FFFFFF;
                        border: 1px solid {t.accent};
                        border-radius: 9999px;
                        padding: 4px 14px;
                        font-size: 12px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{
                        background-color: {t.accent_hover};
                    }}
                    QPushButton:focus {{
                        border: 2px solid {t.accent_focus};
                        padding: 3px 13px;
                    }}
                """)
            else:
                # 未选中：Apple 幽灵药丸 —— 白底 + 发丝线，不抢注意力
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {t.pill_bg};
                        color: {t.text_secondary};
                        border: 1px solid {t.border};
                        border-radius: 9999px;
                        padding: 4px 14px;
                        font-size: 12px;
                        font-weight: 500;
                    }}
                    QPushButton:hover {{
                        background-color: {t.bg_hover};
                        color: {t.text_primary};
                        border-color: {t.border_hover};
                    }}
                    QPushButton:focus {{
                        border: 2px solid {t.accent_focus};
                        padding: 3px 13px;
                    }}
                """)


class ActivityCardWidget(QFrame):
    """单个活动卡片组件"""
    
    clicked = Signal(ActivityCard)
    edit_requested = Signal(ActivityCard)
    delete_requested = Signal(int)  # card_id
    
    def __init__(self, card: ActivityCard, parent=None):
        super().__init__(parent)
        self.card = card
        self._setup_ui()
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        # 键盘可达：卡片是活动记录的编辑/删除入口，必须能 Tab 到
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(self._accessible_name())
    
    def _accessible_name(self) -> str:
        """为屏幕阅读器描述这张卡片（类别 / 标题 / 时段）"""
        parts = [self.card.category or "活动"]
        if self.card.title:
            parts.append(self.card.title)
        time_range = self._format_time_range()
        if time_range:
            parts.append(time_range)
        if self.card.productivity_score > 0:
            parts.append(f"生产力 {int(self.card.productivity_score)}%")
        return "，".join(parts)
    
    def _setup_ui(self):
        t = get_theme()
        self.setObjectName("activityCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)
        
        # 获取效率颜色
        efficiency_color = get_efficiency_color(self.card.productivity_score)
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        
        # 顶部：类别标签 + 时间 + 深度工作徽章
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)
        
        # 类别标签
        category_label = QLabel(self.card.category or "活动")
        category_label.setObjectName("categoryLabel")
        category_color = get_category_color(self.card.category)
        category_label.setStyleSheet(f"""
            QLabel#categoryLabel {{
                background-color: {with_alpha(category_color, 0.12)};
                color: {category_color};
                padding: 5px 12px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
            }}
        """)
        top_layout.addWidget(category_label)
        
        # 深度工作徽章 (duration >= 60 分钟)
        # Apple 规范不使用装饰性渐变，改用单一强调色的实心药丸
        if self.card.duration_minutes >= 60:
            deep_work_badge = QLabel("🔥 深度工作")
            deep_work_badge.setStyleSheet(f"""
                background-color: {t.accent};
                color: #FFFFFF;
                padding: 4px 10px;
                border-radius: 9999px;
                font-size: 11px;
                font-weight: 600;
            """)
            top_layout.addWidget(deep_work_badge)
        
        # 时间范围
        time_str = self._format_time_range()
        time_label = QLabel(time_str)
        time_label.setObjectName("timeLabel")
        time_label.setStyleSheet(f"""
            QLabel#timeLabel {{
                color: {t.text_muted};
                font-size: 12px;
            }}
        """)
        top_layout.addWidget(time_label)
        top_layout.addStretch()
        
        # 生产力评分
        if self.card.productivity_score > 0:
            score_label = QLabel(f"⚡ {int(self.card.productivity_score)}%")
            score_label.setStyleSheet(f"""
                color: {efficiency_color};
                font-size: 12px;
                font-weight: 600;
            """)
            top_layout.addWidget(score_label)
        
        layout.addLayout(top_layout)
        
        # 标题
        title_label = QLabel(self.card.title or "未命名活动")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f"""
            QLabel#titleLabel {{
                color: {t.text_primary};
                font-size: 16px;
                font-weight: 600;
            }}
        """)
        layout.addWidget(title_label)
        
        # 摘要
        if self.card.summary:
            summary_label = QLabel(self.card.summary)
            summary_label.setObjectName("summaryLabel")
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet(f"""
                QLabel#summaryLabel {{
                    color: {t.text_secondary};
                    font-size: 13px;
                    line-height: 1.5;
                }}
            """)
            layout.addWidget(summary_label)
        
        # 应用/网站标签
        if self.card.app_sites:
            apps_layout = QHBoxLayout()
            apps_layout.setSpacing(6)
            
            for i, app in enumerate(self.card.app_sites[:4]):  # 最多显示4个
                app_label = QLabel(app.name)
                app_label.setStyleSheet(f"""
                    background-color: {t.bg_tertiary};
                    color: {t.text_secondary};
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 11px;
                """)
                apps_layout.addWidget(app_label)
            
            if len(self.card.app_sites) > 4:
                more_label = QLabel(f"+{len(self.card.app_sites) - 4}")
                more_label.setStyleSheet(f"""
                    color: {t.text_muted};
                    font-size: 11px;
                """)
                apps_layout.addWidget(more_label)
            
            apps_layout.addStretch()
            layout.addLayout(apps_layout)
        
        # 卡片样式 - 左侧效率指示条
        # Apple 规范：卡片不加阴影，层级靠画布/卡片底色差与发丝线表达。
        # 这里用 bg_secondary（卡）压在 bg_primary（画布）上形成层次。
        self.setStyleSheet(self._card_stylesheet())
    
    def _card_stylesheet(self) -> str:
        """卡片样式（构造与 mouseRelease 共用，避免两处漂移）"""
        t = get_theme()
        efficiency_color = get_efficiency_color(self.card.productivity_score)
        return f"""
            QFrame#activityCard {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-left: 4px solid {efficiency_color};
                border-radius: 18px;
            }}
            QFrame#activityCard:hover {{
                background-color: {t.bg_hover};
                border-color: {t.border_hover};
                border-left: 4px solid {efficiency_color};
            }}
            QFrame#activityCard:focus {{
                border: 2px solid {t.accent_focus};
                border-left: 4px solid {efficiency_color};
            }}
        """
    
    def _format_time_range(self) -> str:
        """格式化时间范围"""
        if self.card.start_time and self.card.end_time:
            start = self.card.start_time.strftime("%H:%M")
            end = self.card.end_time.strftime("%H:%M")
            duration = self.card.duration_minutes
            
            if duration >= 60:
                hours = int(duration // 60)
                mins = int(duration % 60)
                duration_str = f"{hours}h {mins}m" if mins else f"{hours}h"
            else:
                duration_str = f"{int(duration)}m"
            
            return f"{start} - {end} ({duration_str})"
        return ""
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.card)
        super().mousePressEvent(event)
    
    def keyPressEvent(self, event):
        """键盘操作：Enter/Space 打开详情，Menu 键或 Shift+F10 呼出菜单"""
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.card)
            event.accept()
            return
        if key == Qt.Key_Menu or (key == Qt.Key_F10 and event.modifiers() & Qt.ShiftModifier):
            self._show_context_menu(self.rect().center())
            event.accept()
            return
        super().keyPressEvent(event)
    
    def mouseReleaseEvent(self, event):
        # 恢复原始样式
        self.setStyleSheet(self._card_stylesheet())
        super().mouseReleaseEvent(event)
    
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        t = get_theme()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
                color: {t.text_primary};
            }}
            QMenu::item:selected {{
                background-color: {t.bg_hover};
            }}
        """)
        
        # 编辑
        edit_action = QAction("✏️ 编辑", self)
        edit_action.triggered.connect(lambda: self.edit_requested.emit(self.card))
        menu.addAction(edit_action)
        
        menu.addSeparator()
        
        # 删除
        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(lambda: self._confirm_delete())
        menu.addAction(delete_action)
        
        global_pos = self.mapToGlobal(pos)
        # QMenu.exec() 是阻塞的：动画必须排在它之前启动，
        # 否则事件循环被占住，动效永远不会推进。
        menu.adjustSize()
        menu.move(global_pos)
        pop_in(menu, duration="menu", offset=(0, 4))
        menu.exec(global_pos)
    
    def _confirm_delete(self):
        """
        删除走「先做掉 + 可撤销」，不再弹确认框。

        这条记录删了还能原样找回来，用确认框拦一次只是让用户多点一下，
        还会训练出「无脑点确定」。真正的不可逆操作才该用确认框。
        """
        self.delete_requested.emit(self.card.id)


class TimelineCardItemWidget(QWidget):
    """时间轴组合项：左侧轨道刻度 + 右侧活动卡片"""
    
    clicked = Signal(ActivityCard)
    edit_requested = Signal(ActivityCard)
    delete_requested = Signal(int)
    
    def __init__(self, card: ActivityCard, parent=None):
        super().__init__(parent)
        self.card = card
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        self.spine = TimelineSpineWidget(card)
        layout.addWidget(self.spine)
        
        self.card_widget = ActivityCardWidget(card)
        self.card_widget.clicked.connect(self.clicked.emit)
        self.card_widget.edit_requested.connect(self.edit_requested.emit)
        self.card_widget.delete_requested.connect(self.delete_requested.emit)
        layout.addWidget(self.card_widget, 1)


class EmptyStateWidget(QWidget):
    """
    空状态组件 —— 说明「为什么空」并给出「接下来做什么」。

    只写一句「暂无数据」的空状态是残缺的：用户看完不知道该干嘛。
    这里每个空态都带一个真按钮，点了就有反应。
    """
    
    action_triggered = Signal(str)  # 动作标识: start / clear_search / prev_day
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 60)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignCenter)
        
        # 大图标
        self.icon_label = QLabel("⏱️")
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)
        
        # 标题
        self.title_label = QLabel("今天还没有活动记录")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        # 描述
        self.desc_label = QLabel("")
        self.desc_label.setAlignment(Qt.AlignCenter)
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)
        
        # 进度条：只在有真实批次数据时出现
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setVisible(False)
        prog_row = QHBoxLayout()
        prog_row.addStretch()
        prog_row.addWidget(self.progress_bar, 2)
        prog_row.addStretch()
        layout.addLayout(prog_row)
        
        # 出口按钮：空状态必须能点，不能只是看着
        self.action_btn = FeedbackButton("开始录制")
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.setFixedHeight(40)
        self.action_btn.setMinimumWidth(120)
        self.action_btn.setAccessibleName("开始录制")
        self.action_btn.clicked.connect(self._on_action)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.action_btn)
        row.addStretch()
        layout.addSpacing(4)
        layout.addLayout(row)
    
    def _on_action(self):
        text = self.action_btn.text()
        if "清除" in text:
            self.action_triggered.emit("clear_search")
        elif "刷新" in text:
            self.action_triggered.emit("refresh")
        else:
            self.action_triggered.emit("start")
    
    def apply_theme(self):
        t = get_theme()
        self.icon_label.setStyleSheet(f"""
            font-size: 64px;
            padding: 20px;
        """)
        self.title_label.setStyleSheet(f"""
            font-size: 20px;
            font-weight: 600;
            color: {t.text_primary};
        """)
        self.desc_label.setStyleSheet(f"""
            font-size: 14px;
            color: {t.text_muted};
            line-height: 1.6;
        """)
        self.action_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.accent};
                color: #FFFFFF;
                border: none;
                border-radius: 9999px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {t.accent_hover};
            }}
            QPushButton:focus {{
                border: 2px solid {t.accent_focus};
                padding: 9px 23px;
            }}
        """)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {t.bg_tertiary};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {t.accent};
                border-radius: 4px;
            }}
        """)
    
    def set_search_mode(self, is_search: bool):
        """切换搜索模式显示"""
        if is_search:
            self.icon_label.setText("🔍")
            self.title_label.setText("未找到匹配的活动")
            self.desc_label.setText("换个关键词，或清除搜索条件查看全部记录")
            # 搜索无结果时，正确的动作是「清除搜索」而不是「开始录制」
            self.action_btn.setText("清除搜索")
            self.action_btn.setVisible(True)
        else:
            self.icon_label.setText("⏱️")
            self.title_label.setText("今天还没有活动记录")
            self.desc_label.setText(
                "开始录制后，Dayflow 会每隔几分钟分析一次屏幕活动，\n"
                "自动整理成时间轴。大约 5 分钟后第一条记录就会出现。"
            )
            self.action_btn.setText("开始录制")
            self.action_btn.setVisible(True)

    def set_has_pending_analysis(self, has_pending: bool,
                                done: int = 0, total: int = 0):
        """
        按「是否有录到但还没分析出来」区分两种空状态。

        这两种「空」的原因完全不同：一种是根本没录，一种是录了但
        分析还没跑完。混为一谈会让用户以为程序坏了，然后去重装。

        有真实批次数据时给出进度条；没有就只说「正在分析」——
        假进度条比没有进度条更糟。
        """
        if has_pending:
            self.icon_label.setText("⏳")
            if total > 0:
                self.title_label.setText("正在分析今天的活动")
                self.desc_label.setText(
                    f"已处理 {done} / {total} 个批次，完成后会自动出现在这里。"
                )
                self.progress_bar.setVisible(True)
                self.progress_bar.setMaximum(total)
                self.progress_bar.setValue(done)
            else:
                self.title_label.setText("正在分析今天的活动")
                self.desc_label.setText(
                    "已经录到屏幕活动，AI 正在整理成时间轴。\n"
                    "通常几分钟内完成，完成后会自动出现在这里。"
                )
                # 不知道总量就不画进度条：画一条不知道多长的条是编造
                self.progress_bar.setVisible(False)
            self.action_btn.setText("刷新看看")
            self.action_btn.setVisible(True)
        else:
            self.progress_bar.setVisible(False)
            self.set_search_mode(False)


class TimelineHeader(QWidget):
    """时间轴头部 - 显示日期和统计"""

    date_changed = Signal(datetime)
    export_clicked = Signal()
    daily_report_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_date = datetime.now()
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        
        # 日期导航区域
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)
        
        # 上一天按钮（纯图标：必须有可访问名称，否则读屏只会念「按钮」）
        self.prev_btn = FeedbackButton("◀")
        self.prev_btn.setFixedSize(32, 32)
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setAccessibleName("上一天")
        self.prev_btn.setToolTip("上一天")
        self.prev_btn.clicked.connect(self._go_previous_day)
        nav_layout.addWidget(self.prev_btn)
        
        # 日期显示
        self.date_label = QLabel()
        nav_layout.addWidget(self.date_label)
        
        # 下一天按钮
        self.next_btn = FeedbackButton("▶")
        self.next_btn.setFixedSize(32, 32)
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setAccessibleName("下一天")
        self.next_btn.setToolTip("下一天")
        self.next_btn.clicked.connect(self._go_next_day)
        nav_layout.addWidget(self.next_btn)
        
        # 今天按钮
        self.today_btn = FeedbackButton("今天")
        self.today_btn.setFixedHeight(32)
        self.today_btn.setMinimumWidth(60)
        self.today_btn.setCursor(Qt.PointingHandCursor)
        self.today_btn.setAccessibleName("回到今天")
        self.today_btn.clicked.connect(self._go_today)
        nav_layout.addWidget(self.today_btn)
        
        layout.addLayout(nav_layout)
        layout.addStretch()
        
        # 导出按钮
        self.export_btn = FeedbackButton("📥 导出")
        self.export_btn.setFixedHeight(32)
        self.export_btn.setMinimumWidth(84)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setAccessibleName("导出当前时间轴")
        self.export_btn.clicked.connect(self.export_clicked.emit)
        layout.addWidget(self.export_btn)

        # 生成日报按钮
        self.report_btn = FeedbackButton("📋 生成日报")
        self.report_btn.setFixedHeight(32)
        self.report_btn.setMinimumWidth(104)
        self.report_btn.setCursor(Qt.PointingHandCursor)
        self.report_btn.setAccessibleName("为当前日期生成日报")
        self.report_btn.clicked.connect(self.daily_report_clicked.emit)
        layout.addWidget(self.report_btn)
        
        # 统计信息
        self.stats_label = QLabel()
        layout.addWidget(self.stats_label)
        
        self._update_date_display()
    
    def apply_theme(self):
        """应用主题"""
        t = get_theme()
        
        # 导航按钮样式
        nav_btn_style = f"""
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: none;
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
            }}
        """
        self.prev_btn.setStyleSheet(nav_btn_style)
        self.next_btn.setStyleSheet(nav_btn_style)
        
        # 日期显示 - 28px, 700
        self.date_label.setStyleSheet(f"""
            font-size: 28px;
            font-weight: 700;
            color: {t.text_primary};
            padding: 0 12px;
        """)
        
        # 今天按钮（强调色）
        self.today_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.accent};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {t.accent_hover};
            }}
        """)
        
        # 导出按钮
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: none;
                border-radius: 6px;
                font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
            }}
        """)
        
        # 统计信息
        self.stats_label.setStyleSheet(f"""
            font-size: 14px;
            color: {t.text_muted};
            margin-left: 16px;
        """)
    
    def _go_previous_day(self):
        """前一天"""
        self._current_date = self._current_date - timedelta(days=1)
        self._update_date_display()
        self.date_changed.emit(self._current_date)
    
    def _go_next_day(self):
        """后一天"""
        # 不能超过今天
        if self._current_date.date() < datetime.now().date():
            self._current_date = self._current_date + timedelta(days=1)
            self._update_date_display()
            self.date_changed.emit(self._current_date)
    
    def _go_today(self):
        """回到今天"""
        self._current_date = datetime.now()
        self._update_date_display()
        self.date_changed.emit(self._current_date)
    
    def _update_date_display(self):
        today = datetime.now().date()
        
        if self._current_date.date() == today:
            date_text = "今天"
        elif self._current_date.date() == today - timedelta(days=1):
            date_text = "昨天"
        else:
            date_text = self._current_date.strftime("%m月%d日")
        
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[self._current_date.weekday()]
        
        self.date_label.setText(f"{date_text}，{weekday}")
    
    def set_date(self, date: datetime):
        self._current_date = date
        self._update_date_display()
        self.date_changed.emit(date)
    
    def set_stats(self, card_count: int, total_hours: float):
        if card_count > 0:
            self.stats_label.setText(f"{card_count} 个活动 · {total_hours:.1f} 小时")
        else:
            self.stats_label.setText("暂无记录")


class TimelineView(QWidget):
    """时间轴主视图"""
    
    card_selected = Signal(ActivityCard)
    date_changed = Signal(datetime)
    export_requested = Signal(datetime, list)  # 日期, 卡片列表
    card_updated = Signal(ActivityCard)  # 卡片更新信号
    card_deleted = Signal(int)  # 卡片删除信号
    card_restored = Signal(ActivityCard)  # 卡片撤销恢复信号
    daily_report_clicked = Signal(datetime)  # 生成日报信号
    start_recording_requested = Signal()  # 空状态里的「开始录制」
    refresh_requested = Signal()  # 空状态里的「刷新看看」
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[ActivityCard] = []
        self._filtered_cards: List[ActivityCard] = []
        self._current_date = datetime.now()
        self._search_text = ""
        self._selected_category = ""
        self._last_deleted: Optional[ActivityCard] = None
        self._pending_analysis = False
        self._pending_done = 0
        self._pending_total = 0
        self.snackbar: Optional[Snackbar] = None
        
        # 搜索防抖定时器
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)
        self._pending_search = ""
        
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 头部
        self.header = TimelineHeader()
        self.header.date_changed.connect(self._on_date_changed)
        self.header.export_clicked.connect(self._on_export_clicked)
        self.header.daily_report_clicked.connect(lambda: self.daily_report_clicked.emit(self._current_date))
        main_layout.addWidget(self.header)
        
        # 搜索栏
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(24, 12, 24, 8)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索活动标题或摘要...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input)
        
        main_layout.addWidget(search_container)
        
        # 分类筛选胶囊栏
        self.category_filter_bar = CategoryFilterBar()
        self.category_filter_bar.category_selected.connect(self._on_category_selected)
        main_layout.addWidget(self.category_filter_bar)
        
        # 统计汇总（带边距）
        stats_container = QWidget()
        stats_layout = QHBoxLayout(stats_container)
        stats_layout.setContentsMargins(24, 0, 24, 12)
        self.stats_widget = StatsSummaryWidget()
        stats_layout.addWidget(self.stats_widget)
        main_layout.addWidget(stats_container)
        
        # 滚动区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 卡片容器
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(24, 8, 24, 24)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        
        self.scroll.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll)
        
        # 空状态组件
        self.empty_widget = EmptyStateWidget()
        self.empty_widget.action_triggered.connect(self._on_empty_action)
        self.cards_layout.insertWidget(0, self.empty_widget)
    
    def _on_empty_action(self, action: str):
        """空状态里的按钮动作"""
        if action == "start":
            self.start_recording_requested.emit()
        elif action == "clear_search":
            self.search_input.clear()
            self._do_search()
        elif action == "refresh":
            self.refresh_requested.emit()
    
    def apply_theme(self):
        """应用主题"""
        t = get_theme()
        
        # 搜索框样式
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 14px;
                color: {t.text_primary};
            }}
            QLineEdit:focus {{
                border-color: {t.accent};
                background-color: {t.bg_primary};
            }}
            QLineEdit::placeholder {{
                color: {t.text_muted};
            }}
        """)
        
        # 刷新分类筛选栏主题
        if hasattr(self, 'category_filter_bar'):
            self.category_filter_bar.apply_theme()
            
        # 重新创建卡片以应用新主题
        if self._cards:
            self._refresh_cards()
    
    def _on_category_selected(self, category: str):
        """选择分类筛选"""
        self._selected_category = category
        self._refresh_cards()
    
    def _on_search_changed(self, text: str):
        """搜索文本变化 - 使用防抖"""
        self._pending_search = text.strip().lower()
        # 300ms 防抖，避免频繁刷新
        self._search_timer.start(300)
    
    def _do_search(self):
        """执行搜索"""
        self._search_text = self._pending_search
        self._refresh_cards()
    
    def _get_filtered_cards(self) -> List[ActivityCard]:
        """获取过滤后的卡片（支持分类与搜索词组合过滤）"""
        cards = self._cards
        
        # 1. 按分类过滤
        if self._selected_category:
            cards = [c for c in cards if (c.category or "其他") == self._selected_category]
            
        # 2. 按搜索文字过滤
        if not self._search_text:
            return cards
        
        filtered = []
        for card in cards:
            title = (card.title or "").lower()
            summary = (card.summary or "").lower()
            category = (card.category or "").lower()
            
            if (self._search_text in title or 
                self._search_text in summary or 
                self._search_text in category):
                filtered.append(card)
        
        return filtered
    
    def set_cards(self, cards: List[ActivityCard]):
        """设置卡片列表"""
        self._cards = cards
        self._refresh_cards()
    
    def add_card(self, card: ActivityCard):
        """添加单个卡片（来自分析完成的新活动）"""
        self._cards.append(card)
        self._add_card_widget(card, animate=True)
        self._update_empty_state()
        self._update_stats()
    
    def _refresh_cards(self, scroll_to_bottom: bool = False):
        """刷新所有卡片 - 支持时间轴轨道与空闲时段插桩"""
        # 保存当前滚动位置
        scrollbar = self.scroll.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 50
        old_scroll_value = scrollbar.value()
        
        # 暂停界面更新，减少重绘
        self.cards_container.setUpdatesEnabled(False)
        
        try:
            # 清除现有卡片与空闲时段组件
            while self.cards_layout.count() > 1:  # 保留 stretch
                item = self.cards_layout.takeAt(0)
                if item.widget() and item.widget() != self.empty_widget:
                    item.widget().deleteLater()
            
            # 更新分类筛选药丸角标数量
            if hasattr(self, 'category_filter_bar'):
                self.category_filter_bar.update_counts(self._cards)
            
            # 获取过滤后的卡片
            filtered_cards = self._get_filtered_cards()
            
            # 按起始时间排序
            sorted_cards = sorted(filtered_cards, key=lambda c: c.start_time or datetime.min)
            
            # 批量添加新卡片，并在时间跨度 >= 15 分钟时自动插入空闲胶囊
            prev_end_time = None
            for card in sorted_cards:
                if prev_end_time and card.start_time and card.start_time > prev_end_time:
                    gap_mins = (card.start_time - prev_end_time).total_seconds() / 60.0
                    if gap_mins >= 15.0:
                        gap_widget = TimelineGapWidget(prev_end_time, card.start_time, gap_mins)
                        self.cards_layout.insertWidget(self.cards_layout.count() - 1, gap_widget)
                
                self._add_card_widget(card, animate=False)
                if card.end_time:
                    prev_end_time = card.end_time
            
            self._update_empty_state(filtered_cards)
            self._update_stats()
            
            # 更新统计图表
            self.stats_widget.set_data(self._cards)
        finally:
            # 恢复界面更新
            self.cards_container.setUpdatesEnabled(True)
        
        # 使用单次定时器恢复滚动位置
        def restore_scroll():
            if scroll_to_bottom or was_at_bottom:
                scrollbar.setValue(scrollbar.maximum())
            else:
                scrollbar.setValue(min(old_scroll_value, scrollbar.maximum()))
        
        QTimer.singleShot(10, restore_scroll)
    
    def _add_card_widget(self, card: ActivityCard, animate: bool = True,
                         delay: int = 0):
        """添加卡片组件（时间轴轨道 + 卡片组合）"""
        widget = TimelineCardItemWidget(card)
        widget.clicked.connect(self._on_card_clicked)
        widget.edit_requested.connect(self._on_edit_card)
        widget.delete_requested.connect(self._on_delete_card)
        
        # 插入到 stretch 之前
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, widget)
        widget.show()
        
        # 新卡片淡入：这是「刚产生了新活动」的唯一视觉信号。
        # 批量刷新时 animate=False —— 那不是「新增」，是重绘，
        # 给二十张卡逐个做入场动画只会拖慢刷新还让人眼花。
        if animate:
            rise_in(widget, duration="space", delay=delay, distance=6)
        return widget

    def _find_card_widget(self, card_id: int) -> Optional[QWidget]:
        """按 card_id 找到对应的卡片组件"""
        for i in range(self.cards_layout.count()):
            w = self.cards_layout.itemAt(i).widget()
            if w is None:
                continue
            card = getattr(w, "card", None)
            if card is not None and getattr(card, "id", None) == card_id:
                return w
            inner = getattr(w, "card_widget", None)
            if inner is not None:
                c2 = getattr(inner, "card", None)
                if c2 is not None and getattr(c2, "id", None) == card_id:
                    return w
        return None
    
    def _on_card_clicked(self, card: ActivityCard):
        """卡片点击 - 打开编辑对话框"""
        self._on_edit_card(card)
    
    def _on_edit_card(self, card: ActivityCard):
        """打开编辑对话框"""
        dialog = CardEditDialog(card, self)
        dialog.card_updated.connect(self._handle_card_updated)
        dialog.card_deleted.connect(self._handle_card_deleted)
        dialog.exec()
    
    def _on_delete_card(self, card_id: int):
        """处理删除请求"""
        self._handle_card_deleted(card_id)
    
    def _handle_card_updated(self, card: ActivityCard):
        """处理卡片更新"""
        self.card_updated.emit(card)
        # 刷新显示
        self._refresh_cards()
    
    def _handle_card_deleted(self, card_id: int):
        """
        处理卡片删除。

        流程：先折叠消失 → 重建列表 → 给出撤销出口。
        折叠动效是在回答「它走了」；撤销条是在回答「还能拿回来」。
        两者分工明确：动效说发生了什么，撤销条说怎么办。
        """
        removed = next((c for c in self._cards if c.id == card_id), None)
        if removed is None:
            # 找不到就直接通知上层，避免静默失败
            self.card_deleted.emit(card_id)
            return

        self.card_deleted.emit(card_id)
        self._cards = [c for c in self._cards if c.id != card_id]

        target = self._find_card_widget(card_id)
        if target is not None:
            collapse_out(target, height=target.sizeHint().height())
        else:
            self._refresh_cards()

        def _rebuild():
            self._refresh_cards()
            self._show_undo(removed)

        QTimer.singleShot(160, _rebuild)

    def _show_undo(self, card: ActivityCard):
        """显示撤销提示条"""
        title = (card.title or "这条活动记录").strip()
        if len(title) > 24:
            title = title[:24] + "…"
        self._last_deleted = card

        if self.snackbar is None:
            self.snackbar = Snackbar(self)

        def _undo():
            restored = self._last_deleted
            self._last_deleted = None
            if restored is None:
                return
            # 恢复到原来的时间顺序位置
            self._cards.append(restored)
            self._refresh_cards()
            # 找到复原的卡片并短暂高亮，让用户确认「真的回来了」
            QTimer.singleShot(60, lambda: self._flash_card(restored.id))
            self.card_restored.emit(restored)

        self.snackbar.show_message(
            f"已删除「{title}」", "撤销", _undo
        )

    def _flash_card(self, card_id: int):
        """复原后短暂强调该卡片，让用户确认「真的回来了」"""
        w = self._find_card_widget(card_id)
        if w is None:
            return
        inner = getattr(w, "card_widget", w)
        if not hasattr(inner, "_card_stylesheet"):
            return
        t = get_theme()
        original = inner._card_stylesheet()
        inner.setStyleSheet(f"""
            QFrame#activityCard {{
                background-color: {t.accent_light};
                border: 2px solid {t.accent};
                border-left: 4px solid {t.accent};
                border-radius: 18px;
            }}
        """)
        QTimer.singleShot(1400, lambda: inner.setStyleSheet(original))

    def _update_empty_state(self, cards: List[ActivityCard] = None):
        """更新空状态显示"""
        if cards is None:
            cards = self._cards
        
        if len(cards) == 0:
            if self._search_text:
                self.empty_widget.set_search_mode(True)
            else:
                # 区分「还没录」和「录了但这天没分析出活动」——
                # 两者的下一步完全不同，混为一谈会让用户以为程序坏了
                self.empty_widget.set_has_pending_analysis(
                    self._has_pending(), self._pending_done, self._pending_total
                )
            self.empty_widget.setVisible(True)
        else:
            self.empty_widget.setVisible(False)
    
    def _has_pending(self) -> bool:
        """当前是否有正在等待分析的活动（由外部告知）"""
        return self._pending_analysis or self._pending_total > 0

    def set_analysis_progress(self, done: int, total: int):
        """
        接收分析进度。

        done == 0 且 total == 0 表示「没有待分析的切片」——
        这是分析完成后的常态，不该还显示进度条。
        """
        self._pending_done = done
        self._pending_total = total
        self._pending_analysis = total > 0

        if self.empty_widget.isVisible():
            self.empty_widget.set_has_pending_analysis(
                self._pending_analysis, done, total
            )
    
    def _update_stats(self):
        """更新统计信息"""
        total_minutes = sum(c.duration_minutes for c in self._cards)
        self.header.set_stats(len(self._cards), total_minutes / 60)
    
    def set_date(self, date: datetime):
        """设置当前日期"""
        self._current_date = date
        self.header.set_date(date)
    
    def clear(self):
        """清空时间轴"""
        self._cards = []
        self._refresh_cards()
    
    def _on_date_changed(self, date: datetime):
        """日期切换"""
        self._current_date = date
        self.date_changed.emit(date)
    
    def _on_export_clicked(self):
        """导出按钮点击"""
        self.export_requested.emit(self._current_date, self._cards)
    
    def get_current_date(self) -> datetime:
        """获取当前显示的日期"""
        return self._current_date
