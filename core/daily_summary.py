"""Build an auditable daily summary directly from the shared activity ledger."""

from dataclasses import dataclass
from hashlib import sha256
import json

from core.activity_time import application_totals, ledger_days, summarize_activities


@dataclass(frozen=True)
class DailySummary:
    markdown: str
    source_key: str
    evidence: list[dict]


def _text(value):
    return " ".join(str(value or "").split())[:160]


def daily_summary(storage, day):
    cards = ledger_days(storage, day, day)[day]
    if not cards:
        return None

    # Stable canonical data makes duplicate AI requests and stale reports distinguishable.
    snapshot = [card.to_dict() for card in cards]
    key = sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    summary = summarize_activities(cards)
    categories = sorted(summary["categories"].items(), key=lambda item: (-item[1], item[0]))
    ranking = application_totals(cards)[:3]
    longest = sorted(cards, key=lambda card: -card.duration_minutes)[:5]
    evidence = [
        {"id": card.id, "title": _text(card.title), "category": _text(card.category),
         "start": card.start_time.strftime("%H:%M"),
         "end": "24:00" if card.end_time.date() != day else card.end_time.strftime("%H:%M"),
         "minutes": round(card.duration_minutes, 1)}
        for card in longest if card.id is not None
    ]
    lines = [
        "## 本机总结", "",
        f"已记录 **{summary['minutes']:.1f} 分钟**，共 **{summary['count']} 项活动**。",
    ]
    if summary["avgScore"]:
        lines.append(f"含模型评分的活动按时长加权为 **{summary['avgScore']:g} 分**。")
    if evidence:
        item = evidence[0]
        lines.append(f"最长的一段记录是 **{item['minutes']:.1f} 分钟**。[活动 #{item['id']}]")
    lines.extend(["", "### 时间分配", ""])
    lines.extend(f"- {_text(category)}：{minutes:.1f} 分钟" for category, minutes in categories)
    if ranking:
        lines.extend(["", "### 常用应用", ""])
        lines.extend(f"- {_text(app)}：{minutes:.1f} 分钟" for app, minutes in ranking)
    return DailySummary("\n".join(lines), key, evidence)


def evidence_markdown(evidence):
    if not evidence:
        return ""
    rows = [
        f"- {item['start']}–{item['end']} {_text(item['title'])}（{item['minutes']:.1f} 分钟）[活动 #{item['id']}]"
        for item in evidence
    ]
    return "\n\n### 相关活动\n\n" + "\n".join(rows)
