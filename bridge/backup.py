"""Read and merge Dayflow JSON backups, including the pre-Tauri format."""

from collections import defaultdict
from datetime import datetime
import json
import re
from typing import Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field, field_validator

import config
from bridge.settings import DEFAULTS, DEVICE_OPT_IN_KEYS, SECRET_KEYS, write_settings_to_connection
from core.activity_time import local_time

_VALID_SOURCES = {"visual", "local", "local_refined", "manual"}
_EVIDENCE_REF_RE = re.compile(r"\[活动 #(\d+)\]")


class BackupSegment(BaseModel):
    start_time: datetime
    end_time: datetime
    app_name: str
    is_distraction: bool = False


class BackupCard(BaseModel):
    id: Optional[int] = None
    category: str
    title: str
    summary: str | None = ""
    start_time: datetime
    end_time: datetime
    app_sites_json: str | None = "[]"
    distractions_json: str | None = "[]"
    productivity_score: float = 0.0
    source: str = "visual"
    user_edited: bool = False
    segments: List[BackupSegment] = Field(default_factory=list)

    @field_validator("app_sites_json", "distractions_json")
    @classmethod
    def json_list(cls, value):
        if not isinstance(json.loads(value or "[]"), list):
            raise ValueError("活动记录格式无效")
        return value or "[]"

    @field_validator("source")
    @classmethod
    def valid_source(cls, value):
        return value if value in _VALID_SOURCES else "manual"


class Backup(BaseModel):
    cards: list[BackupCard]
    daily_reports: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, str] = Field(default_factory=dict)


# 设备级隐私与外发授权（local_context_mode, local_ai_refinement）双向排除
RESTORABLE_SETTINGS = {
    "daily_goal",
    "record_output_idx",
    "idle_pause_enabled",
    "idle_pause_timeout_min",
    "chunks_max_size_gb",
}
_EXCLUDED_EXPORT_SETTINGS = SECRET_KEYS | DEVICE_OPT_IN_KEYS


def _canonical_json(raw: str | None) -> str:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        parsed = []
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True)


def _canonical_segments(segments: List[Tuple[datetime, datetime, str, bool]]) -> Tuple[Tuple[str, str, str, bool], ...]:
    ordered = sorted(
        (
            local_time(s).isoformat(),
            local_time(e).isoformat(),
            str(app),
            bool(dist),
        )
        for s, e, app, dist in segments
    )
    return tuple(ordered)


def _card_signature(
    *,
    start_time: datetime,
    end_time: datetime,
    category: str,
    title: str,
    summary: str | None,
    app_sites_json: str | None,
    distractions_json: str | None,
    productivity_score: float,
    segments: List[Tuple[datetime, datetime, str, bool]],
) -> tuple:
    """保留微秒精度与完整持久化内容（含分段和无损评分）的精确去重键。"""
    return (
        local_time(start_time).isoformat(),
        local_time(end_time).isoformat(),
        str(category or ""),
        str(title or ""),
        str(summary or ""),
        _canonical_json(app_sites_json),
        _canonical_json(distractions_json),
        float(productivity_score or 0.0),
        _canonical_segments(segments),
    )


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value.replace(" ", "T"))


def _remap_report_references(content: str, id_map: Dict[int, Set[int]]) -> str:
    """仅当旧 ID 唯一映射到本地某张卡片时重写 [活动 #OLD_ID]；多义或缺失统一替换为 [活动记录]。"""
    def _replace(match: re.Match) -> str:
        old_id = int(match.group(1))
        targets = id_map.get(old_id)
        if targets and len(targets) == 1:
            return f"[活动 #{next(iter(targets))}]"
        return "[活动记录]"

    return _EVIDENCE_REF_RE.sub(_replace, content)


def export_backup(storage):
    with storage._get_connection() as conn:
        rows = conn.execute(
            "SELECT id,category,title,summary,start_time,end_time,app_sites_json,"
            "distractions_json,productivity_score,source,user_edited "
            "FROM timeline_cards ORDER BY start_time DESC"
        ).fetchall()
        seg_map: Dict[int, List[dict]] = defaultdict(list)
        if rows:
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in ids)
            for s in conn.execute(
                f"SELECT card_id,start_time,end_time,app_name,is_distraction "
                f"FROM card_segments WHERE card_id IN ({placeholders}) ORDER BY start_time ASC, id ASC",
                tuple(ids),
            ):
                seg_map[s["card_id"]].append({
                    "start_time": s["start_time"],
                    "end_time": s["end_time"],
                    "app_name": s["app_name"],
                    "is_distraction": bool(s["is_distraction"]),
                })
        cards = []
        for row in rows:
            item = dict(row)
            item["user_edited"] = bool(item.get("user_edited", 0))
            item["segments"] = seg_map.get(row["id"], [])
            cards.append(item)

        return {
            "version": config.VERSION,
            "exported_at": datetime.now().isoformat(),
            "cards": cards,
            "settings": {
                key: value
                for key, value in conn.execute("SELECT key,value FROM settings")
                if key in DEFAULTS and key not in _EXCLUDED_EXPORT_SETTINGS
            },
            "daily_reports": dict(conn.execute("SELECT report_date,content FROM daily_reports")),
        }


