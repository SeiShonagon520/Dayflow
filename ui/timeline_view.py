"""
Dayflow Windows - 时间轴视图组件
"""
from datetime import datetime, timedelta
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy, QProgressBar, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPalette, QLinearGradient, QPainter, QBrush

from core.types import ActivityCard


# 类别颜色映射
CATEGORY_COLORS = {
    "工作": "#4F46E5",      # Indigo
    "Work": "#4F46E5",
    "学习": "#0EA5E9",      # Sky Blue
    "Study": "#0EA5E9",
    "编程": "#10B981",      # Emerald
    "Coding": "#10B981",
    "会议": "#F59E0B",      # Amber
    "Meeting": "#F59E0B",
    "娱乐": "#EC4899",      # Pink
    "Entertainment": "#EC4899",
    "社交": "#8B5CF6",      # Violet
    "Social": "#8B5CF6",
    "休息": "#6B7280",      # Gray
    "Break": "#6B7280",
    "其他": "#78716C",      # Stone
    "Other": "#78716C",
}


def get_category_color(category: str) -> str:
    """获取类别对应的颜色"""
    return CATEGORY_COLORS.get(category, "#78716C")


class ActivityCardWidget(QFrame):
    """单个活动卡片组件"""
    
    clicked = Signal(ActivityCard)
    
    def __init__(self, card: ActivityCard, parent=None):
        super().__init__(parent)
        self.card = card
        self._setup_ui()
    
    def _setup_ui(self):
        self.setObjectName("activityCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        
        # 顶部：类别标签 + 时间
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)
        
        # 类别标签
        category_label = QLabel(self.card.category or "活动")
        category_label.setObjectName("categoryLabel")
        category_color = get_category_color(self.card.category)
        category_label.setStyleSheet(f"""
            QLabel#categoryLabel {{
                background-color: {category_color}20;
                color: {category_color};
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
            }}
        """)
        top_layout.addWidget(category_label)
        
        # 时间范围
        time_str = self._format_time_range()
        time_label = QLabel(time_str)
        time_label.setObjectName("timeLabel")
        time_label.setStyleSheet("""
            QLabel#timeLabel {
                color: #9CA3AF;
                font-size: 12px;
            }
        """)
        top_layout.addWidget(time_label)
        top_layout.addStretch()
        
        # 生产力评分
        if self.card.productivity_score > 0:
            score_label = QLabel(f"⚡ {int(self.card.productivity_score)}%")
            score_label.setStyleSheet("""
                color: #10B981;
                font-size: 12px;
                font-weight: 600;
            """)
            top_layout.addWidget(score_label)
        
        layout.addLayout(top_layout)
        
        # 标题
        title_label = QLabel(self.card.title or "未命名活动")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("""
            QLabel#titleLabel {
                color: #F9FAFB;
                font-size: 16px;
                font-weight: 600;
            }
        """)
        layout.addWidget(title_label)
        
        # 摘要
        if self.card.summary:
            summary_label = QLabel(self.card.summary)
            summary_label.setObjectName("summaryLabel")
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet("""
                QLabel#summaryLabel {
                    color: #D1D5DB;
                    font-size: 13px;
                    line-height: 1.5;
                }
            """)
            layout.addWidget(summary_label)
        
        # 应用/网站标签
        if self.card.app_sites:
            apps_layout = QHBoxLayout()
            apps_layout.setSpacing(6)
            
            for i, app in enumerate(self.card.app_sites[:4]):  # 最多显示4个
                app_label = QLabel(app.name)
                app_label.setStyleSheet("""
                    background-color: #374151;
                    color: #E5E7EB;
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 11px;
                """)
                apps_layout.addWidget(app_label)
            
            if len(self.card.app_sites) > 4:
                more_label = QLabel(f"+{len(self.card.app_sites) - 4}")
                more_label.setStyleSheet("""
                    color: #9CA3AF;
                    font-size: 11px;
                """)
                apps_layout.addWidget(more_label)
            
            apps_layout.addStretch()
            layout.addLayout(apps_layout)
        
        # 卡片样式
        self.setStyleSheet("""
            QFrame#activityCard {
                background-color: #1F2937;
                border: 1px solid #374151;
                border-radius: 12px;
            }
            QFrame#activityCard:hover {
                background-color: #283548;
                border-color: #4B5563;
            }
        """)
        
        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
    
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


class TimelineHeader(QWidget):
    """时间轴头部 - 显示日期和统计"""
    
    date_changed = Signal(datetime)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_date = datetime.now()
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        
        # 日期显示
        self.date_label = QLabel()
        self.date_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 700;
            color: #F9FAFB;
        """)
        layout.addWidget(self.date_label)
        
        layout.addStretch()
        
        # 统计信息
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("""
            font-size: 14px;
            color: #9CA3AF;
        """)
        layout.addWidget(self.stats_label)
        
        self._update_date_display()
    
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
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[ActivityCard] = []
        self._current_date = datetime.now()
        self._setup_ui()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 头部
        self.header = TimelineHeader()
        main_layout.addWidget(self.header)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                width: 8px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #4B5563;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #6B7280;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        
        # 卡片容器
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(24, 8, 24, 24)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        
        scroll.setWidget(self.cards_container)
        main_layout.addWidget(scroll)
        
        # 空状态提示
        self.empty_label = QLabel("开始录制以生成时间轴")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("""
            font-size: 16px;
            color: #6B7280;
            padding: 60px;
        """)
        self.cards_layout.insertWidget(0, self.empty_label)
    
    def set_cards(self, cards: List[ActivityCard]):
        """设置卡片列表"""
        self._cards = cards
        self._refresh_cards()
    
    def add_card(self, card: ActivityCard):
        """添加单个卡片"""
        self._cards.append(card)
        self._add_card_widget(card)
        self._update_empty_state()
    
    def _refresh_cards(self):
        """刷新所有卡片"""
        # 清除现有卡片
        while self.cards_layout.count() > 1:  # 保留 stretch
            item = self.cards_layout.takeAt(0)
            if item.widget() and item.widget() != self.empty_label:
                item.widget().deleteLater()
        
        # 添加新卡片
        for card in self._cards:
            self._add_card_widget(card, animate=False)
        
        self._update_empty_state()
        self._update_stats()
    
    def _add_card_widget(self, card: ActivityCard, animate: bool = True):
        """添加卡片组件"""
        widget = ActivityCardWidget(card)
        widget.clicked.connect(self.card_selected.emit)
        
        # 插入到 stretch 之前
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, widget)
    
    def _update_empty_state(self):
        """更新空状态显示"""
        self.empty_label.setVisible(len(self._cards) == 0)
    
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
