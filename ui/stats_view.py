"""
Dayflow Windows - 数据统计与分析视图
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QSpinBox, QComboBox,
    QProgressBar, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath

from ui.themes import get_theme, get_theme_manager
from database.storage import StorageManager
from core.types import ActivityCard

logger = logging.getLogger(__name__)

# 类别颜色映射
CATEGORY_COLORS = {
    "工作": "#3B82F6",
    "编程": "#8B5CF6", 
    "学习": "#10B981",
    "会议": "#F59E0B",
    "娱乐": "#EF4444",
    "社交": "#EC4899",
    "休息": "#6B7280",
    "其他": "#94A3B8",
}


class BarChartWidget(QWidget):
    """柱状图组件 - 显示每日时间分布"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Dict] = []  # [{date, categories: {cat: minutes}}]
        self._max_value = 480  # 默认最大 8 小时
        self.setMinimumHeight(250)
        self.setMinimumWidth(400)
    
    def set_data(self, data: List[Dict], max_value: int = None):
        """设置数据"""
        self._data = data
        if max_value:
            self._max_value = max_value
        elif data:
            max_total = max(sum(d.get("categories", {}).values()) for d in data) if data else 480
            self._max_value = max(max_total, 60)  # 至少 1 小时
        self.update()
    
    def paintEvent(self, event):
        """绘制柱状图"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        t = get_theme()
        width = self.width()
        height = self.height()
        
        # 边距 - 增大底部边距确保标签显示
        margin_left = 45
        margin_right = 15
        margin_top = 15
        margin_bottom = 35
        
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        
        if chart_width <= 0 or chart_height <= 0:
            return
        
        # 计算合适的 Y 轴刻度
        max_hours = self._max_value / 60
        if max_hours <= 1:
            y_step = 0.25
        elif max_hours <= 4:
            y_step = 1
        elif max_hours <= 8:
            y_step = 2
        else:
            y_step = 4
        
        y_max = ((int(max_hours / y_step) + 1) * y_step)
        tick_count = int(y_max / y_step) + 1
        
        # 绘制 Y 轴刻度和网格线
        painter.setFont(QFont("Microsoft YaHei", 9))
        
        for i in range(tick_count):
            hours = i * y_step
            y = margin_top + chart_height - (chart_height * hours / y_max)
            
            # 网格线
            painter.setPen(QPen(QColor(t.border), 1, Qt.DotLine))
            painter.drawLine(margin_left, int(y), width - margin_right, int(y))
            
            # Y 轴标签
            painter.setPen(QPen(QColor(t.text_muted), 1))
            label = f"{hours:.0f}h" if hours == int(hours) else f"{hours:.1f}h"
            painter.drawText(0, int(y) - 8, margin_left - 5, 16, Qt.AlignRight | Qt.AlignVCenter, label)
        
        if not self._data:
            # 无数据提示
            painter.setPen(QPen(QColor(t.text_muted)))
            painter.setFont(QFont("Microsoft YaHei", 11))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            painter.end()
            return
        
        # 计算柱宽
        bar_count = len(self._data)
        total_gap = chart_width * 0.3  # 30% 用于间隔
        gap = total_gap / (bar_count + 1)
        bar_width = (chart_width - total_gap) / bar_count
        bar_width = min(bar_width, 50)  # 最大宽度 50
        
        # 重新计算以居中
        total_bars_width = bar_count * bar_width + (bar_count - 1) * gap
        start_x = margin_left + (chart_width - total_bars_width) / 2
        
        # 绘制柱状图
        for i, day_data in enumerate(self._data):
            x = start_x + i * (bar_width + gap)
            categories = day_data.get("categories", {})
            
            # 堆叠绘制各类别
            current_y = margin_top + chart_height
            for cat, minutes in categories.items():
                bar_height = (minutes / 60 / y_max) * chart_height
                if bar_height < 1:
                    continue
                
                color = QColor(CATEGORY_COLORS.get(cat, "#94A3B8"))
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.NoPen)
                
                rect = QRect(int(x), int(current_y - bar_height), int(bar_width), int(bar_height))
                painter.drawRoundedRect(rect, 3, 3)
                
                current_y -= bar_height
            
            # X 轴标签（日期）
            date_str = day_data.get("date", "")
            if len(date_str) >= 5:
                label = date_str[-5:]  # MM-DD
            else:
                label = date_str
            
            painter.setPen(QPen(QColor(t.text_secondary), 1))
            painter.setFont(QFont("Microsoft YaHei", 8))
            text_rect = QRect(int(x - 10), height - margin_bottom + 5, int(bar_width + 20), 20)
            painter.drawText(text_rect, Qt.AlignCenter, label)
        
        painter.end()


class LineChartWidget(QWidget):
    """折线图组件 - 显示生产力趋势"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []  # [(date, score)]
        self.setMinimumHeight(220)
        self.setMinimumWidth(400)
    
    def set_data(self, data: List[Tuple[str, float]]):
        """设置数据 [(日期, 分数)]"""
        self._data = data
        self.update()
    
    def paintEvent(self, event):
        """绘制折线图"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        t = get_theme()
        width = self.width()
        height = self.height()
        
        # 边距
        margin_left = 45
        margin_right = 15
        margin_top = 15
        margin_bottom = 35
        
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        
        if chart_width <= 0 or chart_height <= 0:
            return
        
        # 绘制 Y 轴刻度 (0-100)
        painter.setFont(QFont("Microsoft YaHei", 9))
        
        for i in range(5):
            y = margin_top + chart_height - (chart_height * i / 4)
            score = 25 * i
            
            # 网格线
            painter.setPen(QPen(QColor(t.border), 1, Qt.DotLine))
            painter.drawLine(margin_left, int(y), width - margin_right, int(y))
            
            # Y 轴标签
            painter.setPen(QPen(QColor(t.text_muted), 1))
            painter.drawText(0, int(y) - 8, margin_left - 5, 16, Qt.AlignRight | Qt.AlignVCenter, f"{score}")
        
        if len(self._data) < 2:
            # 数据不足，显示提示
            painter.setPen(QPen(QColor(t.text_muted)))
            painter.setFont(QFont("Microsoft YaHei", 11))
            painter.drawText(self.rect(), Qt.AlignCenter, "数据不足，需要至少2天记录")
            painter.end()
            return
        
        # 计算点位置
        points = []
        point_count = len(self._data)
        
        for i, (date, score) in enumerate(self._data):
            x = margin_left + (chart_width * i / (point_count - 1)) if point_count > 1 else margin_left
            y = margin_top + chart_height - (chart_height * score / 100)
            points.append((x, y, date, score))
        
        # 绘制填充区域
        if points:
            path = QPainterPath()
            path.moveTo(points[0][0], margin_top + chart_height)
            for x, y, _, _ in points:
                path.lineTo(x, y)
            path.lineTo(points[-1][0], margin_top + chart_height)
            path.closeSubpath()
            
            fill_color = QColor(t.accent)
            fill_color.setAlpha(25)
            painter.fillPath(path, QBrush(fill_color))
        
        # 绘制折线
        painter.setPen(QPen(QColor(t.accent), 2.5))
        for i in range(len(points) - 1):
            painter.drawLine(
                int(points[i][0]), int(points[i][1]),
                int(points[i+1][0]), int(points[i+1][1])
            )
        
        # 绘制数据点和 X 轴标签
        painter.setFont(QFont("Microsoft YaHei", 8))
        show_label_interval = max(1, len(points) // 7)  # 最多显示 7 个标签
        
        for i, (x, y, date, score) in enumerate(points):
            # 数据点
            painter.setBrush(QBrush(QColor(t.bg_primary)))
            painter.setPen(QPen(QColor(t.accent), 2))
            painter.drawEllipse(int(x) - 4, int(y) - 4, 8, 8)
            
            # X 轴标签
            if i % show_label_interval == 0 or i == len(points) - 1:
                label = date[-5:] if len(date) >= 5 else date
                painter.setPen(QPen(QColor(t.text_secondary), 1))
                text_rect = QRect(int(x) - 25, height - margin_bottom + 5, 50, 20)
                painter.drawText(text_rect, Qt.AlignCenter, label)
        
        painter.end()


class GoalWidget(QWidget):
    """目标设定组件"""
    
    goal_changed = Signal(int)  # 目标小时数
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._goal_hours = 8
        self._current_hours = 0
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 目标设置行
        goal_row = QHBoxLayout()
        goal_row.setSpacing(10)
        
        goal_label = QLabel("每日目标:")
        goal_label.setStyleSheet("font-size: 13px;")
        goal_row.addWidget(goal_label)
        
        self.goal_spin = QSpinBox()
        self.goal_spin.setRange(1, 16)
        self.goal_spin.setValue(8)
        self.goal_spin.setSuffix(" 小时")
        self.goal_spin.setFixedWidth(100)
        self.goal_spin.valueChanged.connect(self._on_goal_changed)
        goal_row.addWidget(self.goal_spin)
        
        goal_row.addStretch()
        layout.addLayout(goal_row)
        
        # 进度显示
        self.progress_label = QLabel("今日进度: 0h / 8h")
        self.progress_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.progress_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 状态提示
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.status_label)
    
    def _on_goal_changed(self, value):
        self._goal_hours = value
        self._update_display()
        self.goal_changed.emit(value)
    
    def set_current_hours(self, hours: float):
        """设置当前完成小时数"""
        self._current_hours = hours
        self._update_display()
    
    def set_goal(self, hours: int):
        """设置目标"""
        self._goal_hours = hours
        self.goal_spin.setValue(hours)
        self._update_display()
    
    def _update_display(self):
        """更新显示"""
        t = get_theme()
        
        # 进度文字
        self.progress_label.setText(
            f"今日进度: {self._current_hours:.1f}h / {self._goal_hours}h"
        )
        
        # 进度条
        percent = min(100, (self._current_hours / self._goal_hours) * 100) if self._goal_hours > 0 else 0
        self.progress_bar.setValue(int(percent))
        
        # 颜色
        if percent >= 100:
            color = "#10B981"  # 绿色 - 完成
            status = "🎉 目标已达成！"
        elif percent >= 75:
            color = "#3B82F6"  # 蓝色 - 接近
            status = "💪 加油，快完成了！"
        elif percent >= 50:
            color = "#F59E0B"  # 黄色 - 一半
            status = "⏰ 已完成一半"
        else:
            color = "#6B7280"  # 灰色 - 刚开始
            status = "📝 继续努力"
        
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {t.bg_tertiary};
                border: none;
                border-radius: 10px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 10px;
            }}
        """)
        
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"font-size: 12px; color: {t.text_secondary};")
    
    def apply_theme(self):
        """应用主题"""
        t = get_theme()
        self.goal_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 4px 8px;
                color: {t.text_primary};
            }}
        """)
        self._update_display()


class CategoryLegend(QWidget):
    """类别图例 - 使用网格布局，更紧凑"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        layout.setHorizontalSpacing(20)
        
        categories = list(CATEGORY_COLORS.items())
        cols = 4  # 每行 4 个
        
        for idx, (cat, color) in enumerate(categories):
            row = idx // cols
            col = idx % cols
            
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(5)
            
            # 颜色块
            color_box = QLabel()
            color_box.setFixedSize(10, 10)
            color_box.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            item_layout.addWidget(color_box)
            
            # 文字
            label = QLabel(cat)
            label.setStyleSheet("font-size: 11px;")
            item_layout.addWidget(label)
            item_layout.addStretch()
            
            layout.addWidget(item_widget, row, col)


