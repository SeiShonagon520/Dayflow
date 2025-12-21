"""
Dayflow Windows - 数据统计与分析视图
仪表盘风格设计
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QSpinBox, QComboBox,
    QProgressBar, QSizePolicy, QSpacerItem, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath,
    QLinearGradient, QRadialGradient, QPaintEvent
)

from ui.themes import get_theme, get_theme_manager
from database.storage import StorageManager
from core.types import ActivityCard

logger = logging.getLogger(__name__)

# 类别颜色映射 - 更鲜艳的配色
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

# 指标卡片渐变色
METRIC_GRADIENTS = {
    "time": ("#3B82F6", "#1D4ED8"),      # 蓝色
    "efficiency": ("#10B981", "#059669"), # 绿色
    "deep_work": ("#8B5CF6", "#7C3AED"),  # 紫色
    "activities": ("#F59E0B", "#D97706"), # 橙色
}


def normalize_app_name(name: str) -> str:
    """归一化应用名称"""
    if not name:
        return "未命名"
    
    raw = name.strip()
    lower = raw.lower()
    
    if lower.endswith(".exe"):
        lower = lower[:-4]
    
    if "chrome" in lower:
        return "Chrome"
    if "edge" in lower:
        return "Edge"
    if "firefox" in lower:
        return "Firefox"
    if "cursor" in lower:
        return "Cursor"
    if "vscode" in lower or "visual studio code" in lower:
        return "VS Code"
    if "kiro" in lower:
        return "Kiro"
    
    return raw


class MetricCard(QFrame):
    """单个指标卡片 - 仪表盘风格"""
    
    def __init__(self, title: str, icon: str, gradient_key: str = "time", parent=None):
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._value = "0"
        self._unit = ""
        self._change = 0.0
        self._change_text = ""
        self._gradient_key = gradient_key
        self._mini_data: List[float] = []
        
        self.setFixedHeight(120)
        self.setMinimumWidth(160)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        
        # 顶部：图标 + 标题
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        
        self.icon_label = QLabel(self._icon)
        self.icon_label.setStyleSheet("font-size: 16px;")
        top_row.addWidget(self.icon_label)
        
        self.title_label = QLabel(self._title)
        top_row.addWidget(self.title_label)
        top_row.addStretch()
        
        layout.addLayout(top_row)
        
        # 中间：大数字
        self.value_label = QLabel("0")
        layout.addWidget(self.value_label)
        
        # 底部：变化
        self.change_label = QLabel("")
        layout.addWidget(self.change_label)
        
        layout.addStretch()
        
        # 添加阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
    
    def set_value(self, value: str, unit: str = ""):
        """设置数值"""
        self._value = value
        self._unit = unit
        self.value_label.setText(f"{value}<span style='font-size: 14px; opacity: 0.7;'>{unit}</span>")
        self._apply_style()
    
    def set_change(self, change: float, suffix: str = "%"):
        """设置变化值"""
        self._change = change
        if change > 0:
            self._change_text = f"↑ +{change:.0f}{suffix}"
            change_color = "#10B981"
        elif change < 0:
            self._change_text = f"↓ {change:.0f}{suffix}"
            change_color = "#EF4444"
        else:
            self._change_text = "— 持平"
            change_color = "#9CA3AF"
        
        self.change_label.setText(f"vs 上周 {self._change_text}")
        self.change_label.setStyleSheet(f"font-size: 11px; color: {change_color};")
    
    def _apply_style(self):
        """应用样式"""
        t = get_theme()
        colors = METRIC_GRADIENTS.get(self._gradient_key, METRIC_GRADIENTS["time"])
        
        # 根据主题调整背景
        if t.name == "dark":
            bg_color = t.bg_secondary
            border_color = t.border
        else:
            bg_color = "#FFFFFF"
            border_color = "#E5E7EB"
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 16px;
                border-left: 4px solid {colors[0]};
            }}
        """)
        
        self.title_label.setStyleSheet(f"""
            font-size: 12px;
            color: {t.text_muted};
            font-weight: 500;
        """)
        
        self.value_label.setStyleSheet(f"""
            font-size: 28px;
            font-weight: 700;
            color: {t.text_primary};
        """)
    
    def apply_theme(self):
        self._apply_style()


