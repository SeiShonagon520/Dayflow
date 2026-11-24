"""Read and merge Dayflow JSON backups, including the pre-Tauri format."""

import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

import config
from bridge.settings import DEFAULTS, SECRET_KEYS, write_settings_to_connection


class BackupCard(BaseModel):
    category: str
    title: str
    summary: str | None = ""
    start_time: datetime
    end_time: datetime
    app_sites_json: str | None = "[]"
    distractions_json: str | None = "[]"
    productivity_score: float = 0

    @field_validator("app_sites_json", "distractions_json")
    @classmethod
    def json_list(cls, value):
        if not isinstance(json.loads(value or "[]"), list):
            raise ValueError("活动记录格式无效")
        return value or "[]"


class Backup(BaseModel):
    cards: list[BackupCard]
    daily_reports: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, str] = Field(default_factory=dict)


RESTORABLE_SETTINGS = {
    "daily_goal", "record_output_idx", "idle_pause_enabled",
    "idle_pause_timeout_min", "chunks_max_size_gb",
}


def export_backup(storage):
    with storage._get_connection() as conn:
        return {
            "version": config.VERSION,
            "exported_at": datetime.now().isoformat(),
            "cards": [dict(row) for row in conn.execute(
                "SELECT id,category,title,summary,start_time,end_time,app_sites_json,"
                "distractions_json,productivity_score FROM timeline_cards ORDER BY start_time DESC"
            )],
            "settings": {
                key: value for key, value in conn.execute("SELECT key,value FROM settings")
                if key in DEFAULTS and key not in SECRET_KEYS
            },
            "daily_reports": dict(conn.execute("SELECT report_date,content FROM daily_reports")),
        }


def import_backup(storage, backup, settings=None):
    with storage._get_connection() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        imported = 0
        for card in backup.cards:
            start, end = card.start_time.isoformat(), card.end_time.isoformat()
            if card.end_time <= card.start_time:
                raise ValueError("活动结束时间必须晚于开始时间")
            cursor = conn.execute(
                "INSERT INTO timeline_cards(category,title,summary,start_time,end_time,"
                "app_sites_json,distractions_json,productivity_score) "
                "SELECT ?, ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS ("
                "SELECT 1 FROM timeline_cards WHERE datetime(start_time)=datetime(?) "
                "AND datetime(end_time)=datetime(?))",
                (card.category, card.title, card.summary, start, end, card.app_sites_json,
                 card.distractions_json, card.productivity_score, start, end),
            )
            imported += cursor.rowcount
        for day, content in backup.daily_reports.items():
            if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
                raise ValueError("日报日期格式无效")
            conn.execute(
                "INSERT OR IGNORE INTO daily_reports(report_date,content) VALUES(?, ?)", (day, content)
            )
        if settings:
            write_settings_to_connection(conn, settings)
    return {"imported": imported, "skipped": len(backup.cards) - imported}