class DateCompareWidget(QWidget):
    """日期对比组件"""
    
    def __init__(self, storage: StorageManager, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._date1_data: Dict[str, float] = {}
        self._date2_data: Dict[str, float] = {}
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 日期选择行
        date_row = QHBoxLayout()
        date_row.setSpacing(10)
        
        date_row.addWidget(QLabel("对比日期:"))
        
        self.combo1 = QComboBox()
        self.combo1.setFixedWidth(120)
        self.combo1.currentIndexChanged.connect(self._on_date_changed)
        date_row.addWidget(self.combo1)
        
        date_row.addWidget(QLabel("vs"))
        
        self.combo2 = QComboBox()
        self.combo2.setFixedWidth(120)
        self.combo2.currentIndexChanged.connect(self._on_date_changed)
        date_row.addWidget(self.combo2)
        
        date_row.addStretch()
        layout.addLayout(date_row)
        
        # 对比结果容器
        self.compare_container = QVBoxLayout()
        self.compare_container.setSpacing(8)
        layout.addLayout(self.compare_container)
        
        # 填充日期选项
        self._populate_dates()
    
    def _populate_dates(self):
        """填充日期选项（最近 14 天）"""
        today = datetime.now()
        dates = []
        for i in range(14):
            d = today - timedelta(days=i)
            dates.append(d.strftime("%Y-%m-%d"))
        
        self.combo1.clear()
        self.combo2.clear()
        self.combo1.addItems(dates)
        self.combo2.addItems(dates)
        
        if len(dates) >= 2:
            self.combo2.setCurrentIndex(1)
    
    def _on_date_changed(self):
        """日期选择改变"""
        date1_str = self.combo1.currentText()
        date2_str = self.combo2.currentText()
        
        if not date1_str or not date2_str:
            return
        
        # 获取数据
        self._date1_data = self._get_date_stats(date1_str)
        self._date2_data = self._get_date_stats(date2_str)
        
        self._update_comparison()
    
    def _get_date_stats(self, date_str: str) -> Dict[str, float]:
        """获取某天的统计数据"""
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            cards = self.storage.get_cards_for_date(date)
            
            stats = {}
            for card in cards:
                cat = card.category or "其他"
                minutes = card.duration_minutes
                stats[cat] = stats.get(cat, 0) + minutes
            
            return stats
        except Exception as e:
            logger.error(f"获取日期统计失败: {e}")
            return {}
    
    def _update_comparison(self):
        """更新对比显示"""
        # 清除旧内容
        while self.compare_container.count():
            item = self.compare_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        t = get_theme()
        
        # 获取所有类别
        all_cats = set(self._date1_data.keys()) | set(self._date2_data.keys())
        
        if not all_cats:
            empty = QLabel("暂无数据")
            empty.setStyleSheet(f"color: {t.text_muted}; font-size: 13px;")
            self.compare_container.addWidget(empty)
            return
        
        for cat in sorted(all_cats):
            min1 = self._date1_data.get(cat, 0)
            min2 = self._date2_data.get(cat, 0)
            diff = min1 - min2
            
            row = QHBoxLayout()
            row.setSpacing(10)
            
            # 类别颜色
            color_box = QLabel()
            color_box.setFixedSize(10, 10)
            color_box.setStyleSheet(
                f"background-color: {CATEGORY_COLORS.get(cat, '#94A3B8')}; border-radius: 2px;"
            )
            row.addWidget(color_box)
            
            # 类别名
            cat_label = QLabel(cat)
            cat_label.setFixedWidth(50)
            cat_label.setStyleSheet(f"color: {t.text_primary}; font-size: 12px;")
            row.addWidget(cat_label)
            
            # 日期1时间
            time1 = QLabel(f"{min1:.0f}m")
            time1.setFixedWidth(50)
            time1.setAlignment(Qt.AlignRight)
            time1.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
            row.addWidget(time1)
            
            # 差异
            if diff > 0:
                diff_text = f"↑ +{diff:.0f}m"
                diff_color = "#10B981"
            elif diff < 0:
                diff_text = f"↓ {diff:.0f}m"
                diff_color = "#EF4444"
            else:
                diff_text = "="
                diff_color = t.text_muted
            
            diff_label = QLabel(diff_text)
            diff_label.setFixedWidth(70)
            diff_label.setAlignment(Qt.AlignCenter)
            diff_label.setStyleSheet(f"color: {diff_color}; font-size: 12px; font-weight: bold;")
            row.addWidget(diff_label)
            
            # 日期2时间
            time2 = QLabel(f"{min2:.0f}m")
            time2.setFixedWidth(50)
            time2.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
            row.addWidget(time2)
            
            row.addStretch()
            
            container = QWidget()
            container.setLayout(row)
            self.compare_container.addWidget(container)
    
    def apply_theme(self):
        """应用主题"""
        t = get_theme()
        self.combo1.setStyleSheet(f"""
            QComboBox {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 4px 8px;
                color: {t.text_primary};
            }}
        """)
        self.combo2.setStyleSheet(self.combo1.styleSheet())
        self._update_comparison()


class StatsPanel(QWidget):
    """数据统计面板 - 主容器"""
    
    def __init__(self, storage: StorageManager, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._current_range = "week"  # week / month
        self._setup_ui()
        self._load_data()
        
        # 连接主题变化
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 内容容器
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(24)
        
        # ===== 标题 =====
        title = QLabel("📊 数据统计")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        
        # ===== 时间范围选择 =====
        range_row = QHBoxLayout()
        range_row.setSpacing(8)
        
        self.week_btn = QPushButton("本周")
        self.week_btn.setCheckable(True)
        self.week_btn.setChecked(True)
        self.week_btn.clicked.connect(lambda: self._set_range("week"))
        range_row.addWidget(self.week_btn)
        
        self.month_btn = QPushButton("本月")
        self.month_btn.setCheckable(True)
        self.month_btn.clicked.connect(lambda: self._set_range("month"))
        range_row.addWidget(self.month_btn)
        
        range_row.addStretch()
        layout.addLayout(range_row)
        
        # ===== 周/月统计图表 =====
        chart_section = self._create_section("时间分布")
        
        self.bar_chart = BarChartWidget()
        chart_section.layout().addWidget(self.bar_chart)
        
        self.legend = CategoryLegend()
        chart_section.layout().addWidget(self.legend)
        
        layout.addWidget(chart_section)
        
        # ===== 生产力趋势 =====
        trend_section = self._create_section("生产力趋势")
        
        self.line_chart = LineChartWidget()
        trend_section.layout().addWidget(self.line_chart)
        
        layout.addWidget(trend_section)
        
        # ===== 今日目标 =====
        goal_section = self._create_section("今日目标")
        
        self.goal_widget = GoalWidget()
        self.goal_widget.goal_changed.connect(self._on_goal_changed)
        goal_section.layout().addWidget(self.goal_widget)
        
        layout.addWidget(goal_section)
        
        # ===== 日期对比 =====
        compare_section = self._create_section("日期对比")
        
        self.compare_widget = DateCompareWidget(self.storage)
        compare_section.layout().addWidget(self.compare_widget)
        
        layout.addWidget(compare_section)
        
        # 底部间距
        layout.addStretch()
        
        scroll.setWidget(content)
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
    
    def _create_section(self, title: str) -> QFrame:
        """创建分区容器"""
        frame = QFrame()
        frame.setObjectName("statsSection")
        
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title_label)
        
        return frame
    
    def _set_range(self, range_type: str):
        """设置时间范围"""
        self._current_range = range_type
        self.week_btn.setChecked(range_type == "week")
        self.month_btn.setChecked(range_type == "month")
        self._load_data()
    
    def _load_data(self):
        """加载统计数据"""
        today = datetime.now()
        
        if self._current_range == "week":
            days = 7
        else:
            days = 30
        
        # 收集每日数据
        bar_data = []
        trend_data = []
        total_today_minutes = 0
        
        for i in range(days - 1, -1, -1):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            
            cards = self.storage.get_cards_for_date(date)
            
            # 分类统计
            categories = {}
            total_score = 0
            score_count = 0
            
            for card in cards:
                cat = card.category or "其他"
                minutes = card.duration_minutes
                categories[cat] = categories.get(cat, 0) + minutes
                
                if card.productivity_score > 0:
                    total_score += card.productivity_score
                    score_count += 1
            
            bar_data.append({
                "date": date_str,
                "categories": categories
            })
            
            avg_score = total_score / score_count if score_count > 0 else 0
            trend_data.append((date_str, avg_score))
            
            # 今日总时间
            if i == 0:
                total_today_minutes = sum(categories.values())
        
        # 更新图表
        self.bar_chart.set_data(bar_data)
        self.line_chart.set_data(trend_data)
        
        # 更新目标进度
        self.goal_widget.set_current_hours(total_today_minutes / 60)
        
        # 加载保存的目标
        goal = self.storage.get_setting("daily_goal", "8")
        try:
            self.goal_widget.set_goal(int(goal))
        except ValueError:
            pass
    
    def _on_goal_changed(self, hours: int):
        """目标改变"""
        self.storage.set_setting("daily_goal", str(hours))
    
    def refresh(self):
        """刷新数据"""
        self._load_data()
        self.compare_widget._on_date_changed()
    
    def apply_theme(self):
        """应用主题"""
        t = get_theme()
        
        # 按钮样式
        btn_style = f"""
            QPushButton {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
            }}
            QPushButton:checked {{
                background-color: {t.accent};
                color: white;
                border-color: {t.accent};
            }}
        """
        self.week_btn.setStyleSheet(btn_style)
        self.month_btn.setStyleSheet(btn_style)
        
        # 分区样式
        self.setStyleSheet(f"""
            QFrame#statsSection {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 12px;
            }}
            QLabel {{
                color: {t.text_primary};
            }}
            QLabel#sectionTitle {{
                color: {t.text_primary};
            }}
            QScrollArea {{
                background-color: {t.bg_primary};
                border: none;
            }}
        """)
        
        # 子组件主题
        self.goal_widget.apply_theme()
        self.compare_widget.apply_theme()
        
        # 触发重绘
        self.bar_chart.update()
        self.line_chart.update()