class MetricCardsRow(QWidget):
    """顶部指标卡片行"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # 4 个指标卡片
        self.time_card = MetricCard("总时长", "⏱️", "time")
        self.efficiency_card = MetricCard("平均效率", "⚡", "efficiency")
        self.deep_work_card = MetricCard("深度工作", "🔥", "deep_work")
        self.activities_card = MetricCard("活动数", "📊", "activities")
        
        layout.addWidget(self.time_card)
        layout.addWidget(self.efficiency_card)
        layout.addWidget(self.deep_work_card)
        layout.addWidget(self.activities_card)
    
    def set_data(self, total_hours: float, avg_efficiency: float, deep_work_count: int, 
                 activity_count: int, prev_hours: float = 0, prev_efficiency: float = 0,
                 prev_deep_work: int = 0, prev_activities: int = 0):
        """设置数据"""
        # 总时长
        self.time_card.set_value(f"{total_hours:.1f}", "h")
        if prev_hours > 0:
            change = ((total_hours - prev_hours) / prev_hours) * 100
            self.time_card.set_change(change)
        
        # 效率
        self.efficiency_card.set_value(f"{avg_efficiency:.0f}", "%")
        if prev_efficiency > 0:
            change = avg_efficiency - prev_efficiency
            self.efficiency_card.set_change(change, "pt")
        
        # 深度工作
        self.deep_work_card.set_value(f"{deep_work_count}", "次")
        if prev_deep_work > 0:
            change = deep_work_count - prev_deep_work
            self.deep_work_card.set_change(change, "")
        
        # 活动数
        self.activities_card.set_value(f"{activity_count}", "个")
        if prev_activities > 0:
            change = ((activity_count - prev_activities) / prev_activities) * 100
            self.activities_card.set_change(change)
    
    def apply_theme(self):
        self.time_card.apply_theme()
        self.efficiency_card.apply_theme()
        self.deep_work_card.apply_theme()
        self.activities_card.apply_theme()


class DonutChart(QWidget):
    """环形图组件（精致版 - 带阴影和动画效果）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Tuple[str, float, str]] = []  # [(label, value, color)]
        self._total = 0
        self._center_text = ""
        self._center_subtext = ""
        self.setMinimumSize(200, 200)
        self.setMouseTracking(True)
        self._hovered_index = -1
    
    def set_data(self, data: List[Tuple[str, float, str]], center_text: str = "", center_subtext: str = ""):
        """设置数据 [(标签, 数值, 颜色)]"""
        self._data = data
        self._total = sum(v for _, v, _ in data) if data else 0
        self._center_text = center_text
        self._center_subtext = center_subtext
        self.update()
    
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        t = get_theme()
        
        # 计算尺寸
        size = min(self.width(), self.height())
        outer_radius = size / 2 - 15
        inner_radius = outer_radius * 0.62
        center = QPointF(self.width() / 2, self.height() / 2)
        
        if not self._data or self._total <= 0:
            # 无数据时画空环
            painter.setPen(QPen(QColor(t.border), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, outer_radius, outer_radius)
            
            painter.setPen(QPen(QColor(t.text_muted)))
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            painter.end()
            return
        
        # 绘制内圈阴影效果
        shadow_gradient = QRadialGradient(center, inner_radius * 1.1)
        shadow_color = QColor(0, 0, 0, 20)
        shadow_gradient.setColorAt(0.8, shadow_color)
        shadow_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, inner_radius * 1.1, inner_radius * 1.1)
        
        # 绘制各段
        start_angle = 90 * 16  # 从顶部开始
        gap_angle = 2 * 16  # 段之间的间隙
        
        for idx, (label, value, color) in enumerate(self._data):
            if value <= 0:
                continue
            
            span_angle = int((value / self._total) * 360 * 16) - gap_angle
            if span_angle <= 0:
                continue
            
            # 创建扇形路径
            path = QPainterPath()
            
            # 悬停时稍微放大
            hover_offset = 3 if idx == self._hovered_index else 0
            r_outer = outer_radius + hover_offset
            r_inner = inner_radius
            
            rect = QRectF(center.x() - r_outer, center.y() - r_outer,
                         r_outer * 2, r_outer * 2)
            inner_rect = QRectF(center.x() - r_inner, center.y() - r_inner,
                               r_inner * 2, r_inner * 2)
            
            path.arcMoveTo(rect, start_angle / 16)
            path.arcTo(rect, start_angle / 16, span_angle / 16)
            path.arcTo(inner_rect, (start_angle + span_angle) / 16, -span_angle / 16)
            path.closeSubpath()
            
            # 渐变填充
            base_color = QColor(color)
            gradient = QRadialGradient(center, r_outer)
            lighter = QColor(base_color)
            lighter.setAlpha(255)
            gradient.setColorAt(0.5, lighter)
            gradient.setColorAt(1.0, base_color)
            
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawPath(path)
            
            start_angle += span_angle + gap_angle
        
        # 绘制内圈背景
        painter.setBrush(QBrush(QColor(t.bg_secondary)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, inner_radius, inner_radius)
        
        # 绘制中心文字
        painter.setPen(QPen(QColor(t.text_primary)))
        painter.setFont(QFont("Microsoft YaHei", 22, QFont.Bold))
        
        text_rect = QRectF(center.x() - inner_radius, center.y() - 18,
                          inner_radius * 2, 30)
        painter.drawText(text_rect, Qt.AlignCenter, self._center_text)
        
        # 副标题
        painter.setFont(QFont("Microsoft YaHei", 10))
        painter.setPen(QPen(QColor(t.text_muted)))
        subtext_rect = QRectF(center.x() - inner_radius, center.y() + 12,
                             inner_radius * 2, 20)
        painter.drawText(subtext_rect, Qt.AlignCenter, self._center_subtext)
        
        painter.end()
    
    def mouseMoveEvent(self, event):
        """鼠标移动检测悬停"""
        if not self._data or self._total <= 0:
            return
        
        center = QPointF(self.width() / 2, self.height() / 2)
        pos = event.position()
        
        # 计算鼠标相对于中心的角度和距离
        dx = pos.x() - center.x()
        dy = center.y() - pos.y()  # Y 轴翻转
        
        import math
        distance = math.sqrt(dx * dx + dy * dy)
        
        size = min(self.width(), self.height())
        outer_radius = size / 2 - 15
        inner_radius = outer_radius * 0.62
        
        # 检查是否在环形区域内
        if inner_radius < distance < outer_radius:
            # 计算角度（从顶部顺时针）
            angle = math.degrees(math.atan2(dx, dy))
            if angle < 0:
                angle += 360
            
            # 找到对应的段
            current_angle = 0
            gap_angle = 2  # 度
            
            for idx, (label, value, color) in enumerate(self._data):
                if value <= 0:
                    continue
                span = (value / self._total) * 360 - gap_angle
                if current_angle <= angle < current_angle + span:
                    if self._hovered_index != idx:
                        self._hovered_index = idx
                        minutes = value
                        hours = minutes / 60
                        self.setToolTip(f"{label}\n{hours:.1f}h ({value / self._total * 100:.1f}%)")
                        self.update()
                    return
                current_angle += span + gap_angle
        
        if self._hovered_index != -1:
            self._hovered_index = -1
            self.setToolTip("")
            self.update()
    
    def leaveEvent(self, event):
        if self._hovered_index != -1:
            self._hovered_index = -1
            self.setToolTip("")
            self.update()


class BarChartWidget(QWidget):
    """柱状图组件 - 显示每日时间分布（精致版）"""
    
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
            
            # 网格线（更淡）
            grid_color = QColor(t.border)
            grid_color.setAlpha(80)
            painter.setPen(QPen(grid_color, 1, Qt.DotLine))
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
        bar_width = min(bar_width, 45)  # 最大宽度 45
        
        # 重新计算以居中
        total_bars_width = bar_count * bar_width + (bar_count - 1) * gap
        start_x = margin_left + (chart_width - total_bars_width) / 2
        
        # 绘制柱状图
        for i, day_data in enumerate(self._data):
            x = start_x + i * (bar_width + gap)
            categories = day_data.get("categories", {})
            
            # 计算总高度用于绘制背景
            total_minutes = sum(categories.values())
            
            # 绘制柱子背景（淡色）
            bg_color = QColor(t.bg_tertiary)
            bg_color.setAlpha(60)
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.NoPen)
            bg_rect = QRectF(x, margin_top, bar_width, chart_height)
            painter.drawRoundedRect(bg_rect, 6, 6)
            
            # 堆叠绘制各类别
            current_y = margin_top + chart_height
            for cat, minutes in categories.items():
                bar_height = (minutes / 60 / y_max) * chart_height
                if bar_height < 2:
                    continue
                
                color = QColor(CATEGORY_COLORS.get(cat, "#94A3B8"))
                
                # 创建渐变
                gradient = QLinearGradient(x, current_y - bar_height, x, current_y)
                lighter = QColor(color)
                lighter.setAlpha(220)
                gradient.setColorAt(0, lighter)
                gradient.setColorAt(1, color)
                
                painter.setBrush(QBrush(gradient))
                painter.setPen(Qt.NoPen)
                
                rect = QRectF(x, current_y - bar_height, bar_width, bar_height)
                painter.drawRoundedRect(rect, 4, 4)
                
                current_y -= bar_height
            
            # X 轴标签（日期）
            date_str = day_data.get("date", "")
            if len(date_str) >= 5:
                label = date_str[-5:]  # MM-DD
            else:
                label = date_str
            
            painter.setPen(QPen(QColor(t.text_secondary), 1))
            painter.setFont(QFont("Microsoft YaHei", 8))
            text_rect = QRectF(x - 5, height - margin_bottom + 5, bar_width + 10, 20)
            painter.drawText(text_rect, Qt.AlignCenter, label)
        
        painter.end()


