"""
Dayflow - SQLite 连接池管理
支持连接复用、空闲清理、单调截止时间约束与优雅关闭
"""
import sqlite3
import threading
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DEFAULT_BUSY_TIMEOUT_MS = 3000


class PoolExhaustedError(Exception):
    """连接池耗尽异常"""
    pass


@dataclass
class PooledConnection:
    """池化连接包装"""
    connection: sqlite3.Connection
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    in_use: bool = False

    def mark_used(self):
        self.last_used = datetime.now()
        self.in_use = True

    def mark_released(self):
        self.last_used = datetime.now()
        self.in_use = False

    def is_idle_timeout(self, idle_timeout: float) -> bool:
        if self.in_use:
            return False
        idle_seconds = (datetime.now() - self.last_used).total_seconds()
        return idle_seconds > idle_timeout


class ConnectionPool:
    """
    SQLite 连接池

    功能:
    - 连接复用，减少创建开销
    - 可配置的最大连接数与单调截止时间（贯穿取连接与 busy_timeout）
    - 空闲连接自动清理
    - 优雅关闭，执行 WAL checkpoint
    """

    def __init__(
        self,
        db_path: str,
        max_size: int = 5,
        timeout: float = 4.5,
        idle_timeout: float = 300.0,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ):
        self.db_path = str(db_path)
        self.max_size = max_size
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.busy_timeout_ms = busy_timeout_ms

        self._pool: list[PooledConnection] = []
        self._lock = threading.RLock()
        self._closed = False

        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_stop_event = threading.Event()
        self._start_cleanup_thread()

        logger.info(
            "连接池已初始化: max_size=%s, timeout=%ss, busy_timeout=%sms, idle_timeout=%ss",
            max_size, timeout, busy_timeout_ms, idle_timeout,
        )

    def _start_cleanup_thread(self):
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="ConnectionPool-Cleanup",
        )
        self._cleanup_thread.start()

    def _cleanup_loop(self):
        while not self._cleanup_stop_event.is_set():
            self._cleanup_stop_event.wait(60)
            if not self._cleanup_stop_event.is_set():
                self._cleanup_idle()

    def _cleanup_idle(self):
        with self._lock:
            if self._closed:
                return

            to_remove = [p for p in self._pool if p.is_idle_timeout(self.idle_timeout)]
            for pooled_conn in to_remove:
                try:
                    pooled_conn.connection.close()
                    self._pool.remove(pooled_conn)
                    logger.debug("已清理空闲连接，当前池大小: %s", len(self._pool))
                except Exception as e:
                    logger.warning("清理空闲连接失败: %s", e)

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=self.busy_timeout_ms / 1000.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute(f"PRAGMA busy_timeout={int(self.busy_timeout_ms)}")
        return conn

    def acquire(self, deadline: Optional[float] = None) -> sqlite3.Connection:
        """
        获取连接。传入 monotonic deadline 时，取连接与 SQLite 写锁等待共享同一截止时间。
        """
        if self._closed:
            raise RuntimeError("连接池已关闭")

        effective_deadline = time.monotonic() + self.timeout
        if deadline is not None:
            effective_deadline = min(effective_deadline, deadline)

        while True:
            with self._lock:
                if self._closed:
                    raise RuntimeError("连接池已关闭")

                for pooled_conn in self._pool:
                    if not pooled_conn.in_use:
                        pooled_conn.mark_used()
                        return pooled_conn.connection

                if len(self._pool) < self.max_size:
                    conn = self._create_connection()
                    pooled_conn = PooledConnection(connection=conn)
                    pooled_conn.mark_used()
                    self._pool.append(pooled_conn)
                    return conn

            remaining = effective_deadline - time.monotonic()
            if remaining <= 0:
                raise PoolExhaustedError(f"连接池等待超时（剩余 {remaining:.2f}s）")
            time.sleep(min(0.05, remaining))

    def release(self, conn: sqlite3.Connection) -> None:
        with self._lock:
            for pooled_conn in self._pool:
                if pooled_conn.connection is conn:
                    pooled_conn.mark_released()
                    return

            logger.warning("释放的连接不在池中，直接关闭")
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def get_connection(self, deadline: Optional[float] = None):
        """
        获取连接的上下文管理器。若提供 monotonic deadline，
        动态收紧连接上的 PRAGMA busy_timeout 以确保总等待不超过截止时间。
        """
        conn = self.acquire(deadline=deadline)
        adjusted_timeout = False
        try:
            if deadline is not None:
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    raise sqlite3.OperationalError("数据库操作已超出截止时间")
                conn.execute(f"PRAGMA busy_timeout={max(50, min(self.busy_timeout_ms, remaining_ms))}")
                adjusted_timeout = True
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            if adjusted_timeout:
                try:
                    conn.execute(f"PRAGMA busy_timeout={int(self.busy_timeout_ms)}")
                except Exception:
                    pass
            self.release(conn)

    def close_all(self) -> None:
        """关闭所有连接并在最后一个连接上执行一次 WAL checkpoint"""
        with self._lock:
            self._closed = True
            self._cleanup_stop_event.set()
            connections = list(self._pool)
            self._pool.clear()
            cleanup_thread = self._cleanup_thread

        if cleanup_thread and cleanup_thread.is_alive() and cleanup_thread is not threading.current_thread():
            cleanup_thread.join(timeout=2.0)

        for idx, pooled_conn in enumerate(connections):
            is_last = idx == len(connections) - 1
            try:
                if is_last:
                    pooled_conn.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                pooled_conn.connection.close()
            except Exception as e:
                logger.warning("关闭连接失败: %s", e)

        logger.info("连接池已关闭，所有连接已释放")
