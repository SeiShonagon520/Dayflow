"""
Dayflow Windows - 数据库管理
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from contextlib import contextmanager

import config
from core.types import (
    VideoChunk, ChunkStatus,
    AnalysisBatch, BatchStatus,
    ActivityCard, AppSite, Distraction
)


class StorageManager:
    """SQLite 数据库管理器"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.DATABASE_PATH
        self._init_database()
    
    def _init_database(self):
        """初始化数据库结构"""
        schema_path = Path(__file__).parent / "schema.sql"
        with self._get_connection() as conn:
            with open(schema_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接上下文"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # ==================== Chunks ====================
    
    def save_chunk(self, chunk: VideoChunk) -> int:
        """保存视频切片"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO chunks (file_path, start_time, end_time, duration_seconds, status, batch_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.file_path,
                    chunk.start_time.isoformat() if chunk.start_time else None,
                    chunk.end_time.isoformat() if chunk.end_time else None,
                    chunk.duration_seconds,
                    chunk.status.value,
                    chunk.batch_id
                )
            )
            return cursor.lastrowid
    
    def get_pending_chunks(self, limit: int = 100) -> List[VideoChunk]:
        """获取待分析的切片"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM chunks 
                WHERE status = ? 
                ORDER BY start_time ASC 
                LIMIT ?
                """,
                (ChunkStatus.PENDING.value, limit)
            )
            return [self._row_to_chunk(row) for row in cursor.fetchall()]
    
    def update_chunk_status(self, chunk_id: int, status: ChunkStatus, batch_id: Optional[int] = None):
        """更新切片状态"""
        with self._get_connection() as conn:
            if batch_id is not None:
                conn.execute(
                    "UPDATE chunks SET status = ?, batch_id = ? WHERE id = ?",
                    (status.value, batch_id, chunk_id)
                )
            else:
                conn.execute(
                    "UPDATE chunks SET status = ? WHERE id = ?",
                    (status.value, chunk_id)
                )
    
    def _row_to_chunk(self, row: sqlite3.Row) -> VideoChunk:
        """将数据库行转换为 VideoChunk 对象"""
        return VideoChunk(
            id=row["id"],
            file_path=row["file_path"],
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            duration_seconds=row["duration_seconds"],
            status=ChunkStatus(row["status"]),
            batch_id=row["batch_id"]
        )
    
    # ==================== Batches ====================
    
    def create_batch(self, batch: AnalysisBatch) -> int:
        """创建分析批次"""
        with self._get_connection() as conn:
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
                    batch.observations_json
                )
            )
            return cursor.lastrowid
    
    def update_batch(self, batch_id: int, status: BatchStatus, 
                     observations_json: Optional[str] = None,
                     error_message: Optional[str] = None):
        """更新批次状态"""
        with self._get_connection() as conn:
            if status == BatchStatus.COMPLETED:
                conn.execute(
                    """
                    UPDATE analysis_batches 
                    SET status = ?, observations_json = ?, completed_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                    """,
                    (status.value, observations_json or "[]", batch_id)
                )
            elif status == BatchStatus.FAILED:
                conn.execute(
                    """
                    UPDATE analysis_batches 
                    SET status = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                    """,
                    (status.value, error_message, batch_id)
                )
            else:
                conn.execute(
                    "UPDATE analysis_batches SET status = ? WHERE id = ?",
                    (status.value, batch_id)
                )
    
    def get_pending_batches(self) -> List[AnalysisBatch]:
        """获取待处理的批次"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM analysis_batches WHERE status = ?",
                (BatchStatus.PENDING.value,)
            )
            return [self._row_to_batch(row) for row in cursor.fetchall()]
    
    def _row_to_batch(self, row: sqlite3.Row) -> AnalysisBatch:
        """将数据库行转换为 AnalysisBatch 对象"""
        return AnalysisBatch(
            id=row["id"],
            chunk_ids=json.loads(row["chunk_ids"]),
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            status=BatchStatus(row["status"]),
            observations_json=row["observations_json"],
            error_message=row["error_message"]
        )
    
    # ==================== Timeline Cards ====================
    
    def save_card(self, card: ActivityCard, batch_id: Optional[int] = None) -> int:
        """保存时间轴卡片"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO timeline_cards 
                (batch_id, category, title, summary, start_time, end_time, 
                 app_sites_json, distractions_json, productivity_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    card.category,
                    card.title,
                    card.summary,
                    card.start_time.isoformat() if card.start_time else None,
                    card.end_time.isoformat() if card.end_time else None,
                    json.dumps([a.to_dict() for a in card.app_sites]),
                    json.dumps([d.to_dict() for d in card.distractions]),
                    card.productivity_score
                )
            )
            return cursor.lastrowid
    
    def get_cards_for_date(self, date: datetime) -> List[ActivityCard]:
        """获取指定日期的时间轴卡片"""
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM timeline_cards 
                WHERE start_time >= ? AND start_time <= ?
                ORDER BY start_time ASC
                """,
                (start.isoformat(), end.isoformat())
            )
            return [self._row_to_card(row) for row in cursor.fetchall()]
    
    def get_recent_cards(self, limit: int = 10) -> List[ActivityCard]:
        """获取最近的卡片（用作上下文）"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM timeline_cards 
                ORDER BY end_time DESC 
                LIMIT ?
                """,
                (limit,)
            )
            return [self._row_to_card(row) for row in cursor.fetchall()]
    
    def _row_to_card(self, row: sqlite3.Row) -> ActivityCard:
        """将数据库行转换为 ActivityCard 对象"""
        return ActivityCard(
            id=row["id"],
            category=row["category"],
            title=row["title"],
            summary=row["summary"],
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            app_sites=[AppSite.from_dict(a) for a in json.loads(row["app_sites_json"] or "[]")],
            distractions=[Distraction.from_dict(d) for d in json.loads(row["distractions_json"] or "[]")],
            productivity_score=row["productivity_score"]
        )
    
    # ==================== Settings ====================
    
    def get_setting(self, key: str, default: str = "") -> str:
        """获取设置值"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            return row["value"] if row else default
    
    def set_setting(self, key: str, value: str):
        """设置值"""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
                """,
                (key, value, value)
            )
