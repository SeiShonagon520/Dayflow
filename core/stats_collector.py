"""
Dayflow - 统计数据收集器
用于 Web Dashboard 导出功能
"""
from datetime import date, timedelta

from core.activity_time import application_totals, ledger_days, split_hours, summarize_activities
from database.storage import StorageManager

# 分类颜色映射
CATEGORY_COLORS = {
    "工作": "#7c3aed",    # 紫色
    "学习": "#3b82f6",    # 蓝色
    "编程": "#10b981",    # 绿色
    "会议": "#f59e0b",    # 橙色
    "娱乐": "#ef4444",    # 红色
    "社交": "#ec4899",    # 粉色
    "休息": "#6b7280",    # 灰色
    "其他": "#8b5cf6",    # 浅紫色
}


class StatsCollector:
    """Compute dashboard metrics from the same clipped, non-overlapping ledger."""

    def __init__(self, storage: StorageManager):
        self.storage = storage
        self._range = None
        self._days = {}

    def load(self, start_date: date, end_date: date):
        self._days = ledger_days(self.storage, start_date, end_date)
        self._range = (start_date, end_date)

    def _get_cards_in_range(self, start_date: date, end_date: date):
        if self._range != (start_date, end_date):
            self.load(start_date, end_date)
        return [card for cards in self._days.values() for card in cards]

    def summary(self, start_date: date, end_date: date):
        return summarize_activities(self._get_cards_in_range(start_date, end_date))

    def get_category_distribution(self, start_date: date, end_date: date):
        categories = self.summary(start_date, end_date)["categories"]
        return [
            {"name": category, "value": round(minutes, 1), "color": CATEGORY_COLORS.get(category, CATEGORY_COLORS["其他"])}
            for category, minutes in sorted(categories.items(), key=lambda item: -item[1])
        ]

    def get_hourly_efficiency(self, end_date: date, start_date: date | None = None):
        hours = [{"hour": h, "score": 0.0, "duration": 0.0} for h in range(24)]
        scored_minutes = [0.0] * 24
        for card in self._get_cards_in_range(start_date or end_date, end_date):
            for hour, minutes in split_hours(card):
                hours[hour]["duration"] += minutes
                if card.productivity_score > 0:
                    hours[hour]["score"] += minutes * card.productivity_score
                    scored_minutes[hour] += minutes
        for row, minutes in zip(hours, scored_minutes):
            row["score"] = round(row["score"] / minutes, 1) if minutes else 0.0
            row["duration"] = round(row["duration"], 1)
        return hours

    def get_weekly_trend(self, end_date: date, start_date: date | None = None):
        self._get_cards_in_range(start_date or end_date - timedelta(days=6), end_date)
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        return [
            {"date": day.isoformat(), "weekday": weekdays[day.weekday()],
             "duration": round(summary["minutes"], 1), "score": summary["avgScore"]}
            for day, cards in self._days.items()
            for summary in [summarize_activities(cards)]
        ]

    def get_top_applications(self, start_date: date, end_date: date, limit: int = 5):
        ranking = application_totals(self._get_cards_in_range(start_date, end_date))
        total = sum(minutes for _, minutes in ranking)
        return [
            {"name": name, "duration": round(minutes, 1),
             "percentage": round(minutes / total * 100, 1) if total else 0}
            for name, minutes in ranking[:limit]
        ]

    def get_activities(self, start_date: date, end_date: date):
        return [
            {
                "start": card.start_time.strftime("%H:%M"),
                "end": "24:00" if card.end_time.date() != card.start_time.date() else card.end_time.strftime("%H:%M"),
                "date": card.start_time.date().isoformat(),
                "category": card.category or "其他",
                "category_color": CATEGORY_COLORS.get(card.category, CATEGORY_COLORS["其他"]),
                "title": card.title, "summary": card.summary, "score": card.productivity_score,
                "duration": round(card.duration_minutes, 1),
                "main_app": card.app_sites[0].name if card.app_sites else "",
                "apps": [app.name for app in card.app_sites],
            }
            for card in self._get_cards_in_range(start_date, end_date)
        ]
