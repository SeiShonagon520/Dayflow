"""
Dayflow Windows - 数据库管理
"""
import sqlite3
import json
import logging
import time
import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
from contextlib import contextmanager

import config
from core.activity_time import day_bounds, local_time
from core.types import (
    VideoChunk, ChunkStatus,
    AnalysisBatch, BatchStatus,
    ActivityCard, ActivitySegment, AppSite, Distraction
)
from database.connection_pool import ConnectionPool

logger = logging.getLogger(__name__)

_WATERMARK_KEY = "local_recorder_watermark"
_MAX_UNDO_SNAPSHOTS = 20


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except ValueError:
            return None


def _iso_local(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return local_time(value).isoformat()


class StorageManager:
    """SQLite 数据库管理器 - 使用连接池"""

    def __init__(self, db_path: Optional[Path] = None):
        """初始化数据库管理器"""
        self.db_path = db_path or config.DATABASE_PATH
        logger.info("数据库路径: %s", self.db_path)
        self._pool: Optional[ConnectionPool] = ConnectionPool(
            db_path=str(self.db_path),
            max_size=5,
            timeout=4.5,
            idle_timeout=300.0,
        )
        self._init_database()

    def _init_database(self):
        """初始化数据库结构"""
        if getattr(sys, "frozen", False):
            base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            schema_path = base_dir / "database" / "schema.sql"
            if not schema_path.exists():
                schema_path = Path(__file__).parent / "schema.sql"
        else:
            schema_path = Path(__file__).parent / "schema.sql"

        with self._get_connection() as conn:
            with open(schema_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())

            # 数据库迁移：为旧数据库添加新字段与依赖索引
            self._migrate_database(conn)

    def _migrate_database(self, conn):
        """Make existing databases and queues readable before any workers start."""
        conn.execute("BEGIN IMMEDIATE")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
        for name, declaration in (
            ("window_records_path", "TEXT"),
            ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
            ("retry_at", "REAL NOT NULL DEFAULT 0"),
            ("analysis_error", "TEXT"),
        ):
            if name not in columns:
                conn.execute(f"ALTER TABLE chunks ADD COLUMN {name} {declaration}")

        report_columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_reports)")}
        for name in ("source_key", "previous_content", "previous_source_key"):
            if name not in report_columns:
                conn.execute(f"ALTER TABLE daily_reports ADD COLUMN {name} TEXT")

        card_columns = {row[1] for row in conn.execute("PRAGMA table_info(timeline_cards)")}
        for name, declaration in (
            ("source", "TEXT NOT NULL DEFAULT 'visual'"),
            ("user_edited", "INTEGER NOT NULL DEFAULT 0"),
            ("session_key", "TEXT"),
            ("session_token", "TEXT"),
            ("is_finalized", "INTEGER NOT NULL DEFAULT 1"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("refinement_status", "TEXT NOT NULL DEFAULT 'none'"),
            ("refinement_lease_id", "TEXT"),
            ("refinement_lease_expires_at", "REAL NOT NULL DEFAULT 0"),
            ("refinement_attempts", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in card_columns:
                conn.execute(f"ALTER TABLE timeline_cards ADD COLUMN {name} {declaration}")

        # 依赖新列的索引统一放在迁移完成之后创建
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cards_source_finalized "
            "ON timeline_cards(source, is_finalized, end_time)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cards_refinement "
            "ON timeline_cards(refinement_status, refinement_lease_expires_at)"
        )

    @contextmanager
    def _get_connection(self, deadline: Optional[float] = None):
        """获取数据库连接上下文（支持贯穿取连接和 busy_timeout 的单调截止时间）"""
        if self._pool is None:
            raise RuntimeError("数据库连接池已关闭")
        with self._pool.get_connection(deadline=deadline) as conn:
            yield conn

    def close(self):
        """关闭数据库连接池"""
        if self._pool is not None:
            self._pool.close_all()
            self._pool = None
            logger.info("数据库连接池已关闭")

    # ==================== Watermark & Startup Recovery ====================

    def _advance_watermark_in_tx(self, conn: sqlite3.Connection, dt: Optional[datetime]) -> None:
        if dt is None:
            return
        candidate = local_time(dt)
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (_WATERMARK_KEY,)).fetchone()
        existing = _parse_dt(row["value"]) if row else None
        if existing is None or candidate > local_time(existing):
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                (_WATERMARK_KEY, candidate.isoformat()),
            )

    def get_local_watermark(self) -> Optional[datetime]:
        """规范化后独立取最大已提交水位，避免 T/空格 混排的字符串 MAX 错误及删卡丢水位。"""
        candidates: List[datetime] = []
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (_WATERMARK_KEY,)).fetchone()
            if row and row["value"]:
                dt = _parse_dt(row["value"])
                if dt is not None:
                    candidates.append(local_time(dt))
            for table in ("timeline_cards", "recorder_candidates"):
                for r in conn.execute(f"SELECT end_time FROM {table} WHERE end_time IS NOT NULL"):
                    dt = _parse_dt(r["end_time"])
                    if dt is not None:
                        candidates.append(local_time(dt))
        return max(candidates) if candidates else None

    def cleanup_expired_context_events(self, retention_days: int = 90) -> int:
        """滚动清理超过保留期的上下文明细（不动 card_segments）。"""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("DELETE FROM context_events WHERE end_time < ?", (cutoff,))
            return cur.rowcount

    def _settle_candidate_row_in_tx(self, conn: sqlite3.Connection, cand: sqlite3.Row) -> Optional[int]:
        """在事务内将已确认的候选分心记录提升为独立已封口卡片（幂等）。"""
        start_dt = _parse_dt(cand["start_time"])
        end_dt = _parse_dt(cand["end_time"])
        if not start_dt or not end_dt or local_time(end_dt) <= local_time(start_dt):
            return None
        start_dt = local_time(start_dt)
        end_dt = local_time(end_dt)
        dur = (end_dt - start_dt).total_seconds()
        friendly = cand["friendly_app"] or cand["app_name"] or "其他"
        category = cand["category"] or "其他"
        ctx = {}
        try:
            ctx = json.loads(cand["context_json"] or "{}")
        except json.JSONDecodeError:
            ctx = {}
        title = str(ctx.get("title") or friendly)
        summary = str(ctx.get("summary") or "")
        session_key = ctx.get("session_key")
        app_sites = [AppSite(name=friendly, duration_seconds=dur)]
        card = ActivityCard(
            category=category,
            title=title,
            summary=summary,
            start_time=start_dt,
            end_time=end_dt,
            app_sites=app_sites,
            distractions=[],
            productivity_score=0.0,
            source="local",
            user_edited=False,
            session_key=session_key,
            is_finalized=True,
            version=1,
        )
        new_id = self._insert_card(
            conn,
            card,
            batch_id=None,
            source="local",
            is_finalized=1,
            session_token=None,
            refinement_status="pending",
        )
        conn.execute(
            "INSERT INTO card_segments (card_id, start_time, end_time, app_name, is_distraction) "
            "VALUES (?, ?, ?, ?, 0)",
            (new_id, start_dt.isoformat(), end_dt.isoformat(), friendly),
        )
        self._advance_watermark_in_tx(conn, end_dt)
        return new_id

    def recover_interrupted_local_sessions(self) -> Dict[str, int]:
        """启动崩溃恢复：结算遗留候选并封口未完成本机卡片，保证每段秒数只归属一次。"""
        promoted = 0
        sealed = 0
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cand = conn.execute("SELECT * FROM recorder_candidates WHERE id = 1").fetchone()
            if cand is not None:
                if self._settle_candidate_row_in_tx(conn, cand) is not None:
                    promoted = 1
                conn.execute("DELETE FROM recorder_candidates WHERE id = 1")

            open_rows = conn.execute(
                "SELECT id, end_time FROM timeline_cards WHERE is_finalized = 0"
            ).fetchall()
            for r in open_rows:
                dt = _parse_dt(r["end_time"])
                if dt is not None:
                    self._advance_watermark_in_tx(conn, dt)
            sealed = conn.execute(
                "UPDATE timeline_cards SET is_finalized = 1, session_token = NULL, version = version + 1 "
                "WHERE is_finalized = 0"
            ).rowcount
        return {"promoted_candidates": promoted, "sealed_cards": sealed}

    # ==================== Chunks ====================

    def save_chunk(self, chunk: VideoChunk) -> int:
        """保存视频切片"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO chunks (file_path, start_time, end_time, duration_seconds, status, batch_id, window_records_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.file_path,
                    chunk.start_time.isoformat() if chunk.start_time else None,
                    chunk.end_time.isoformat() if chunk.end_time else None,
                    chunk.duration_seconds,
                    chunk.status.value,
                    chunk.batch_id,
                    chunk.window_records_path,
                ),
            )
            return cursor.lastrowid

    def get_pending_chunks(self, limit: int = 100) -> List[VideoChunk]:
        """获取待分析的切片"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM chunks
                WHERE status = ? AND retry_at <= ?
                ORDER BY start_time ASC
                LIMIT ?
                """,
                (ChunkStatus.PENDING.value, time.time(), limit),
            )
            return [self._row_to_chunk(row) for row in cursor.fetchall()]

    def analysis_queue_size(self):
        with self._get_connection() as conn:
            return dict(conn.execute(
                "SELECT status, COUNT(*) FROM chunks WHERE status <> 'completed' GROUP BY status"
            ))

    def recover_interrupted_analysis(self):
        """Run once under the worker lock before claiming any new work."""
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE chunks SET status='failed', analysis_error='legacy_partial' "
                "WHERE status IN ('processing', 'failed') AND analysis_error IS NULL "
                "AND EXISTS (SELECT 1 FROM timeline_cards WHERE batch_id=chunks.batch_id)"
            )
            recovered = conn.execute(
                "UPDATE chunks SET status='pending', retry_at=0, analysis_error=NULL, batch_id=NULL "
                "WHERE status='processing' OR (status='failed' AND analysis_error IS NULL)"
            ).rowcount
            conn.execute(
                "UPDATE analysis_batches SET status='failed', error_message='interrupted', "
                "completed_at=CURRENT_TIMESTAMP WHERE status IN ('pending','processing')"
            )
            return recovered

    def retry_analysis_after_settings_change(self):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE chunks SET status='pending', retry_count=0, retry_at=0, analysis_error=NULL "
                "WHERE status IN ('pending', 'failed') "
                "AND analysis_error IN ('authorization', 'provider', 'empty_observations', 'empty_cards')"
            )

    def claim_analysis_batch(self, batch):
        ids = batch.chunk_ids
        if not ids:
            return None
        placeholders = ",".join("?" for _ in ids)
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            available = conn.execute(
                f"SELECT COUNT(*) FROM chunks WHERE id IN ({placeholders}) AND status='pending' AND retry_at <= ?",
                (*ids, now),
            ).fetchone()[0]
            if available != len(ids):
                return None
            batch_id = self._insert_batch(conn, batch)
            conn.execute(
                f"UPDATE chunks SET status='processing', batch_id=? WHERE id IN ({placeholders})",
                (batch_id, *ids),
            )
            return batch_id

    def release_analysis_chunks(self, batch_id, ids, reason, *, retryable, finish_batch=False):
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for chunk_id in ids:
                row = conn.execute(
                    "SELECT retry_count FROM chunks WHERE id=? AND batch_id=? AND status='processing'",
                    (chunk_id, batch_id),
                ).fetchone()
                if row is None:
                    continue
                attempts = row[0] + 1
                retry = retryable and (reason == "network" or attempts < 5)
                retry_at = time.time() + 15 * 2 ** min(attempts - 1, 3) if retry else 0
                conn.execute(
                    "UPDATE chunks SET status=?, retry_count=?, retry_at=?, analysis_error=? WHERE id=?",
                    ("pending" if retry else "failed", attempts, retry_at, reason, chunk_id),
                )
            if finish_batch:
                conn.execute(
                    "UPDATE analysis_batches SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP "
                    "WHERE id=? AND status='processing'",
                    (reason, batch_id),
                )

    def commit_analysis_batch(self, batch_id, ids, observations, cards):
        if not ids or not cards:
            raise ValueError("分析结果为空")
        placeholders = ",".join("?" for _ in ids)
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            claimed = conn.execute(
                f"SELECT COUNT(*) FROM chunks WHERE batch_id=? AND status='processing' AND id IN ({placeholders})",
                (batch_id, *ids),
            ).fetchone()[0]
            if claimed != len(ids):
                raise RuntimeError("分析切片已被其他任务接管")
            for card in cards:
                # 仅可信视觉批处理路径写入 source='visual'
                self._insert_card(
                    conn,
                    card,
                    batch_id=batch_id,
                    source="visual",
                    is_finalized=1,
                    session_token=None,
                    refinement_status="none",
                )
            conn.execute(
                f"UPDATE chunks SET status='completed', retry_at=0, analysis_error=NULL "
                f"WHERE batch_id=? AND id IN ({placeholders})",
                (batch_id, *ids),
            )
            result = conn.execute(
                "UPDATE analysis_batches SET status='completed', observations_json=?, "
                "completed_at=CURRENT_TIMESTAMP WHERE id=? AND status='processing'",
                (json.dumps(observations, ensure_ascii=False), batch_id),
            )
            if result.rowcount != 1:
                raise RuntimeError("分析批次已失效")

    def update_chunk_status(self, chunk_id: int, status: ChunkStatus, batch_id: Optional[int] = None):
        """更新切片状态"""
        with self._get_connection() as conn:
            if batch_id is not None:
                conn.execute(
                    "UPDATE chunks SET status = ?, batch_id = ? WHERE id = ?",
                    (status.value, batch_id, chunk_id),
                )
            else:
                conn.execute(
                    "UPDATE chunks SET status = ? WHERE id = ?",
                    (status.value, chunk_id),
                )

    def _row_to_chunk(self, row: sqlite3.Row) -> VideoChunk:
        return VideoChunk(
            id=row["id"],
            file_path=row["file_path"],
            start_time=_parse_dt(row["start_time"]),
            end_time=_parse_dt(row["end_time"]),
            duration_seconds=row["duration_seconds"],
            status=ChunkStatus(row["status"]),
            batch_id=row["batch_id"],
            window_records_path=row["window_records_path"],
        )

    # ==================== Batches ====================

    def create_batch(self, batch: AnalysisBatch) -> int:
        with self._get_connection() as conn:
            return self._insert_batch(conn, batch)

    def _insert_batch(self, conn, batch):
        cursor = conn.execute(
            """
            INSERT INTO analysis_batches (chunk_ids, start_time, end_time, status, observations_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                json.dumps(batch.chunk_ids),
                batch.start_time.isoformat() if batch.start_time else None,
                batch.end_time.isoformat() if batch.end_time else None,
                batch.status.value,
                batch.observations_json,
            ),
        )
        return cursor.lastrowid

    def update_batch(
        self,
        batch_id: int,
        status: BatchStatus,
        observations_json: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        with self._get_connection() as conn:
            if status == BatchStatus.COMPLETED:
                conn.execute(
                    """
                    UPDATE analysis_batches
                    SET status = ?, observations_json = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status.value, observations_json or "[]", batch_id),
                )
            elif status == BatchStatus.FAILED:
                conn.execute(
                    """
                    UPDATE analysis_batches
                    SET status = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status.value, error_message, batch_id),
                )
            else:
                conn.execute(
                    "UPDATE analysis_batches SET status = ? WHERE id = ?",
                    (status.value, batch_id),
                )

    # ==================== Timeline Cards & Local Session Atomics ====================

    def save_card(
        self,
        card: ActivityCard,
        batch_id: Optional[int] = None,
        *,
        restore_id: Optional[int] = None,
        source: Optional[str] = None,
    ) -> int:
        """保存时间轴卡片"""
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            resolved_source = source or getattr(card, "source", None) or ("visual" if batch_id is not None else "manual")
            is_finalized = 1 if restore_id is not None else (1 if getattr(card, "is_finalized", True) else 0)
            user_edited = 1 if (restore_id is not None or getattr(card, "user_edited", False)) else 0
            refinement_status = "skipped" if restore_id is not None else (
                "pending" if resolved_source == "local" else "none"
            )
            card_id = self._insert_card(
                conn,
                card,
                batch_id=batch_id,
                restore_id=restore_id,
                source=resolved_source,
                user_edited=user_edited,
                is_finalized=is_finalized,
                session_token=None,
                refinement_status=refinement_status,
            )
            if card.segments:
                self._replace_segments_in_tx(conn, card_id, card.segments)
            if card.end_time and resolved_source in ("local", "local_refined"):
                self._advance_watermark_in_tx(conn, card.end_time)
            return card_id

    def _replace_segments_in_tx(
        self, conn: sqlite3.Connection, card_id: int, segments: Sequence[ActivitySegment]
    ) -> None:
        conn.execute("DELETE FROM card_segments WHERE card_id = ?", (card_id,))
        rows = [
            (
                card_id,
                _iso_local(seg.start_time),
                _iso_local(seg.end_time),
                seg.app_name,
                1 if seg.is_distraction else 0,
            )
            for seg in segments
            if seg.start_time and seg.end_time and local_time(seg.end_time) > local_time(seg.start_time)
        ]
        if rows:
            conn.executemany(
                "INSERT INTO card_segments (card_id, start_time, end_time, app_name, is_distraction) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def _insert_context_event_in_tx(
        self, conn: sqlite3.Connection, card_id: Optional[int], event: Optional[dict]
    ) -> Optional[int]:
        if not event:
            return None
        start_dt = event.get("start_time")
        end_dt = event.get("end_time")
        if not start_dt or not end_dt:
            return None
        start_iso = _iso_local(start_dt) if isinstance(start_dt, datetime) else str(start_dt)
        end_iso = _iso_local(end_dt) if isinstance(end_dt, datetime) else str(end_dt)
        cur = conn.execute(
            """
            INSERT INTO context_events (
                start_time, end_time, duration_seconds, app_name, friendly_app, category,
                domain, project_name, document_name, meeting_active, source, card_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                start_iso,
                end_iso,
                float(event.get("duration_seconds", 0.0)),
                str(event.get("app_name", "")),
                str(event.get("friendly_app", "")),
                str(event.get("category", "其他")),
                event.get("domain"),
                event.get("project_name"),
                event.get("document_name"),
                1 if event.get("meeting_active") else 0,
                str(event.get("source", "app_only")),
                card_id,
            ),
        )
        return cur.lastrowid

    def start_local_card(
        self,
        card: ActivityCard,
        session_token: str,
        segments: Sequence[ActivitySegment],
        context_event: Optional[dict] = None,
        *,
        deadline: Optional[float] = None,
    ) -> int:
        """原子创建活跃本机卡片（is_finalized=0, 绑定 session_token）及初始分段。"""
        with self._get_connection(deadline=deadline) as conn:
            conn.execute("BEGIN IMMEDIATE")
            card_id = self._insert_card(
                conn,
                card,
                batch_id=None,
                source="local",
                user_edited=0,
                is_finalized=0,
                session_token=session_token,
                refinement_status="pending",
            )
            self._replace_segments_in_tx(conn, card_id, segments)
            self._insert_context_event_in_tx(conn, card_id, context_event)
            self._advance_watermark_in_tx(conn, card.end_time)
            return card_id

    def extend_local_card(
        self,
        card: ActivityCard,
        *,
        session_token: Optional[str] = None,
        segments: Optional[Sequence[ActivitySegment]] = None,
        context_event: Optional[dict] = None,
        finalize: bool = False,
        deadline: Optional[float] = None,
    ) -> bool:
        """
        延伸活跃本机卡片：
        - 提供 session_token 时强校验 id + session_token + is_finalized=0；
        - 语义字段（category/title/summary/session_key）通过 SQL CASE 原子保护 user_edited=0；
        - 记账字段（end_time/app_sites_json/distractions_json/card_segments）始终准确更新。
        """
        with self._get_connection(deadline=deadline) as conn:
            conn.execute("BEGIN IMMEDIATE")
            app_sites_json = json.dumps([a.to_dict() for a in card.app_sites], ensure_ascii=False)
            distractions_json = json.dumps([d.to_dict() for d in card.distractions], ensure_ascii=False)
            end_iso = _iso_local(card.end_time)

            if session_token is not None:
                sql = (
                    "UPDATE timeline_cards SET "
                    "end_time = ?, app_sites_json = ?, distractions_json = ?, "
                    "category = CASE WHEN user_edited = 0 THEN ? ELSE category END, "
                    "title = CASE WHEN user_edited = 0 THEN ? ELSE title END, "
                    "summary = CASE WHEN user_edited = 0 THEN ? ELSE summary END, "
                    "session_key = CASE WHEN user_edited = 0 THEN ? ELSE session_key END, "
                    "is_finalized = ?, "
                    "session_token = CASE WHEN ? = 1 THEN NULL ELSE session_token END, "
                    "version = version + 1 "
                    "WHERE id = ? AND session_token = ? AND is_finalized = 0"
                )
                params = (
                    end_iso,
                    app_sites_json,
                    distractions_json,
                    card.category,
                    card.title,
                    card.summary,
                    card.session_key,
                    1 if finalize else 0,
                    1 if finalize else 0,
                    card.id,
                    session_token,
                )
            else:
                sql = (
                    "UPDATE timeline_cards SET end_time = ?, app_sites_json = ?, "
                    "distractions_json = ?, version = version + 1 "
                    "WHERE id = ?"
                )
                params = (end_iso, app_sites_json, distractions_json, card.id)

            res = conn.execute(sql, params)
            if res.rowcount != 1:
                return False
            if segments is not None:
                self._replace_segments_in_tx(conn, card.id, segments)
            if context_event is not None:
                self._insert_context_event_in_tx(conn, card.id, context_event)
            self._advance_watermark_in_tx(conn, card.end_time)
            return True

    def upsert_recorder_candidate(
        self,
        *,
        session_token: str,
        primary_card: ActivityCard,
        primary_segments: Sequence[ActivitySegment],
        candidate: dict,
        deadline: Optional[float] = None,
    ) -> bool:
        """在单事务中停住主卡在切出水位并持久化待定分心候选状态。"""
        with self._get_connection(deadline=deadline) as conn:
            conn.execute("BEGIN IMMEDIATE")
            app_sites_json = json.dumps([a.to_dict() for a in primary_card.app_sites], ensure_ascii=False)
            distractions_json = json.dumps([d.to_dict() for d in primary_card.distractions], ensure_ascii=False)
            res = conn.execute(
                "UPDATE timeline_cards SET end_time = ?, app_sites_json = ?, distractions_json = ?, "
                "version = version + 1 WHERE id = ? AND session_token = ? AND is_finalized = 0",
                (
                    _iso_local(primary_card.end_time),
                    app_sites_json,
                    distractions_json,
                    primary_card.id,
                    session_token,
                ),
            )
            if res.rowcount != 1:
                return False
            self._replace_segments_in_tx(conn, primary_card.id, primary_segments)
            conn.execute(
                """
                INSERT INTO recorder_candidates (
                    id, session_token, primary_card_id, primary_session_key,
                    start_time, end_time, app_name, friendly_app, category, context_json, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    session_token = excluded.session_token,
                    primary_card_id = excluded.primary_card_id,
                    primary_session_key = excluded.primary_session_key,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    app_name = excluded.app_name,
                    friendly_app = excluded.friendly_app,
                    category = excluded.category,
                    context_json = excluded.context_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    session_token,
                    primary_card.id,
                    primary_card.session_key,
                    _iso_local(candidate["start_time"]),
                    _iso_local(candidate["end_time"]),
                    candidate["app_name"],
                    candidate["friendly_app"],
                    candidate["category"],
                    json.dumps(candidate.get("context", {}), ensure_ascii=False),
                ),
            )
            self._advance_watermark_in_tx(conn, candidate["end_time"])
            return True

    def absorb_recorder_candidate(
        self,
        *,
        session_token: str,
        primary_card: ActivityCard,
        primary_segments: Sequence[ActivitySegment],
        context_event: Optional[dict] = None,
        deadline: Optional[float] = None,
    ) -> bool:
        """在单事务中将 <=30s 候选吸收为主卡的分心段并清除候选行。"""
        with self._get_connection(deadline=deadline) as conn:
            conn.execute("BEGIN IMMEDIATE")
            app_sites_json = json.dumps([a.to_dict() for a in primary_card.app_sites], ensure_ascii=False)
            distractions_json = json.dumps([d.to_dict() for d in primary_card.distractions], ensure_ascii=False)
            res = conn.execute(
                "UPDATE timeline_cards SET "
                "end_time = ?, app_sites_json = ?, distractions_json = ?, "
                "summary = CASE WHEN user_edited = 0 THEN ? ELSE summary END, "
                "version = version + 1 "
                "WHERE id = ? AND session_token = ? AND is_finalized = 0",
                (
                    _iso_local(primary_card.end_time),
                    app_sites_json,
                    distractions_json,
                    primary_card.summary,
                    primary_card.id,
                    session_token,
                ),
            )
            if res.rowcount != 1:
                conn.execute("DELETE FROM recorder_candidates WHERE id = 1 AND session_token = ?", (session_token,))
                return False
            self._replace_segments_in_tx(conn, primary_card.id, primary_segments)
            self._insert_context_event_in_tx(conn, primary_card.id, context_event)
            conn.execute("DELETE FROM recorder_candidates WHERE id = 1")
            self._advance_watermark_in_tx(conn, primary_card.end_time)
            return True

    def promote_recorder_candidate(
        self,
        *,
        session_token: str,
        primary_card: Optional[ActivityCard],
        primary_segments: Optional[Sequence[ActivitySegment]],
        candidate_card: Optional[ActivityCard],
        candidate_segments: Optional[Sequence[ActivitySegment]],
        candidate_finalize: bool,
        new_session_token: Optional[str] = None,
        candidate_context_event: Optional[dict] = None,
        deadline: Optional[float] = None,
    ) -> Optional[int]:
        """
        在单事务中封口主卡并将已确认候选提交为独立卡片，同时删除候选行。
        若主卡已被删除（rowcount==0），仍继续提交已确认的候选时间避免丢失。
        """
        with self._get_connection(deadline=deadline) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if primary_card is not None and primary_card.id is not None:
                app_sites_json = json.dumps([a.to_dict() for a in primary_card.app_sites], ensure_ascii=False)
                distractions_json = json.dumps([d.to_dict() for d in primary_card.distractions], ensure_ascii=False)
                res = conn.execute(
                    "UPDATE timeline_cards SET end_time = ?, app_sites_json = ?, distractions_json = ?, "
                    "is_finalized = 1, session_token = NULL, version = version + 1 "
                    "WHERE id = ? AND session_token = ? AND is_finalized = 0",
                    (
                        _iso_local(primary_card.end_time),
                        app_sites_json,
                        distractions_json,
                        primary_card.id,
                        session_token,
                    ),
                )
                if res.rowcount == 1 and primary_segments is not None:
                    self._replace_segments_in_tx(conn, primary_card.id, primary_segments)
                self._advance_watermark_in_tx(conn, primary_card.end_time)

            # 确认候选行仍存在（防止删除主卡事务已提前结算过该候选，避免重复提交）
            cand_row = conn.execute("SELECT id FROM recorder_candidates WHERE id = 1").fetchone()
            conn.execute("DELETE FROM recorder_candidates WHERE id = 1")
            if cand_row is None or candidate_card is None:
                return None
            if (
                candidate_card.start_time is None
                or candidate_card.end_time is None
                or local_time(candidate_card.end_time) <= local_time(candidate_card.start_time)
            ):
                return None

            new_id = self._insert_card(
                conn,
                candidate_card,
                batch_id=None,
                source="local",
                user_edited=0,
                is_finalized=1 if candidate_finalize else 0,
                session_token=None if candidate_finalize else new_session_token,
                refinement_status="pending",
            )
            if candidate_segments:
                self._replace_segments_in_tx(conn, new_id, candidate_segments)
            self._insert_context_event_in_tx(conn, new_id, candidate_context_event)
            self._advance_watermark_in_tx(conn, candidate_card.end_time)
            return new_id

    def _insert_card(
        self,
        conn: sqlite3.Connection,
        card: ActivityCard,
        batch_id: Optional[int],
        restore_id: Optional[int] = None,
        *,
        source: str = "visual",
        user_edited: int = 0,
        is_finalized: int = 1,
        session_token: Optional[str] = None,
        version: int = 1,
        refinement_status: str = "none",
    ) -> int:
        cursor = conn.execute(
            """
            INSERT INTO timeline_cards
            (id, batch_id, category, title, summary, start_time, end_time,
             app_sites_json, distractions_json, productivity_score,
             source, user_edited, session_key, session_token, is_finalized, version,
             refinement_status, refinement_lease_id, refinement_lease_expires_at, refinement_attempts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 0)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                restore_id,
                batch_id,
                card.category,
                card.title,
                card.summary,
                _iso_local(card.start_time),
                _iso_local(card.end_time),
                json.dumps([a.to_dict() for a in card.app_sites], ensure_ascii=False),
                json.dumps([d.to_dict() for d in card.distractions], ensure_ascii=False),
                card.productivity_score,
                source,
                int(user_edited),
                card.session_key,
                session_token,
                int(is_finalized),
                int(version),
                refinement_status,
            ),
        )
        return restore_id if restore_id is not None else cursor.lastrowid

    def _load_segments_map(self, conn: sqlite3.Connection, card_ids: Sequence[int]) -> Dict[int, List[ActivitySegment]]:
        if not card_ids:
            return {}
        placeholders = ",".join("?" for _ in card_ids)
        rows = conn.execute(
            f"SELECT card_id, start_time, end_time, app_name, is_distraction "
            f"FROM card_segments WHERE card_id IN ({placeholders}) ORDER BY start_time ASC, id ASC",
            tuple(card_ids),
        ).fetchall()
        out: Dict[int, List[ActivitySegment]] = {}
        for row in rows:
            s = _parse_dt(row["start_time"])
            e = _parse_dt(row["end_time"])
            if s and e:
                out.setdefault(row["card_id"], []).append(
                    ActivitySegment(
                        start_time=s,
                        end_time=e,
                        app_name=row["app_name"],
                        is_distraction=bool(row["is_distraction"]),
                    )
                )
        return out

    def get_cards_for_date(self, date: datetime) -> List[ActivityCard]:
        """Return the original cards that overlap this local calendar day."""
        return self.get_cards_in_range(*day_bounds(date.date()))

    def get_cards_in_range(self, start: datetime, end: datetime) -> List[ActivityCard]:
        latest = end.date()
        if end.time() == datetime.min.time():
            upper = latest.isoformat()
        elif latest < datetime.max.date():
            upper = (latest + timedelta(days=1)).isoformat()
        else:
            upper = latest.isoformat() + "U"
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM timeline_cards WHERE start_time < ? AND end_time > ?",
                (upper, start.date().isoformat()),
            ).fetchall()
            card_ids = [row["id"] for row in rows if row["id"] is not None]
            seg_map = self._load_segments_map(conn, card_ids)
            cards = [self._row_to_card(row, seg_map.get(row["id"], [])) for row in rows]
        return sorted(
            (
                card
                for card in cards
                if card.start_time
                and card.end_time
                and local_time(card.start_time) < end
                and local_time(card.end_time) > start
            ),
            key=lambda card: (local_time(card.start_time), card.id or 0),
        )

    def get_recent_cards(self, limit: int = 10) -> List[ActivityCard]:
        """获取最近的卡片"""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM timeline_cards ORDER BY end_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
            seg_map = self._load_segments_map(conn, [r["id"] for r in rows])
            return [self._row_to_card(row, seg_map.get(row["id"], [])) for row in rows]

    def get_recent_visual_cards(self, limit: int = 5) -> List[ActivityCard]:
        """仅供视觉分析提示词使用：在 LIMIT 前强过滤可信视觉批处理产出的卡片。"""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM timeline_cards "
                "WHERE source = 'visual' AND batch_id IS NOT NULL "
                "ORDER BY end_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_card(row) for row in rows]

    def _row_to_card(
        self, row: sqlite3.Row, segments: Optional[List[ActivitySegment]] = None
    ) -> ActivityCard:
        keys = set(row.keys())
        return ActivityCard(
            id=row["id"],
            category=row["category"],
            title=row["title"],
            summary=row["summary"],
            start_time=_parse_dt(row["start_time"]),
            end_time=_parse_dt(row["end_time"]),
            app_sites=[AppSite.from_dict(a) for a in json.loads(row["app_sites_json"] or "[]")],
            distractions=[Distraction.from_dict(d) for d in json.loads(row["distractions_json"] or "[]")],
            productivity_score=row["productivity_score"],
            source=row["source"] if "source" in keys else "visual",
            user_edited=bool(row["user_edited"]) if "user_edited" in keys else False,
            session_key=row["session_key"] if "session_key" in keys else None,
            is_finalized=bool(row["is_finalized"]) if "is_finalized" in keys else True,
            version=int(row["version"]) if "version" in keys else 1,
            segments=list(segments) if segments else [],
        )

    def update_card(
        self,
        card_id: int,
        category: str = None,
        title: str = None,
        summary: str = None,
        productivity_score: float = None,
    ) -> bool:
        """更新时间轴卡片（置 user_edited=1、递增 version 并撤销任何未完成精炼租约）"""
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                updates = []
                params = []

                if category is not None:
                    updates.append("category = ?")
                    params.append(category)
                if title is not None:
                    updates.append("title = ?")
                    params.append(title)
                if summary is not None:
                    updates.append("summary = ?")
                    params.append(summary)
                if productivity_score is not None:
                    updates.append("productivity_score = ?")
                    params.append(productivity_score)

                if not updates:
                    return False

                updates.extend([
                    "user_edited = 1",
                    "version = version + 1",
                    "refinement_status = CASE WHEN refinement_status IN ('pending', 'claimed') THEN 'skipped' ELSE refinement_status END",
                    "refinement_lease_id = NULL",
                    "refinement_lease_expires_at = 0",
                ])
                params.append(card_id)
                sql = f"UPDATE timeline_cards SET {', '.join(updates)} WHERE id = ?"
                cur = conn.execute(sql, params)
                if cur.rowcount == 0:
                    return False
                logger.info("已更新卡片 %s", card_id)
                return True
        except Exception as e:
            logger.error("更新卡片失败 %s: %s", card_id, e)
            return False

    def delete_card_with_undo(self, card_id: int) -> Optional[str]:
        """
        在同一事务中：
        1. 若存在关联该主卡且已确认时间的候选分心区间，先独立结算为已封口卡片；
        2. 保存完整服务端撤销快照（含 source/user_edited/version/card_segments）；
        3. 显式级联删除 timeline_cards、card_segments、context_events 及匹配候选。
        返回 undo_token；若卡片不存在返回 None。
        """
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM timeline_cards WHERE id = ?", (card_id,)).fetchone()
            if row is None:
                return None

            # 1. 结算关联候选，防止删主卡抹掉已确认候选时间
            cand = conn.execute(
                "SELECT * FROM recorder_candidates WHERE id = 1 AND primary_card_id = ?",
                (card_id,),
            ).fetchone()
            if cand is not None:
                self._settle_candidate_row_in_tx(conn, cand)
                conn.execute("DELETE FROM recorder_candidates WHERE id = 1")

            # 2. 保存服务端撤销快照（保留最新 _MAX_UNDO_SNAPSHOTS 条）
            seg_rows = conn.execute(
                "SELECT start_time, end_time, app_name, is_distraction FROM card_segments "
                "WHERE card_id = ? ORDER BY start_time ASC, id ASC",
                (card_id,),
            ).fetchall()
            segments_payload = [
                {
                    "start_time": r["start_time"],
                    "end_time": r["end_time"],
                    "app_name": r["app_name"],
                    "is_distraction": bool(r["is_distraction"]),
                }
                for r in seg_rows
            ]
            card_obj = self._row_to_card(row)
            undo_token = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO deleted_card_snapshots (
                    undo_token, card_id, card_json, segments_json, source, user_edited, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    undo_token,
                    card_id,
                    json.dumps(card_obj.to_dict(), ensure_ascii=False),
                    json.dumps(segments_payload, ensure_ascii=False),
                    card_obj.source,
                    1 if card_obj.user_edited else 0,
                    int(card_obj.version),
                ),
            )
            conn.execute(
                "DELETE FROM deleted_card_snapshots WHERE undo_token NOT IN ("
                "SELECT undo_token FROM deleted_card_snapshots ORDER BY rowid DESC LIMIT ?)",
                (_MAX_UNDO_SNAPSHOTS,),
            )

            # 3. 显式清理关联子表并删除主卡（保留 local_recorder_watermark 不回退）
            if card_obj.end_time:
                self._advance_watermark_in_tx(conn, card_obj.end_time)
            conn.execute("DELETE FROM card_segments WHERE card_id = ?", (card_id,))
            conn.execute("DELETE FROM context_events WHERE card_id = ?", (card_id,))
            conn.execute("DELETE FROM timeline_cards WHERE id = ?", (card_id,))
            logger.info("已删除卡片 %s", card_id)
            return undo_token

    def delete_card(self, card_id: int) -> bool:
        """删除时间轴卡片"""
        try:
            return self.delete_card_with_undo(card_id) is not None
        except Exception as e:
            logger.error("删除卡片失败 %s: %s", card_id, e)
            return False

    def restore_card_with_snapshot(
        self,
        fallback_card: ActivityCard,
        undo_token: Optional[str] = None,
    ) -> int:
        """
        撤销删除：优先按服务端快照无损恢复 source / user_edited / card_segments。
        强制 is_finalized=1、session_token=NULL、version=old_version+1、清空租约并置 refinement_status='skipped'，
        杜绝旧录制器或删除前发出的在途精炼请求回写。
        """
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            snap = None
            if undo_token:
                snap = conn.execute(
                    "SELECT * FROM deleted_card_snapshots WHERE undo_token = ? AND card_id = ?",
                    (undo_token, fallback_card.id),
                ).fetchone()
            if snap is None and fallback_card.id is not None:
                snap = conn.execute(
                    "SELECT * FROM deleted_card_snapshots WHERE card_id = ? ORDER BY rowid DESC LIMIT 1",
                    (fallback_card.id,),
                ).fetchone()

            if snap is not None:
                data = json.loads(snap["card_json"])
                card = ActivityCard(
                    id=snap["card_id"],
                    category=data.get("category", fallback_card.category),
                    title=data.get("title", fallback_card.title),
                    summary=data.get("summary", fallback_card.summary),
                    start_time=_parse_dt(data.get("start_time")) or fallback_card.start_time,
                    end_time=_parse_dt(data.get("end_time")) or fallback_card.end_time,
                    app_sites=[AppSite.from_dict(a) for a in data.get("app_sites", [])],
                    distractions=[Distraction.from_dict(d) for d in data.get("distractions", [])],
                    productivity_score=float(data.get("productivity_score", 0.0)),
                    source=snap["source"],
                    user_edited=bool(snap["user_edited"]),
                    is_finalized=True,
                    version=int(snap["version"]) + 1,
                )
                segments = [ActivitySegment.from_dict(s) for s in json.loads(snap["segments_json"] or "[]")]
                conn.execute("DELETE FROM deleted_card_snapshots WHERE undo_token = ?", (snap["undo_token"],))
            else:
                card = fallback_card
                segments = list(fallback_card.segments)
                card.version = max(2, int(getattr(fallback_card, "version", 1)) + 1)

            card_id = self._insert_card(
                conn,
                card,
                batch_id=None,
                restore_id=card.id,
                source=card.source or "manual",
                user_edited=1 if snap is None else (1 if card.user_edited else 0),
                is_finalized=1,
                session_token=None,
                version=card.version,
                refinement_status="skipped",
            )
            if segments:
                self._replace_segments_in_tx(conn, card_id, segments)
            if card.end_time:
                self._advance_watermark_in_tx(conn, card.end_time)
            return card_id

    # ==================== Text Refinement Lease & Quota ====================

    def reconcile_expired_refinement_leases(self, now_ts: Optional[float] = None, max_attempts: int = 3) -> Dict[str, int]:
        """回收已过期的精炼租约：达到重试上限转终态 failed，否则退回 pending。"""
        now = time.time() if now_ts is None else now_ts
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            failed = conn.execute(
                "UPDATE timeline_cards SET refinement_status = 'failed', "
                "refinement_lease_id = NULL, refinement_lease_expires_at = 0 "
                "WHERE refinement_status = 'claimed' AND refinement_lease_expires_at <= ? "
                "AND refinement_attempts >= ?",
                (now, max_attempts),
            ).rowcount
            requeued = conn.execute(
                "UPDATE timeline_cards SET refinement_status = 'pending', "
                "refinement_lease_id = NULL, refinement_lease_expires_at = 0 "
                "WHERE refinement_status = 'claimed' AND refinement_lease_expires_at <= ? "
                "AND refinement_attempts < ?",
                (now, max_attempts),
            ).rowcount
            return {"failed": failed, "requeued": requeued}

    def claim_refinement_batch(
        self,
        lease_id: str,
        *,
        now_ts: Optional[float] = None,
        quota_date: Optional[str] = None,
        lease_ttl: float = 180.0,
        max_cards: int = 10,
        daily_limit: int = 24,
        max_attempts: int = 3,
    ) -> List[ActivityCard]:
        """
        原子回收过期租约、校验并递增持久化日额度，然后领取一批已封口且未编辑的本机卡片。
        """
        now = time.time() if now_ts is None else now_ts
        day_str = quota_date or datetime.now().date().isoformat()
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # 先回收过期租约（含达到第 3 次尝试上限的终态收口）
            conn.execute(
                "UPDATE timeline_cards SET refinement_status = 'failed', "
                "refinement_lease_id = NULL, refinement_lease_expires_at = 0 "
                "WHERE refinement_status = 'claimed' AND refinement_lease_expires_at <= ? "
                "AND refinement_attempts >= ?",
                (now, max_attempts),
            )
            conn.execute(
                "UPDATE timeline_cards SET refinement_status = 'pending', "
                "refinement_lease_id = NULL, refinement_lease_expires_at = 0 "
                "WHERE refinement_status = 'claimed' AND refinement_lease_expires_at <= ? "
                "AND refinement_attempts < ?",
                (now, max_attempts),
            )

            # 校验持久化每日批次数硬上限
            qrow = conn.execute(
                "SELECT batch_count FROM refinement_quota WHERE quota_date = ?", (day_str,)
            ).fetchone()
            used = int(qrow["batch_count"]) if qrow else 0
            if used >= daily_limit:
                return []

            rows = conn.execute(
                """
                SELECT * FROM timeline_cards
                WHERE source = 'local'
                  AND is_finalized = 1
                  AND user_edited = 0
                  AND refinement_status = 'pending'
                  AND refinement_attempts < ?
                ORDER BY start_time ASC, id ASC
                LIMIT ?
                """,
                (max_attempts, max_cards),
            ).fetchall()
            if not rows:
                return []

            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"UPDATE timeline_cards SET "
                f"refinement_status = 'claimed', "
                f"refinement_lease_id = ?, "
                f"refinement_lease_expires_at = ?, "
                f"refinement_attempts = refinement_attempts + 1 "
                f"WHERE id IN ({placeholders})",
                (lease_id, now + lease_ttl, *ids),
            )
            conn.execute(
                "INSERT INTO refinement_quota (quota_date, batch_count) VALUES (?, 1) "
                "ON CONFLICT(quota_date) DO UPDATE SET batch_count = batch_count + 1",
                (day_str,),
            )
            seg_map = self._load_segments_map(conn, ids)
            return [self._row_to_card(row, seg_map.get(row["id"], [])) for row in rows]

    def commit_refinement_results(
        self,
        lease_id: str,
        updates: List[dict],
        *,
        skipped_ids: Sequence[int] = (),
        failed_ids: Sequence[int] = (),
        max_attempts: int = 3,
    ) -> int:
        """条件原子提交精炼结果：强校验 id、version、user_edited=0、source='local'、lease_id。"""
        committed = 0
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for item in updates:
                res = conn.execute(
                    """
                    UPDATE timeline_cards SET
                        category = ?, title = ?, summary = ?, productivity_score = ?,
                        source = 'local_refined',
                        refinement_status = 'refined',
                        refinement_lease_id = NULL,
                        refinement_lease_expires_at = 0,
                        version = version + 1
                    WHERE id = ? AND version = ? AND user_edited = 0
                      AND source = 'local' AND refinement_lease_id = ?
                    """,
                    (
                        item["category"],
                        item["title"],
                        item["summary"],
                        float(item["productivity_score"]),
                        int(item["id"]),
                        int(item["expected_version"]),
                        lease_id,
                    ),
                )
                committed += res.rowcount

            for cid in skipped_ids:
                conn.execute(
                    "UPDATE timeline_cards SET refinement_status = 'skipped', "
                    "refinement_lease_id = NULL, refinement_lease_expires_at = 0 "
                    "WHERE id = ? AND refinement_lease_id = ?",
                    (int(cid), lease_id),
                )
            for cid in failed_ids:
                conn.execute(
                    "UPDATE timeline_cards SET "
                    "refinement_status = CASE WHEN refinement_attempts >= ? THEN 'failed' ELSE 'pending' END, "
                    "refinement_lease_id = NULL, refinement_lease_expires_at = 0 "
                    "WHERE id = ? AND refinement_lease_id = ?",
                    (max_attempts, int(cid), lease_id),
                )
        return committed

    def release_refinement_lease(
        self, lease_id: str, *, retryable: bool = True, max_attempts: int = 3
    ) -> int:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if retryable:
                sql = (
                    "UPDATE timeline_cards SET "
                    "refinement_status = CASE WHEN refinement_attempts >= ? THEN 'failed' ELSE 'pending' END, "
                    "refinement_lease_id = NULL, refinement_lease_expires_at = 0 "
                    "WHERE refinement_lease_id = ?"
                )
                return conn.execute(sql, (max_attempts, lease_id)).rowcount
            return conn.execute(
                "UPDATE timeline_cards SET refinement_status = 'failed', "
                "refinement_lease_id = NULL, refinement_lease_expires_at = 0 "
                "WHERE refinement_lease_id = ?",
                (lease_id,),
            ).rowcount

    # ==================== Settings ====================

    def get_setting(self, key: str, default: str = "") -> str:
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM settings WHERE key = ?", (key,)
                ).fetchone()
            return row["value"] if row else default
        except Exception as e:
            logger.error("读取设置失败 %s: %s", key, e)
            return default

    def set_setting(self, key: str, value: str):
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
                    """,
                    (key, value, value),
                )
            logger.info("已保存设置 %s", key)
        except Exception as e:
            logger.error("保存设置失败 %s: %s", key, e)

    # ==================== Daily Reports ====================

    def get_report_revision(self, day):
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content, source_key, previous_content IS NOT NULL AS has_previous "
                "FROM daily_reports WHERE report_date=?",
                (day,),
            ).fetchone()
            return dict(row) if row else {}

    def save_report_revision(self, day, content, source_key):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO daily_reports(report_date,content,source_key) VALUES(?,?,?) "
                "ON CONFLICT(report_date) DO UPDATE SET previous_content=content, previous_source_key=source_key, "
                "content=excluded.content, source_key=excluded.source_key, created_at=CURRENT_TIMESTAMP",
                (day, content, source_key),
            )

    def restore_report_revision(self, day):
        with self._get_connection() as conn:
            return conn.execute(
                "UPDATE daily_reports SET content=previous_content, source_key=previous_source_key, "
                "previous_content=content, previous_source_key=source_key "
                "WHERE report_date=? AND previous_content IS NOT NULL",
                (day,),
            ).rowcount == 1
