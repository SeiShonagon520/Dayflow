"""
Dayflow 统计聚合服务

把原先埋在 ui/stats_view.py 里的统计逻辑抽出来 —— 那段代码和 Qt 图表
组件耦合在一起，没法被别的界面复用。现在它是纯函数式的聚合，
输入日期范围，输出前端直接可用的结构。

不含任何 Qt / Web 依赖，测试可以单独跑。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from core.activity_time import (
    application_totals,
    ledger_days,
    split_hours,
    summarize_activities,
)
from database.storage import StorageManager


def collect_stats(storage: StorageManager, days: int = 7,
                  today: datetime | None = None) -> dict:
    """
    汇总最近 N 天的全部统计数据。

    Args:
        days: 统计窗口天数（7=本周，30=近 30 天）
    Returns:
        前端直接可用的 dict，包含指标卡、分类分布、趋势、
        热力图、贡献日历、应用榜单，以及上一周期的对比数据。
    """
    today = today or datetime.now()

    # 当前窗口 + 等长的上一窗口，用于环比
    cur_dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    prev_dates = [today - timedelta(days=days + i) for i in range(days - 1, -1, -1)]

    # The heat map and both comparison windows share one SQLite snapshot.
    end = today + timedelta(days=6 - today.weekday())
    start = end - timedelta(days=18 * 7 - 1)
    ledger = ledger_days(storage, min(start.date(), prev_dates[0].date()), end.date())
    cur_cards = {d.date().isoformat(): ledger[d.date()] for d in cur_dates}
    prev_cards = {d.date().isoformat(): ledger[d.date()] for d in prev_dates}

    cur = summarize_activities([c for v in cur_cards.values() for c in v])
    prev = summarize_activities([c for v in prev_cards.values() for c in v])
    today_summary = summarize_activities(cur_cards[today.strftime("%Y-%m-%d")])

    # 趋势 + 每日分类
    trend = [{"date": k, "score": round(summarize_activities(v)["avgScore"], 1),
              "hours": round(summarize_activities(v)["minutes"] / 60, 2)}
             for k, v in cur_cards.items()]

    daily = [{"date": k,
              "categories": {c: round(m, 1)
                             for c, m in summarize_activities(v)["categories"].items()}}
             for k, v in cur_cards.items()]

    # 贡献日历：往前 18 周，和 GitHub 那种一致
    calendar = []
    for i in range(18 * 7):
        d = start + timedelta(days=i)
        s = summarize_activities(ledger[d.date()])
        calendar.append({
            "date": d.strftime("%Y-%m-%d"),
            "hours": round(s["minutes"] / 60, 2),
            "score": s["avgScore"],
            "count": s["count"],
        })

    hourly: List[List[dict]] = [[] for _ in range(24)]
    for cards in cur_cards.values():
        for card in cards:
            for hour, minutes in split_hours(card):
                hourly[hour].append({"score": card.productivity_score, "minutes": minutes})

    app_ranking = [
        {"name": name, "minutes": round(minutes, 1)}
        for name, minutes in application_totals([card for cards in cur_cards.values() for card in cards])
    ]

    def delta(a: float, b: float) -> float:
        return round((a - b) / b * 100, 1) if b else 0.0

    return {
        "days": days,
        "rangeStart": cur_dates[0].strftime("%Y-%m-%d"),
        "rangeEnd": today.strftime("%Y-%m-%d"),
        "metrics": {
            "totalHours": round(cur["minutes"] / 60, 1),
            "totalMinutes": cur["minutes"],
            "avgScore": cur["avgScore"],
            "deepWork": cur["deepWork"],
            "deepWorkMinutes": round(cur["deepWorkMinutes"], 1),
            "activityCount": cur["count"],
            "todayHours": round(today_summary["minutes"] / 60, 1),
            "todayMinutes": today_summary["minutes"],
            "todayScore": today_summary["avgScore"],
        },
        "changes": {
            "totalHours": delta(cur["minutes"] / 60, prev["minutes"] / 60),
            "avgScore": delta(cur["avgScore"], prev["avgScore"]),
            "deepWork": delta(cur["deepWorkMinutes"], prev["deepWorkMinutes"]),
            "activityCount": delta(cur["count"], prev["count"]),
        },
        "categories": [{"name": k, "minutes": round(v, 1)}
                       for k, v in sorted(cur["categories"].items(),
                                          key=lambda x: -x[1])],
        "trend": trend,
        "daily": daily,
        "hourly": hourly,
        "calendar": calendar,
        "appRanking": app_ranking,
    }
