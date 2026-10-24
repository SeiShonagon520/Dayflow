"""
Dayflow 统计聚合服务

把原先埋在 ui/stats_view.py 里的统计逻辑抽出来 —— 那段代码和 Qt 图表
组件耦合在一起，没法被别的界面复用。现在它是纯函数式的聚合，
输入日期范围，输出前端直接可用的结构。

不含任何 Qt / Web 依赖，测试可以单独跑。
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from core.types import ActivityCard
from database.storage import StorageManager

# 应用名归一化：把 "Google Chrome" / "chrome.exe" 之类收敛成同一个键，
# 否则排行榜会出现八个 Chrome。
_NOISE_SUFFIX = re.compile(r"(\.exe|\.lnk)$", re.IGNORECASE)


def normalize_app_name(name: str) -> str:
    if not name:
        return "未命名"
    n = _NOISE_SUFFIX.sub("", name).strip()
    return n or name


def _app_minutes(card: ActivityCard) -> Dict[str, float]:
    """
    把一张卡片的应用时长拆成各应用的分钟数。

    app_sites 里的 duration_seconds 是模型给的估计值，经常和卡片总时长
    对不上（全是 0、或加起来是总时长的三倍）。这里做归一化，让应用
    榜单的总量和卡片总时长自洽 —— 否则图表之间会互相矛盾。
    """
    if not card.app_sites:
        return {}

    total_seconds = max(card.duration_minutes, 0) * 60
    raw = [max(a.duration_seconds or 0, 0) for a in card.app_sites]
    s = sum(raw)

    if total_seconds <= 0:
        norm = raw
    elif s <= 0:
        # 全是 0：平均分配，别让这些应用从榜单上消失
        per = total_seconds / len(card.app_sites)
        norm = [per] * len(card.app_sites)
    else:
        ratio = total_seconds / s
        norm = [v * ratio for v in raw]

    out: Dict[str, float] = {}
    for site, seconds in zip(card.app_sites, norm):
        if seconds <= 0:
            continue
        key = normalize_app_name(site.name)
        out[key] = out.get(key, 0) + seconds / 60
    return out


def _day_summary(cards: List[ActivityCard]) -> dict:
    """一天的单点汇总"""
    minutes = sum(c.duration_minutes for c in cards)
    scored = [c.productivity_score for c in cards if c.productivity_score > 0]
    categories: Dict[str, float] = defaultdict(float)
    for c in cards:
        categories[c.category or "其他"] += c.duration_minutes
    return {
        "minutes": minutes,
        "count": len(cards),
        "avgScore": (sum(scored) / len(scored)) if scored else 0.0,
        "deepWork": sum(1 for c in cards if c.duration_minutes >= 60),
        "categories": dict(categories),
    }


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

    cur_cards: Dict[str, List[ActivityCard]] = {}
    prev_cards: Dict[str, List[ActivityCard]] = {}
    for d in cur_dates:
        cur_cards[d.strftime("%Y-%m-%d")] = storage.get_cards_for_date(d)
    for d in prev_dates:
        prev_cards[d.strftime("%Y-%m-%d")] = storage.get_cards_for_date(d)

    cur = _day_summary([c for v in cur_cards.values() for c in v])
    prev = _day_summary([c for v in prev_cards.values() for c in v])
    today_summary = _day_summary(cur_cards[today.strftime("%Y-%m-%d")])

    # 趋势 + 每日分类
    trend = [{"date": k, "score": round(_day_summary(v)["avgScore"], 1),
              "hours": round(_day_summary(v)["minutes"] / 60, 2)}
             for k, v in cur_cards.items()]

    daily = [{"date": k,
              "categories": {c: round(m, 1)
                             for c, m in _day_summary(v)["categories"].items()}}
             for k, v in cur_cards.items()]

    # 贡献日历：往前 17 周，和 GitHub 那种一致
    end = today + timedelta(days=6 - today.weekday())
    start = end - timedelta(days=6 * 17 + 6)
    calendar = []
    for i in range(18 * 7):
        d = start + timedelta(days=i)
        s = _day_summary(storage.get_cards_for_date(d))
        calendar.append({
            "date": d.strftime("%Y-%m-%d"),
            "hours": round(s["minutes"] / 60, 2),
            "score": round(s["avgScore"], 0),
            "count": s["count"],
        })

    # 小时热力图：一天里 24 个时段各有多少活动
    hourly: List[List[dict]] = [[] for _ in range(24)]
    for cards in cur_cards.values():
        for c in cards:
            if c.start_time:
                hourly[c.start_time.hour].append(
                    {"score": round(c.productivity_score, 0),
                     "minutes": round(c.duration_minutes, 1)})

    # 应用榜单
    usage: Dict[str, float] = defaultdict(float)
    for cards in cur_cards.values():
        for c in cards:
            for name, mins in _app_minutes(c).items():
                usage[name] += mins
    app_ranking = [{"name": k, "minutes": round(v, 1)}
                   for k, v in sorted(usage.items(), key=lambda x: -x[1])]

    def delta(a: float, b: float) -> float:
        return round((a - b) / b * 100, 1) if b else 0.0

    return {
        "days": days,
        "rangeStart": cur_dates[0].strftime("%Y-%m-%d"),
        "rangeEnd": today.strftime("%Y-%m-%d"),
        "metrics": {
            "totalHours": round(cur["minutes"] / 60, 1),
            "avgScore": round(cur["avgScore"], 0),
            "deepWork": cur["deepWork"],
            "activityCount": cur["count"],
            "todayHours": round(today_summary["minutes"] / 60, 1),
            "todayScore": round(today_summary["avgScore"], 0),
        },
        "changes": {
            "totalHours": delta(cur["minutes"] / 60, prev["minutes"] / 60),
            "avgScore": delta(cur["avgScore"], prev["avgScore"]),
            "deepWork": delta(cur["deepWork"], prev["deepWork"]),
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