def import_backup(storage, backup: Backup, settings=None):
    with storage._get_connection() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")

        # 读取现有全部卡片及其分段，构建无损全内容索引
        existing_rows = conn.execute(
            "SELECT id,category,title,summary,start_time,end_time,app_sites_json,"
            "distractions_json,productivity_score FROM timeline_cards"
        ).fetchall()
        existing_segs: Dict[int, List[Tuple[datetime, datetime, str, bool]]] = defaultdict(list)
        for s in conn.execute(
            "SELECT card_id,start_time,end_time,app_name,is_distraction FROM card_segments"
        ):
            existing_segs[s["card_id"]].append(
                (_parse_iso(s["start_time"]), _parse_iso(s["end_time"]), s["app_name"], bool(s["is_distraction"]))
            )

        sig_to_ids: Dict[tuple, List[int]] = defaultdict(list)
        for r in existing_rows:
            sig = _card_signature(
                start_time=_parse_iso(r["start_time"]),
                end_time=_parse_iso(r["end_time"]),
                category=r["category"],
                title=r["title"],
                summary=r["summary"],
                app_sites_json=r["app_sites_json"],
                distractions_json=r["distractions_json"],
                productivity_score=r["productivity_score"],
                segments=existing_segs.get(r["id"], []),
            )
            sig_to_ids[sig].append(int(r["id"]))

        imported = 0
        old_id_map: Dict[int, Set[int]] = defaultdict(set)

        for card in backup.cards:
            if local_time(card.end_time) <= local_time(card.start_time):
                raise ValueError("活动结束时间必须晚于开始时间")
            seg_tuples = [
                (local_time(seg.start_time), local_time(seg.end_time), seg.app_name, bool(seg.is_distraction))
                for seg in card.segments
                if local_time(seg.end_time) > local_time(seg.start_time)
            ]
            sig = _card_signature(
                start_time=card.start_time,
                end_time=card.end_time,
                category=card.category,
                title=card.title,
                summary=card.summary,
                app_sites_json=card.app_sites_json,
                distractions_json=card.distractions_json,
                productivity_score=card.productivity_score,
                segments=seg_tuples,
            )

            matched_ids = sig_to_ids.get(sig)
            if matched_ids:
                if card.id is not None:
                    old_id_map[int(card.id)].update(matched_ids)
                continue

            start_iso = local_time(card.start_time).isoformat()
            end_iso = local_time(card.end_time).isoformat()
            cursor = conn.execute(
                """
                INSERT INTO timeline_cards(
                    category,title,summary,start_time,end_time,
                    app_sites_json,distractions_json,productivity_score,
                    source,user_edited,is_finalized,session_token,refinement_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, 'skipped')
                """,
                (
                    card.category,
                    card.title,
                    card.summary,
                    start_iso,
                    end_iso,
                    card.app_sites_json,
                    card.distractions_json,
                    float(card.productivity_score),
                    card.source,
                    1 if card.user_edited else 0,
                ),
            )
            new_id = int(cursor.lastrowid)
            if seg_tuples:
                conn.executemany(
                    "INSERT INTO card_segments (card_id, start_time, end_time, app_name, is_distraction) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [(new_id, s.isoformat(), e.isoformat(), app, 1 if dist else 0) for s, e, app, dist in seg_tuples],
                )
            sig_to_ids[sig].append(new_id)
            if card.id is not None:
                old_id_map[int(card.id)].add(new_id)
            imported += 1

        for day, content in backup.daily_reports.items():
            if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
                raise ValueError("日报日期格式无效")
            remapped = _remap_report_references(content, old_id_map)
            conn.execute(
                "INSERT OR IGNORE INTO daily_reports(report_date,content) VALUES(?, ?)",
                (day, remapped),
            )

        if settings:
            safe_settings = {k: v for k, v in settings.items() if k not in _EXCLUDED_EXPORT_SETTINGS}
            if safe_settings:
                write_settings_to_connection(conn, safe_settings)

    return {"imported": imported, "skipped": len(backup.cards) - imported}
