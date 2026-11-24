"""
Dayflow - 仪表盘导出器
生成 HTML 格式的生产力报告
"""
import logging
import webbrowser
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict

from jinja2 import Environment, FileSystemLoader

import config
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
    total_duration_minutes: int
    total_duration_formatted: str
    avg_productivity_score: float
    deep_work_minutes: int
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
    
    # AI 洞察
    ai_insights: Optional[str]


def format_duration(minutes: int) -> str:
    """
    将分钟数格式化为可读字符串
    
    Args:
        minutes: 分钟数
        
    Returns:
        格式化字符串，如 "2h 30m" 或 "45m"
    """
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
        
        # 添加自定义过滤器
        self.env.filters['format_duration'] = format_duration
    
    def _get_template_dir(self) -> Path:
        """获取模板目录路径"""
        # 优先使用打包后的路径
        if hasattr(config, 'APP_DIR'):
            packed_path = config.APP_DIR / "templates"
            if packed_path.exists():
                return packed_path
        
        # 开发环境路径
        dev_path = Path(__file__).parent.parent / "templates"
        if dev_path.exists():
            return dev_path
        
        raise FileNotFoundError("模板目录不存在")
    
    def export(
        self, 
        start_date: date, 
        end_date: date,
        output_dir: Optional[Path] = None
    ) -> Path:
        """
        导出仪表盘 HTML 文件
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            output_dir: 输出目录，默认为 APP_DATA_DIR/reports
            
        Returns:
            生成的 HTML 文件路径
        """
        logger.info(f"开始导出仪表盘: {start_date} ~ {end_date}")
        
        # 确定输出目录
        if output_dir is None:
            output_dir = config.APP_DATA_DIR / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        html_content = self.render(start_date, end_date)
        
        # 生成文件名
        if start_date == end_date:
            filename = f"dayflow_report_{start_date}.html"
        else:
            filename = f"dayflow_report_{start_date}_{end_date}.html"
        
        output_path = output_dir / filename
        
        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"仪表盘已导出: {output_path}")
        return output_path

    def render(self, start_date: date, end_date: date) -> str:
        return self._render_template(self._collect_data(start_date, end_date))
    
    def export_and_open(self, start_date: date, end_date: date) -> Path:
        """
        导出并在浏览器中打开
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            生成的 HTML 文件路径
        """
        path = self.export(start_date, end_date)
        
        try:
            webbrowser.open(path.as_uri())
            logger.info("已在浏览器中打开仪表盘")
        except Exception as e:
            logger.warning(f"无法自动打开浏览器: {e}")
            logger.info(f"请手动打开文件: {path}")
        
        return path

    def _collect_data(self, start_date: date, end_date: date) -> DashboardData:
        """收集指定日期范围的数据"""
        # 基础统计
        total_duration = self.stats.get_total_duration(start_date, end_date)
        avg_productivity = self.stats.get_avg_productivity(start_date, end_date)
        deep_work = self.stats.get_deep_work_duration(start_date, end_date)
        activity_count = self.stats.get_activity_count(start_date, end_date)
        
        # 图表数据
        category_distribution = self.stats.get_category_distribution(start_date, end_date)
        
        # 每小时效率 - 如果是单日则使用该日，否则使用最后一天
        hourly_efficiency = self.stats.get_hourly_efficiency(end_date)
        
        # 周趋势
        weekly_trend = self.stats.get_weekly_trend(end_date)
        
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
            ai_insights=None  # AI 洞察暂不实现
        )
    
    def _render_template(self, data: DashboardData) -> str:
        """渲染 HTML 模板"""
        template = self.env.get_template("dashboard.html")
        return template.render(data=data)