class LineChartWidget(QWidget):
    """折线图组件 - 显示生产力趋势（渐变填充 + 圆滑曲线）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []  # [(date, score)]
        self.setMinimumHeight(220)
        self.setMinimumWidth(400)
    
    def set_data(self, data: List[Tuple[str, float]]):
        """设置数据 [(日期, 分数)]"""
        self._data = data
        self.update()
    
    def _smooth_curve(self, points: List[Tuple[float, float]]) -> QPainterPath:
        """生成平滑曲线路径"""
        path = QPainterPath()
        if len(points) < 2:
            return path
        
        path.moveTo(points[0][0], points[0][1])
        
        for i in range(1, len(points)):
            # 使用贝塞尔曲线实现平滑
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            
            # 控制点
            ctrl_x = (x0 + x1) / 2
            
            path.cubicTo(ctrl_x, y0, ctrl_x, y1, x1, y1)
        
        return path
    
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
        
        # 绘制渐变填充区域
        if points:
            # 创建平滑曲线路径
            curve_points = [(p[0], p[1]) for p in points]
            curve_path = self._smooth_curve(curve_points)
            
            # 创建填充路径
            fill_path = QPainterPath(curve_path)
            fill_path.lineTo(points[-1][0], margin_top + chart_height)
            fill_path.lineTo(points[0][0], margin_top + chart_height)
            fill_path.closeSubpath()
            
            # 渐变填充
            gradient = QLinearGradient(0, margin_top, 0, margin_top + chart_height)
            accent_color = QColor(t.accent)
            accent_color.setAlpha(60)
            gradient.setColorAt(0, accent_color)
            accent_color.setAlpha(5)
            gradient.setColorAt(1, accent_color)
            
            painter.fillPath(fill_path, QBrush(gradient))
            
            # 绘制平滑曲线
            painter.setPen(QPen(QColor(t.accent), 2.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(curve_path)
        
        # 绘制数据点和 X 轴标签
        painter.setFont(QFont("Microsoft YaHei", 8))
        show_label_interval = max(1, len(points) // 7)  # 最多显示 7 个标签
        
        for i, (x, y, date, score) in enumerate(points):
            # 数据点 - 带光晕效果
            # 外圈光晕
            glow_color = QColor(t.accent)
            glow_color.setAlpha(50)
            painter.setBrush(QBrush(glow_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(x) - 8, int(y) - 8, 16, 16)
            
            # 内圈
            painter.setBrush(QBrush(QColor(t.bg_primary)))
            painter.setPen(QPen(QColor(t.accent), 2.5))
            painter.drawEllipse(int(x) - 5, int(y) - 5, 10, 10)
            
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


class HourlyHeatmapWidget(QWidget):
    """每小时效率热力图 - 显示一天中各时段的效率分布（精致版）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Dict[int, Tuple[float, float]] = {}  # hour -> (avg_score, total_minutes)
        self.setMinimumHeight(100)
        self.setMinimumWidth(400)
        self.setMouseTracking(True)
        self._hovered_hour = -1
    
    def set_data(self, data: Dict[int, Tuple[float, float]]):
        """设置数据 {hour: (avg_score, total_minutes)}"""
        self._data = data
        self.update()
    
    def paintEvent(self, event):
        """绘制热力图"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        t = get_theme()
        width = self.width()
        height = self.height()
        
        margin_left = 10
        margin_right = 10
        margin_top = 10
        margin_bottom = 25
        
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        
        if chart_width <= 0 or chart_height <= 0:
            return
        
        cell_width = chart_width / 24
        cell_height = min(chart_height, 40)
        cell_y = margin_top + (chart_height - cell_height) / 2
        
        # 绘制每个小时的格子
        for hour in range(24):
            x = margin_left + hour * cell_width
            
            # 获取该小时的数据
            score, minutes = self._data.get(hour, (0, 0))
            
            # 根据效率分数计算颜色
            if minutes > 0:
                # 有数据：根据分数显示颜色（渐变效果）
                if score >= 70:
                    base_color = QColor("#10B981")  # 绿色 - 高效
                elif score >= 50:
                    base_color = QColor("#3B82F6")  # 蓝色 - 中等
                elif score >= 30:
                    base_color = QColor("#F59E0B")  # 黄色 - 一般
                else:
                    base_color = QColor("#EF4444")  # 红色 - 低效
                
                # 根据时长调整透明度（更细腻的渐变）
                alpha = min(255, int(120 + minutes * 1.5))
                base_color.setAlpha(alpha)
            else:
                # 无数据：淡灰色
                base_color = QColor(t.bg_tertiary)
                base_color.setAlpha(100)
            
            # 绘制圆角格子
            rect = QRectF(x + 2, cell_y, cell_width - 4, cell_height)
            
            # 悬停效果
            if hour == self._hovered_hour:
                # 高亮边框
                painter.setPen(QPen(QColor(t.accent), 2))
                painter.setBrush(QBrush(base_color))
                painter.drawRoundedRect(rect, 6, 6)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(base_color))
                painter.drawRoundedRect(rect, 6, 6)
        
        # 绘制 X 轴标签（每隔 4 小时）
        painter.setPen(QPen(QColor(t.text_muted)))
        painter.setFont(QFont("Microsoft YaHei", 9))
        for hour in [0, 4, 8, 12, 16, 20, 24]:
            if hour == 24:
                x = margin_left + 23 * cell_width + cell_width
            else:
                x = margin_left + hour * cell_width
            label = f"{hour:02d}:00" if hour < 24 else ""
            if hour < 24:
                painter.drawText(int(x) - 15, height - 5, label)
        
        painter.end()
    
    def mouseMoveEvent(self, event):
        """鼠标移动显示 tooltip"""
        margin_left = 10
        chart_width = self.width() - margin_left - 10
        cell_width = chart_width / 24
        
        x = event.position().x() - margin_left
        if 0 <= x < chart_width:
            hour = int(x / cell_width)
            if 0 <= hour < 24:
                self._hovered_hour = hour
                score, minutes = self._data.get(hour, (0, 0))
                
                if minutes > 0:
                    self.setToolTip(f"{hour:02d}:00 - {hour+1:02d}:00\n效率: {score:.0f}%\n时长: {minutes:.0f}分钟")
                else:
                    self.setToolTip(f"{hour:02d}:00 - {hour+1:02d}:00\n无数据")
                
                self.update()
                return
        
        self._hovered_hour = -1
        self.setToolTip("")
        self.update()
    
    def leaveEvent(self, event):
        self._hovered_hour = -1
        self.update()


class WeekCompareWidget(QWidget):
    """周对比组件 - 本周 vs 上周"""
    
    def __init__(self, storage: StorageManager, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._this_week_data: Dict[str, float] = {}
        self._last_week_data: Dict[str, float] = {}
        self._this_week_score = 0
        self._last_week_score = 0
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 总览对比
        self.summary_layout = QHBoxLayout()
        self.summary_layout.setSpacing(20)
        layout.addLayout(self.summary_layout)
        
        # 详细对比容器
        self.detail_container = QVBoxLayout()
        self.detail_container.setSpacing(8)
        layout.addLayout(self.detail_container)
    
    def load_data(self):
        """加载本周和上周数据"""
        today = datetime.now()
        
        # 计算本周起始（周一）
        days_since_monday = today.weekday()
        this_week_start = today - timedelta(days=days_since_monday)
        last_week_start = this_week_start - timedelta(days=7)
        
        self._this_week_data = self._get_week_stats(this_week_start)
        self._last_week_data = self._get_week_stats(last_week_start)
        
        self._update_display()
    
    def _get_week_stats(self, start_date: datetime) -> Dict[str, float]:
        """获取一周的统计数据"""
        stats = {}
        total_score = 0
        score_count = 0
        
        for i in range(7):
            date = start_date + timedelta(days=i)
            if date > datetime.now():
                break
            
            cards = self.storage.get_cards_for_date(date)
            for card in cards:
                cat = card.category or "其他"
                stats[cat] = stats.get(cat, 0) + card.duration_minutes
                
                if card.productivity_score > 0:
                    total_score += card.productivity_score
                    score_count += 1
        
        # 存储平均分数
        if score_count > 0:
            stats["_avg_score"] = total_score / score_count
        else:
            stats["_avg_score"] = 0
        
        return stats
    
    def _update_display(self):
        """更新显示"""
        t = get_theme()
        
        # 清除旧内容
        while self.summary_layout.count():
            item = self.summary_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        while self.detail_container.count():
            item = self.detail_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 计算总时长
        this_total = sum(v for k, v in self._this_week_data.items() if not k.startswith("_"))
        last_total = sum(v for k, v in self._last_week_data.items() if not k.startswith("_"))
        
        this_score = self._this_week_data.get("_avg_score", 0)
        last_score = self._last_week_data.get("_avg_score", 0)
        
        # 总览卡片
        self._add_summary_card("本周总时长", this_total, last_total, "分钟", self.summary_layout)
        self._add_summary_card("本周效率", this_score, last_score, "%", self.summary_layout)
        
        self.summary_layout.addStretch()
        
        # 分类对比
        all_cats = set(self._this_week_data.keys()) | set(self._last_week_data.keys())
        all_cats = {c for c in all_cats if not c.startswith("_")}
        
        for cat in sorted(all_cats):
            this_val = self._this_week_data.get(cat, 0)
            last_val = self._last_week_data.get(cat, 0)
            
            row = QHBoxLayout()
            row.setSpacing(10)
            
            # 类别颜色
            color_box = QLabel()
            color_box.setFixedSize(10, 10)
            color_box.setStyleSheet(f"background-color: {CATEGORY_COLORS.get(cat, '#94A3B8')}; border-radius: 2px;")
            row.addWidget(color_box)
            
            # 类别名
            cat_label = QLabel(cat)
            cat_label.setFixedWidth(50)
            cat_label.setStyleSheet(f"color: {t.text_primary}; font-size: 12px;")
            row.addWidget(cat_label)
            
            # 本周
            this_label = QLabel(f"{this_val:.0f}m")
            this_label.setFixedWidth(60)
            this_label.setAlignment(Qt.AlignRight)
            this_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
            row.addWidget(this_label)
            
            # 变化
            diff = this_val - last_val
            if diff > 0:
                diff_text = f"↑ +{diff:.0f}m"
                diff_color = "#10B981"
            elif diff < 0:
                diff_text = f"↓ {diff:.0f}m"
                diff_color = "#EF4444"
            else:
                diff_text = "—"
                diff_color = t.text_muted
            
            diff_label = QLabel(diff_text)
            diff_label.setFixedWidth(80)
            diff_label.setAlignment(Qt.AlignCenter)
            diff_label.setStyleSheet(f"color: {diff_color}; font-size: 12px; font-weight: bold;")
            row.addWidget(diff_label)
            
            # 上周
            last_label = QLabel(f"{last_val:.0f}m")
            last_label.setFixedWidth(60)
            last_label.setStyleSheet(f"color: {t.text_muted}; font-size: 12px;")
            row.addWidget(last_label)
            
            row.addStretch()
            
            container = QWidget()
            container.setLayout(row)
            self.detail_container.addWidget(container)
    
    def _add_summary_card(self, title: str, this_val: float, last_val: float, unit: str, layout: QHBoxLayout):
        """添加总览卡片"""
        t = get_theme()
        
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {t.bg_tertiary};
                border-radius: 12px;
                padding: 12px;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(4)
        
        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
        card_layout.addWidget(title_label)
        
        # 数值
        if unit == "分钟":
            hours = this_val / 60
            value_text = f"{hours:.1f}h"
        else:
            value_text = f"{this_val:.0f}{unit}"
        
        value_label = QLabel(value_text)
        value_label.setStyleSheet(f"color: {t.text_primary}; font-size: 20px; font-weight: bold;")
        card_layout.addWidget(value_label)
        
        # 变化
        diff = this_val - last_val
        if last_val > 0:
            percent = (diff / last_val) * 100
            if diff > 0:
                change_text = f"↑ {percent:.0f}%"
                change_color = "#10B981"
            elif diff < 0:
                change_text = f"↓ {abs(percent):.0f}%"
                change_color = "#EF4444"
            else:
                change_text = "持平"
                change_color = t.text_muted
        else:
            change_text = "—"
            change_color = t.text_muted
        
        change_label = QLabel(f"vs 上周 {change_text}")
        change_label.setStyleSheet(f"color: {change_color}; font-size: 11px;")
        card_layout.addWidget(change_label)
        
        layout.addWidget(card)
    
    def apply_theme(self):
        self._update_display()


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


class AppUsageListWidget(QWidget):
    """应用/网站使用时长榜单"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []  # [(name, minutes)]
        self._setup_ui()
        self.apply_theme()
        get_theme_manager().theme_changed.connect(self.apply_theme)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.rows_container = QVBoxLayout()
        self.rows_container.setSpacing(8)
        layout.addLayout(self.rows_container)
        
        self.empty_label = QLabel("暂无应用使用数据")
        self.empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_label)
    
    def set_data(self, data: List[Tuple[str, float]]):
        """设置应用使用数据（分钟）"""
        self._data = data
        self._refresh()
    
    def _refresh(self):
        # 清空旧行
        while self.rows_container.count():
            item = self.rows_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self._data:
            self.empty_label.show()
            return
        
        self.empty_label.hide()
        t = get_theme()
        
        total_minutes = sum(m for _, m in self._data) or 1
        top_items = self._data[:10]  # 只展示前 10 个
        
        for name, minutes in top_items:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            
            name_label = QLabel(name or "未命名")
            name_label.setFixedWidth(160)
            name_label.setStyleSheet(f"color: {t.text_primary}; font-size: 12px;")
            row_layout.addWidget(name_label)
            
            bar = QProgressBar()
            bar.setRange(0, 100)
            percent = minutes / total_minutes * 100
            bar.setValue(int(percent))
            bar.setTextVisible(False)
            bar.setFixedHeight(12)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {t.bg_tertiary};
                    border: none;
                    border-radius: 6px;
                }}
                QProgressBar::chunk {{
                    background-color: {t.accent};
                    border-radius: 6px;
                }}
            """)
            row_layout.addWidget(bar, 1)
            
            time_label = QLabel(self._format_minutes(minutes))
            time_label.setFixedWidth(70)
            time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            time_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
            row_layout.addWidget(time_label)
            
            container = QWidget()
            container.setLayout(row_layout)
            self.rows_container.addWidget(container)
    
    def _format_minutes(self, minutes: float) -> str:
        if minutes >= 60:
            h = int(minutes // 60)
            m = int(minutes % 60)
            return f"{h}h{m:02d}m" if m else f"{h}h"
        return f"{int(minutes)}m"
    
    def apply_theme(self):
        t = get_theme()
        self.setStyleSheet("")
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; font-size: 13px; padding: 8px 0;")
        # 重新渲染行以应用主题色
        self._refresh()


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
        layout.setSpacing(20)
        
        # ===== 标题行 =====
        header_row = QHBoxLayout()
        header_row.setSpacing(16)
        
        title = QLabel("📊 数据统计")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        header_row.addWidget(title)
        
        header_row.addStretch()
        
        # 时间范围选择
        self.week_btn = QPushButton("本周")
        self.week_btn.setCheckable(True)
        self.week_btn.setChecked(True)
        self.week_btn.clicked.connect(lambda: self._set_range("week"))
        header_row.addWidget(self.week_btn)
        
        self.month_btn = QPushButton("本月")
        self.month_btn.setCheckable(True)
        self.month_btn.clicked.connect(lambda: self._set_range("month"))
        header_row.addWidget(self.month_btn)
        
        layout.addLayout(header_row)
        
        # ===== 顶部指标卡片 =====
        self.metric_cards = MetricCardsRow()
        layout.addWidget(self.metric_cards)
        
        # ===== 双栏布局区域 =====
        grid_row = QHBoxLayout()
        grid_row.setSpacing(16)
        
        # 左栏
        left_col = QVBoxLayout()
        left_col.setSpacing(16)
        
        # 时间分布（柱状图）
        chart_section = self._create_section("时间分布")
        self.bar_chart = BarChartWidget()
        chart_section.layout().addWidget(self.bar_chart)
        self.legend = CategoryLegend()
        chart_section.layout().addWidget(self.legend)
        left_col.addWidget(chart_section)
        
        # 生产力趋势（折线图）
        trend_section = self._create_section("生产力趋势")
        self.line_chart = LineChartWidget()
        trend_section.layout().addWidget(self.line_chart)
        left_col.addWidget(trend_section)
        
        # 时段效率热力图
        heatmap_section = self._create_section("时段效率分布")
        self.heatmap_widget = HourlyHeatmapWidget()
        heatmap_section.layout().addWidget(self.heatmap_widget)
        left_col.addWidget(heatmap_section)
        
        grid_row.addLayout(left_col, 3)  # 左栏占 3 份
        
        # 右栏
        right_col = QVBoxLayout()
        right_col.setSpacing(16)
        
        # 类别分布（环形图）
        donut_section = self._create_section("类别分布")
        self.donut_chart = DonutChart()
        self.donut_chart.setMinimumSize(200, 200)
        self.donut_chart.setMaximumHeight(220)
        donut_section.layout().addWidget(self.donut_chart, alignment=Qt.AlignCenter)
        # 环形图图例
        self.donut_legend = CategoryLegend()
        donut_section.layout().addWidget(self.donut_legend)
        right_col.addWidget(donut_section)
        
        # 今日目标
        goal_section = self._create_section("今日目标")
        self.goal_widget = GoalWidget()
        self.goal_widget.goal_changed.connect(self._on_goal_changed)
        goal_section.layout().addWidget(self.goal_widget)
        right_col.addWidget(goal_section)
        
        # 周对比
        week_compare_section = self._create_section("本周 vs 上周")
        self.week_compare_widget = WeekCompareWidget(self.storage)
        week_compare_section.layout().addWidget(self.week_compare_widget)
        right_col.addWidget(week_compare_section)
        
        right_col.addStretch()
        grid_row.addLayout(right_col, 2)  # 右栏占 2 份
        
        layout.addLayout(grid_row)
        
        # ===== 底部全宽区域 =====
        # 应用/网站使用
        self.app_section = self._create_section("应用 / 网站使用")
        self.app_section_title = self.app_section.findChild(QLabel, "sectionTitle")
        self.app_usage_widget = AppUsageListWidget()
        self.app_section.layout().addWidget(self.app_usage_widget)
        layout.addWidget(self.app_section)
        
        # 日期对比
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
        
        # 根据时间范围更新应用分区标题文案
        if self.app_section_title:
            if range_type == "week":
                self.app_section_title.setText("本周应用 / 网站使用")
            else:
                self.app_section_title.setText("本月应用 / 网站使用")
        
        self._load_data()
    
    def _load_data(self):
        """加载统计数据 - 优化版本"""
        # 防止重复加载
        if hasattr(self, '_loading') and self._loading:
            return
        self._loading = True
        
        try:
            today = datetime.now()
            
            if self._current_range == "week":
                days = 7
            else:
                days = 30
            
            # 暂停更新
            self.bar_chart.setUpdatesEnabled(False)
            self.line_chart.setUpdatesEnabled(False)
            
            # 收集每日数据
            bar_data: List[Dict] = []
            trend_data: List[Tuple[str, float]] = []
            total_today_minutes = 0
            app_usage_by_range: Dict[str, float] = {}
            hourly_data: Dict[int, List[Tuple[float, float]]] = {h: [] for h in range(24)}  # 热力图数据
            
            # 汇总数据（用于指标卡片和环形图）
            total_minutes_range = 0
            total_score_range = 0
            score_count_range = 0
            deep_work_count = 0
            activity_count = 0
            category_minutes: Dict[str, float] = {}
            
            # 上周数据（用于对比）
            prev_total_minutes = 0
            prev_total_score = 0
            prev_score_count = 0
            prev_deep_work = 0
            prev_activities = 0
            
            # 加载上周数据
            for i in range(days + days - 1, days - 1, -1):
                date = today - timedelta(days=i)
                cards = self.storage.get_cards_for_date(date)
                
                for card in cards:
                    prev_total_minutes += card.duration_minutes
                    prev_activities += 1
                    if card.productivity_score > 0:
                        prev_total_score += card.productivity_score
                        prev_score_count += 1
                    if card.duration_minutes >= 60:
                        prev_deep_work += 1
            
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
                    
                    # 汇总统计
                    total_minutes_range += minutes
                    category_minutes[cat] = category_minutes.get(cat, 0) + minutes
                    activity_count += 1
                    
                    if card.productivity_score > 0:
                        total_score += card.productivity_score
                        score_count += 1
                        total_score_range += card.productivity_score
                        score_count_range += 1
                    
                    # 深度工作（60分钟以上）
                    if minutes >= 60:
                        deep_work_count += 1
                    
                    # 收集热力图数据（按小时）
                    if card.start_time:
                        hour = card.start_time.hour
                        hourly_data[hour].append((card.productivity_score, card.duration_minutes))
                    
                    # 统计当前时间范围内的应用/网站使用（周/月）
                    if card.app_sites:
                        # 先做 duration_seconds 的兜底与归一化，避免与卡片总时长严重不符
                        card_total_seconds = max(card.duration_minutes, 0) * 60
                        raw_seconds = [max(getattr(app, "duration_seconds", 0) or 0, 0) for app in card.app_sites]
                        sum_app_seconds = sum(raw_seconds)
                        
                        normalized_seconds: List[float] = []
                        if card_total_seconds > 0:
                            if sum_app_seconds <= 0:
                                # 全为 0：平均分配
                                per = card_total_seconds / len(card.app_sites)
                                normalized_seconds = [per] * len(card.app_sites)
                            else:
                                # 归一化为与卡片总时长接近
                                ratio = card_total_seconds / sum_app_seconds
                                normalized_seconds = [s * ratio for s in raw_seconds]
                        else:
                            normalized_seconds = raw_seconds
                        
                        for app, sec in zip(card.app_sites, normalized_seconds):
                            if sec <= 0:
                                continue
                            minutes_app = sec / 60
                            key = normalize_app_name(app.name)
                            app_usage_by_range[key] = app_usage_by_range.get(key, 0) + minutes_app
                
                bar_data.append({
                    "date": date_str,
                    "categories": categories
                })
                
                avg_score = total_score / score_count if score_count > 0 else 0
                trend_data.append((date_str, avg_score))
                
                # 今日总时间
                if i == 0:
                    total_today_minutes = sum(categories.values())
            
            # 更新顶部指标卡片
            total_hours = total_minutes_range / 60
            avg_efficiency = total_score_range / score_count_range if score_count_range > 0 else 0
            prev_hours = prev_total_minutes / 60
            prev_efficiency = prev_total_score / prev_score_count if prev_score_count > 0 else 0
            
            self.metric_cards.set_data(
                total_hours=total_hours,
                avg_efficiency=avg_efficiency,
                deep_work_count=deep_work_count,
                activity_count=activity_count,
                prev_hours=prev_hours,
                prev_efficiency=prev_efficiency,
                prev_deep_work=prev_deep_work,
                prev_activities=prev_activities
            )
            
            # 更新环形图
            donut_data = []
            for cat, minutes in sorted(category_minutes.items(), key=lambda x: x[1], reverse=True):
                color = CATEGORY_COLORS.get(cat, "#94A3B8")
                donut_data.append((cat, minutes, color))
            
            center_text = f"{total_hours:.1f}h"
            center_subtext = "总时长"
            self.donut_chart.set_data(donut_data, center_text, center_subtext)
            
            # 更新图表
            self.bar_chart.set_data(bar_data)
            self.line_chart.set_data(trend_data)
            
            # 更新目标进度
            self.goal_widget.set_current_hours(total_today_minutes / 60)
            
            # 更新应用使用榜单（基于当前时间范围的汇总）
            sorted_usage = sorted(app_usage_by_range.items(), key=lambda x: x[1], reverse=True)
            self.app_usage_widget.set_data(sorted_usage)
            
            # 更新热力图
            heatmap_data = {}
            for hour, items in hourly_data.items():
                if items:
                    avg_score = sum(s for s, m in items) / len(items)
                    total_minutes = sum(m for s, m in items)
                    heatmap_data[hour] = (avg_score, total_minutes)
            self.heatmap_widget.set_data(heatmap_data)
            
            # 更新周对比
            self.week_compare_widget.load_data()
            
            # 加载保存的目标
            goal = self.storage.get_setting("daily_goal", "8")
            try:
                self.goal_widget.set_goal(int(goal))
            except ValueError:
                pass
        finally:
            # 恢复更新
            self.bar_chart.setUpdatesEnabled(True)
            self.line_chart.setUpdatesEnabled(True)
            self._loading = False
    
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
        
        # 按钮样式 - Apple 风格
        btn_style = f"""
            QPushButton {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 10px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 500;
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
        
        # 分区样式 - Apple 风格大圆角
        self.setStyleSheet(f"""
            QFrame#statsSection {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 16px;
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
        self.metric_cards.apply_theme()
        self.goal_widget.apply_theme()
        self.compare_widget.apply_theme()
        self.app_usage_widget.apply_theme()
        self.week_compare_widget.apply_theme()
        
        # 触发重绘
        self.bar_chart.update()
        self.line_chart.update()
        self.heatmap_widget.update()
        self.donut_chart.update()
