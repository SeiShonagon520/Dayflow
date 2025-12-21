"""
Dayflow Windows - 数据库管理
"""
import sqlite3
import json
import logging
import threading
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
from database.connection_pool import ConnectionPool, PoolExhaustedError

logger = logging.getLogger(__name__)


class StorageManager:
    """SQLite 数据库管理器 - 使用连接池"""
    
    def __init__(self, db_path: Optional[Path] = None, use_pool: bool = True):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
            use_pool: 是否使用连接池（默认 True）
        """
        self.db_path = db_path or config.DATABASE_PATH
        self._use_pool = use_pool
        self._pool: Optional[ConnectionPool] = None
        self._local = threading.local()  # 线程本地存储（兼容模式）
        
        logger.info(f"数据库路径: {self.db_path}")
        
        if use_pool:
            self._pool = ConnectionPool(
                db_path=str(self.db_path),
                max_size=5,
                timeout=30.0,
                idle_timeout=300.0
            )
        
        self._init_database()
    
    def _init_database(self):
        """初始化数据库结构"""
        schema_path = Path(__file__).parent / "schema.sql"
        with self._get_connection() as conn:
            with open(schema_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            
            # 数据库迁移：为旧数据库添加新字段
            self._migrate_database(conn)
    
    def _migrate_database(self, conn):
        """数据库迁移 - 添加新字段"""
        try:
            # 检查 chunks 表是否有 window_records_path 字段
            cursor = conn.execute("PRAGMA table_info(chunks)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "window_records_path" not in columns:
                conn.execute("ALTER TABLE chunks ADD COLUMN window_records_path TEXT")
                logger.info("数据库迁移: 添加 chunks.window_records_path 字段")
        except Exception as e:
            logger.debug(f"数据库迁移检查: {e}")
    
    def _get_cached_connection(self):
        """获取线程本地的缓存连接（兼容模式）"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # 使用 WAL 模式，但确保数据立即写入
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=FULL")  # 改为 FULL 确保数据写入
        return self._local.conn
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接上下文"""
        if self._use_pool and self._pool:
            # 使用连接池
            with self._pool.get_connection() as conn:
                yield conn
        else:
            # 兼容模式：使用缓存连接
            conn = self._get_cached_connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def close(self):
        """关闭数据库连接"""
        if self._use_pool and self._pool:
            # 关闭连接池
            self._pool.close_all()
            self._pool = None
            logger.info("数据库连接池已关闭")
        else:
            # 兼容模式
            if hasattr(self._local, 'conn') and self._local.conn is not None:
                try:
                    # 最终 checkpoint 确保所有数据写入主数据库文件
                    self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    self._local.conn.close()
                    logger.info("数据库连接已关闭")
                except Exception as e:
                    logger.error(f"关闭数据库连接失败: {e}")
                finally:
                    self._local.conn = None
    
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
                    chunk.window_records_path
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
        # 安全获取 window_records_path（兼容旧数据库）
        window_records_path = None
        try:
            window_records_path = row["window_records_path"]
        except (IndexError, KeyError):
            pass
        
        return VideoChunk(
            id=row["id"],
            file_path=row["file_path"],
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            duration_seconds=row["duration_seconds"],
            status=ChunkStatus(row["status"]),
            batch_id=row["batch_id"],
            window_records_path=window_records_path
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
    
    def update_card(self, card_id: int, category: str = None, title: str = None, 
                    summary: str = None, productivity_score: float = None) -> bool:
        """更新时间轴卡片"""
        try:
            with self._get_connection() as conn:
                # 构建动态更新语句
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
                
                params.append(card_id)
                sql = f"UPDATE timeline_cards SET {', '.join(updates)} WHERE id = ?"
                conn.execute(sql, params)
                logger.info(f"已更新卡片 {card_id}")
                return True
        except Exception as e:
            logger.error(f"更新卡片失败 {card_id}: {e}")
            return False
    
    def delete_card(self, card_id: int) -> bool:
        """删除时间轴卡片"""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM timeline_cards WHERE id = ?", (card_id,))
                logger.info(f"已删除卡片 {card_id}")
                return True
        except Exception as e:
            logger.error(f"删除卡片失败 {card_id}: {e}")
            return False
    
    # ==================== Settings ====================
    
    def get_setting(self, key: str, default: str = "") -> str:
        """获取设置值 - 使用独立连接确保读取最新数据"""
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            conn.close()
            value = row["value"] if row else default
            logger.debug(f"读取设置 {key}: {'已找到' if row else '使用默认值'}")
            return value
        except Exception as e:
            logger.error(f"读取设置失败 {key}: {e}")
            return default
    
    def set_setting(self, key: str, value: str):
        """设置值 - 使用独立连接确保立即写入"""
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
                """,
                (key, value, value)
            )
            conn.commit()
            # 强制 checkpoint 确保 WAL 数据写入主文件
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            logger.info(f"已保存设置 {key}")
        except Exception as e:
            logger.error(f"保存设置失败 {key}: {e}")
