"""
Dayflow - SQLite 连接池管理
支持连接复用、空闲清理、优雅关闭
"""
import sqlite3
import threading
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty, Full
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


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
        """标记为使用中"""
        self.last_used = datetime.now()
        self.in_use = True
    
    def mark_released(self):
        """标记为已释放"""
        self.last_used = datetime.now()
        self.in_use = False
    
    def is_idle_timeout(self, idle_timeout: float) -> bool:
        """检查是否空闲超时"""
        if self.in_use:
            return False
        idle_seconds = (datetime.now() - self.last_used).total_seconds()
        return idle_seconds > idle_timeout


class ConnectionPool:
    """
    SQLite 连接池
    
    功能:
    - 连接复用，减少创建开销
    - 可配置的最大连接数
    - 空闲连接自动清理
    - 优雅关闭，执行 WAL checkpoint
    """
    
    def __init__(
        self,
        db_path: str,
        max_size: int = 5,
        timeout: float = 30.0,
        idle_timeout: float = 300.0
    ):
        """
        初始化连接池
        
        Args:
            db_path: 数据库文件路径
            max_size: 最大连接数
            timeout: 获取连接超时时间（秒）
            idle_timeout: 空闲连接超时时间（秒）
        """
        self.db_path = str(db_path)
        self.max_size = max_size
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        
        self._pool: list[PooledConnection] = []
        self._lock = threading.RLock()
        self._closed = False
        
        # 启动空闲清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_stop_event = threading.Event()
        self._start_cleanup_thread()
        
        logger.info(f"连接池已初始化: max_size={max_size}, timeout={timeout}s, idle_timeout={idle_timeout}s")
    
    def _start_cleanup_thread(self):
        """启动空闲连接清理线程"""
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="ConnectionPool-Cleanup"
        )
        self._cleanup_thread.start()
    
    def _cleanup_loop(self):
        """空闲连接清理循环"""
        while not self._cleanup_stop_event.is_set():
            # 每 60 秒检查一次
            self._cleanup_stop_event.wait(60)
            if not self._cleanup_stop_event.is_set():
                self._cleanup_idle()
    
    def _cleanup_idle(self):
        """清理空闲连接"""
        with self._lock:
            if self._closed:
                return
            
            to_remove = []
            for pooled_conn in self._pool:
                if pooled_conn.is_idle_timeout(self.idle_timeout):
                    to_remove.append(pooled_conn)
            
            for pooled_conn in to_remove:
                try:
                    pooled_conn.connection.close()
                    self._pool.remove(pooled_conn)
                    logger.debug(f"已清理空闲连接，当前池大小: {len(self._pool)}")
                except Exception as e:
                    logger.warning(f"清理空闲连接失败: {e}")
    
    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0
        )
        conn.row_factory = sqlite3.Row
        # 使用 WAL 模式
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn
    
    def acquire(self) -> sqlite3.Connection:
        """
        获取连接
        
        阻塞直到获取到连接或超时
        
        Returns:
            数据库连接
        
        Raises:
            PoolExhaustedError: 连接池耗尽且超时
        """
        if self._closed:
            raise RuntimeError("连接池已关闭")
        
        start_time = time.time()
        
        while True:
            with self._lock:
                # 尝试获取空闲连接
                for pooled_conn in self._pool:
                    if not pooled_conn.in_use:
                        pooled_conn.mark_used()
                        logger.debug(f"复用连接，当前池大小: {len(self._pool)}")
                        return pooled_conn.connection
                
                # 如果池未满，创建新连接
                if len(self._pool) < self.max_size:
                    conn = self._create_connection()
                    pooled_conn = PooledConnection(connection=conn)
                    pooled_conn.mark_used()
                    self._pool.append(pooled_conn)
                    logger.debug(f"创建新连接，当前池大小: {len(self._pool)}")
                    return conn
            
            # 检查超时
            elapsed = time.time() - start_time
            if elapsed >= self.timeout:
                raise PoolExhaustedError(
                    f"连接池耗尽，等待 {self.timeout} 秒后超时"
                )
            
            # 短暂等待后重试
            time.sleep(0.1)
    
    def release(self, conn: sqlite3.Connection) -> None:
        """
        释放连接回池
        
        Args:
            conn: 要释放的连接
        """
        with self._lock:
            for pooled_conn in self._pool:
                if pooled_conn.connection is conn:
                    pooled_conn.mark_released()
                    logger.debug("连接已释放回池")
                    return
            
            # 如果连接不在池中（可能是异常情况），直接关闭
            logger.warning("释放的连接不在池中，直接关闭")
            try:
                conn.close()
            except Exception:
                pass
    
    @contextmanager
    def get_connection(self):
        """
        获取连接的上下文管理器
        
        自动获取和释放连接
        
        Yields:
            数据库连接
        """
        conn = self.acquire()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.release(conn)
    
    def close_all(self) -> None:
        """
        关闭所有连接
        
        执行 WAL checkpoint 确保数据写入
        """
        with self._lock:
            self._closed = True
            
            # 停止清理线程
            self._cleanup_stop_event.set()
            
            # 关闭所有连接
            for pooled_conn in self._pool:
                try:
                    # 执行 WAL checkpoint
                    pooled_conn.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    pooled_conn.connection.close()
                except Exception as e:
                    logger.warning(f"关闭连接失败: {e}")
            
            self._pool.clear()
            logger.info("连接池已关闭，所有连接已释放")
    
    @property
    def size(self) -> int:
        """当前池中的连接数"""
        with self._lock:
            return len(self._pool)
    
    @property
    def available(self) -> int:
        """当前可用的连接数"""
        with self._lock:
            return sum(1 for c in self._pool if not c.in_use)
    
    @property
    def in_use(self) -> int:
        """当前使用中的连接数"""
        with self._lock:
            return sum(1 for c in self._pool if c.in_use)
