"""
Dayflow - 仪表盘导出器
生成 HTML 格式的生产力报告
"""
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict

from jinja2 import Environment, FileSystemLoader

from database.storage import StorageManager
from core.stats_collector import StatsCollector, CATEGORY_COLORS

logger = logging.getLogger(__name__)


@dataclass
class DashboardData:
    """仪表盘数据容器"""
    # 基本信息
    title: str
    date_range: str
    generated_at: str
    
    # 概览统计
    total_duration_minutes: float
    total_duration_formatted: str
    avg_productivity_score: float
    deep_work_minutes: float
    deep_work_formatted: str
    activity_count: int
    
    # 图表数据
    category_distribution: List[Dict]
    hourly_efficiency: List[Dict]
    weekly_trend: List[Dict]
    top_applications: List[Dict]
    
    # 活动列表
    activities: List[Dict]
    categories: List[str]
    category_colors: Dict[str, str]


def format_duration(minutes: float) -> str:
    """
    将分钟数格式化为可读字符串
    
    Args:
        minutes: 分钟数
        
    Returns:
        格式化字符串，如 "2h 30m" 或 "45m"
    """
    minutes = int(minutes + 0.5)
    if minutes < 1:
        return "0m"
    
    hours = minutes // 60
    mins = minutes % 60
    
    if hours > 0 and mins > 0:
        return f"{hours}h {mins}m"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{mins}m"


class DashboardExporter:
    """仪表盘导出器"""
    
    def __init__(self, storage: StorageManager):
        self.storage = storage
        self.stats = StatsCollector(storage)
        
        # 模板目录 - 支持打包后的路径
        self.template_dir = self._get_template_dir()
        self.env = Environment(loader=FileSystemLoader(self.template_dir), autoescape=True)
    
    def _get_template_dir(self) -> Path:
        """获取模板目录路径"""
        if getattr(sys, "frozen", False):
            base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            packed_path = base_dir / "templates"
            if packed_path.exists():
                return packed_path
        
        # 开发环境路径
        dev_path = Path(__file__).parent.parent / "templates"
        if dev_path.exists():
            return dev_path
        
        raise FileNotFoundError("模板目录不存在")

    def render(self, start_date: date, end_date: date) -> str:
        return self._render_template(self._collect_data(start_date, end_date))

    def _collect_data(self, start_date: date, end_date: date) -> DashboardData:
        """收集指定日期范围的数据"""
        self.stats.load(start_date, end_date)
        totals = self.stats.summary(start_date, end_date)
        total_duration = totals["minutes"]
        avg_productivity = totals["avgScore"]
        deep_work = totals["deepWorkMinutes"]
        activity_count = totals["count"]
        
        # 图表数据
        category_distribution = self.stats.get_category_distribution(start_date, end_date)
        
        hourly_efficiency = self.stats.get_hourly_efficiency(end_date, start_date)
        
        # 周趋势
        weekly_trend = self.stats.get_weekly_trend(end_date, start_date)
        
        # 应用排行
        top_applications = self.stats.get_top_applications(start_date, end_date, limit=5)
        
        # 活动列表
        activities = self.stats.get_activities(start_date, end_date)
        
        # 提取所有分类
        categories = list(set(a['category'] for a in activities))
        
        # 日期范围文本
        if start_date == end_date:
            date_range = f"{start_date.year:04d}年{start_date.month:02d}月{start_date.day:02d}日"
        else:
            date_range = f"{start_date.isoformat()} 至 {end_date.isoformat()}"
        
        return DashboardData(
            title=f"Dayflow 生产力报告 - {date_range}",
            date_range=date_range,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_duration_minutes=total_duration,
            total_duration_formatted=format_duration(total_duration),
            avg_productivity_score=avg_productivity,
            deep_work_minutes=deep_work,
            deep_work_formatted=format_duration(deep_work),
            activity_count=activity_count,
            category_distribution=category_distribution,
            hourly_efficiency=hourly_efficiency,
            weekly_trend=weekly_trend,
            top_applications=top_applications,
            activities=activities,
            categories=categories,
            category_colors=CATEGORY_COLORS,
        )
    
    def _render_template(self, data: DashboardData) -> str:
        """渲染 HTML 模板"""
        template = self.env.get_template("dashboard.html")
        return template.render(data=data)
