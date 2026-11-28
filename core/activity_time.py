"""Local-time interval rules shared by activity consumers."""

from dataclasses import replace
from collections import defaultdict
from datetime import datetime, time, timedelta
import re

from core.types import ActivitySegment, AppSite


def local_time(value):
    # The database records Dayflow wall-clock times, including legacy ISO rows.
    return value.replace(tzinfo=None)


def day_bounds(day):
    end = datetime.combine(day + timedelta(days=1), time.min) if day < datetime.max.date() else datetime.max
    return datetime.combine(day, time.min), end


def _clip_segments(segments, start, end):
    clipped = []
    for seg in segments:
        seg_start = max(start, local_time(seg.start_time))
        seg_end = min(end, local_time(seg.end_time))
        if seg_end > seg_start:
            clipped.append(ActivitySegment(
                start_time=seg_start,
                end_time=seg_end,
                app_name=seg.app_name,
                is_distraction=bool(seg.is_distraction),
            ))
    return clipped


def _app_sites_from_segments(segments):
    totals = defaultdict(float)
    order = []
    for seg in segments:
        dur = (seg.end_time - seg.start_time).total_seconds()
        if dur <= 0:
            continue
        if seg.app_name not in totals:
            order.append(seg.app_name)
        totals[seg.app_name] += dur
    return [AppSite(name=name, duration_seconds=totals[name]) for name in order]


def clip_card(card, start, end):
    if card.start_time is None or card.end_time is None:
        return None
    original_start = local_time(card.start_time)
    original_end = local_time(card.end_time)
    clipped_start = max(start, original_start)
    clipped_end = min(end, original_end)
    if clipped_end <= clipped_start:
        return None

    has_segments = bool(getattr(card, "segments", None))
    clipped_segments = _clip_segments(card.segments, clipped_start, clipped_end) if has_segments else []
    share = (clipped_end - clipped_start) / (original_end - original_start)

    if share == 1 and not has_segments:
        return replace(card, start_time=clipped_start, end_time=clipped_end)

    offset = (clipped_start - original_start).total_seconds()
    duration = (clipped_end - clipped_start).total_seconds()
    distractions = []
    for item in card.distractions:
        item_start = max(offset, item.timestamp)
        item_end = min(offset + duration, item.timestamp + item.duration_seconds)
        if item_end > item_start or (item.duration_seconds == 0 and offset <= item.timestamp < offset + duration):
            distractions.append(replace(item, timestamp=item_start - offset, duration_seconds=item_end - item_start))

    if has_segments:
        app_sites = _app_sites_from_segments(clipped_segments) if clipped_segments else []
    else:
        app_sites = [replace(app, duration_seconds=app.duration_seconds * share) for app in card.app_sites]

    return replace(
        card,
        start_time=clipped_start,
        end_time=clipped_end,
        app_sites=app_sites,
        distractions=distractions,
        segments=clipped_segments,
    )


def activity_segments(cards, start, end):
    """Yield original card and its share of the range, with overlaps counted once."""
    ordered = sorted(
        (card for card in cards if card.start_time and card.end_time),
        key=lambda card: (local_time(card.start_time), card.id or 0),
    )
    cursor = start
    for card in ordered:
        segment = clip_card(card, cursor, end)
        if segment:
            yield card, segment
            cursor = segment.end_time


def split_hours(card):
    cursor = card.start_time
    while cursor < card.end_time:
        boundary = (
            cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            if cursor.hour < 23 or cursor.date() < datetime.max.date()
            else datetime.max
        )
        end = min(boundary, card.end_time)
        yield cursor.hour, (end - cursor).total_seconds() / 60
        cursor = end


def average_productivity(cards):
    scored = [card for card in cards if card.productivity_score > 0]
    minutes = sum(card.duration_minutes for card in scored)
    return round(sum(card.productivity_score * card.duration_minutes for card in scored) / minutes, 1) if minutes else 0.0


def ledger_days(storage, first, last):
    """Read a range once, then attribute its active minutes to local dates."""
    start, _ = day_bounds(first)
    _, end = day_bounds(last)
    by_day = {first + timedelta(days=i): [] for i in range((last - first).days + 1)}
    cards = storage.get_cards_in_range(start, end)
    for _, segment in activity_segments(cards, start, end):
        cursor = segment.start_time
        while cursor < segment.end_time:
            _, midnight = day_bounds(cursor.date())
            clipped_end = min(midnight, segment.end_time)
            by_day[cursor.date()].append(clip_card(segment, cursor, clipped_end))
            cursor = clipped_end
    return by_day


def focus_minutes(card) -> float:
    """Return unrounded focus minutes, excluding absorbed distraction segments."""
    segs = getattr(card, "segments", None)
    if segs:
        total = 0.0
        for seg in segs:
            if not seg.is_distraction:
                dur = (local_time(seg.end_time) - local_time(seg.start_time)).total_seconds()
                if dur > 0:
                    total += dur / 60.0
        return total
    return card.duration_minutes


def summarize_activities(cards):
    categories = defaultdict(float)
    for card in cards:
        categories[card.category or "其他"] += card.duration_minutes
    # Deep work uses unrounded exact focus minutes (distractions excluded).
    durations = [fm for card in cards if (fm := focus_minutes(card)) >= 60.0]
    card_ids = {card.id for card in cards if card.id is not None}
    return {
        "minutes": sum(categories.values()),
        "count": len(card_ids) + sum(card.id is None for card in cards),
        "avgScore": average_productivity(cards),
        "deepWork": len(durations),
        "deepWorkMinutes": sum(durations),
        "categories": dict(categories),
    }


def normalize_app_name(name):
    if not name:
        return "未命名"
    return re.sub(r"(\.exe|\.lnk)$", "", name, flags=re.IGNORECASE).strip() or name


def app_minutes(card):
    segs = getattr(card, "segments", None)
    if segs:
        out = defaultdict(float)
        for seg in segs:
            dur = (local_time(seg.end_time) - local_time(seg.start_time)).total_seconds()
            if dur > 0:
                out[normalize_app_name(seg.app_name)] += dur / 60.0
        if out:
            return dict(out)
    if not card.app_sites:
        return {}
    durations = [max(app.duration_seconds or 0, 0) for app in card.app_sites]
    total = sum(durations)
    minutes = card.duration_minutes
    out = defaultdict(float)
    for app, duration in zip(card.app_sites, durations):
        share = duration / total if total else 1 / len(durations)
        if share and minutes:
            out[normalize_app_name(app.name)] += share * minutes
    return dict(out)


def application_totals(cards):
    out = defaultdict(float)
    for card in cards:
        for app, minutes in app_minutes(card).items():
            out[app] += minutes
    return sorted(out.items(), key=lambda item: (-item[1], item[0]))
