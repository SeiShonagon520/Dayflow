"""
Dayflow Windows - 分析调度器
批量处理视频切片，调用 API 生成时间轴卡片
"""
import asyncio
import logging
import json
import math
import threading
import time
from contextlib import contextmanager
from typing import List, Optional
from pathlib import Path

import httpx

import config
from core.activity_time import clip_card, local_time
from core.chunk_files import chunk_files, protected_chunk_files
from core.types import (
    VideoChunk,
    AnalysisBatch, BatchStatus,
)
from core.llm_provider import DayflowBackendProvider, ProviderAuthorizationError, UnreadableChunkError
from database.storage import StorageManager

logger = logging.getLogger(__name__)


@contextmanager
def analysis_worker_lock(db_path):
    """Only the process that owns the queue may recover interrupted claims."""
    path = Path(str(db_path) + ".analysis.lock")
    with path.open("a+b") as handle:
        handle.seek(0)
        import os
        if os.name == "nt":
            import msvcrt
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            acquire()
        except OSError:
            yield False
        else:
            # Closing the handle releases the lock, including after a force quit.
            yield True


class AnalysisScheduler:
    """
    分析调度器
    - 定时扫描待分析的视频切片
    - 打包成批次发送给 API
    - 将结果存入数据库
    """
    
    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        provider: Optional[DayflowBackendProvider] = None,
        batch_duration_minutes: int = None,
        scan_interval_seconds: int = None,
    ):
        self.storage = storage or StorageManager()
        self.provider = provider or DayflowBackendProvider()
        self._fixed_provider = provider is not None
        self._provider_settings = self._settings()
        self._auth_blocked = False
        self.batch_duration = batch_duration_minutes or config.BATCH_DURATION_MINUTES
        self.scan_interval = scan_interval_seconds or config.ANALYSIS_INTERVAL_SECONDS
        
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._thread_lock = threading.Lock()
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def start(self):
        with self._thread_lock:
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                return
            self._stop_event.clear()
            self._running = True
            self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._scheduler_thread.start()

    def stop(self, deadline: Optional[float] = None):
        self._stop_event.set()
        loop, task = self._loop, self._worker_task
        if loop and task:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # The worker has already finished closing its event loop.
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            wait_s = max(0.2, (deadline - time.monotonic()) if deadline is not None else 5.0)
            self._scheduler_thread.join(timeout=wait_s)
        return not self._running

    def _scheduler_loop(self):
        try:
            with analysis_worker_lock(self.storage.db_path) as acquired:
                if acquired and not self._stop_event.is_set():
                    recovered = self.storage.recover_interrupted_analysis()
                    if recovered:
                        logger.info("恢复中断的录制切片: %s", recovered)
                    asyncio.run(self._run_worker())
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("分析调度器无法启动")
        finally:
            self._loop = self._worker_task = None
            self._running = False

    async def _run_worker(self):
        self._loop = asyncio.get_running_loop()
        self._worker_task = asyncio.current_task()
        try:
            while not self._stop_event.is_set():
                try:
                    await self._scan_and_process()
                except Exception:
                    logger.exception("读取分析队列失败")
                await asyncio.sleep(self.scan_interval)
        finally:
            await self._close_provider()

    @staticmethod
    def _settings():
        return config.API_BASE_URL, config.API_KEY, config.API_MODEL

    async def _close_provider(self):
        close = getattr(self.provider, "close", None)
        if close:
            await close()

    async def _refresh_provider(self):
        settings = self._settings()
        if not self._fixed_provider and settings != self._provider_settings:
            await self._close_provider()
            self.provider = DayflowBackendProvider()
            self._provider_settings = settings
            self._auth_blocked = False

    async def _scan_and_process(self):
        await self._refresh_provider()
        if self._auth_blocked:
            return
        batches = self._create_batches(self.storage.get_pending_chunks())
        for batch in batches:
            if self._stop_event.is_set():
                break
            retry_reason = await self._process_batch(batch)
            if retry_reason in {"network", "authorization"}:
                break
    
    def _create_batches(self, chunks: List[VideoChunk]) -> List[List[VideoChunk]]:
        """将切片分组为批次"""
        if not chunks:
            return []
        
        batches = []
        current_batch = []
        batch_duration = 0
        max_duration = self.batch_duration * 60  # 转换为秒
        
        for chunk in chunks:
            is_gap = current_batch and chunk.start_time and current_batch[-1].end_time and (
                local_time(chunk.start_time) - local_time(current_batch[-1].end_time)
            ).total_seconds() > 1
            if current_batch and (is_gap or batch_duration + chunk.duration_seconds > max_duration):
                batches.append(current_batch)
                current_batch = []
                batch_duration = 0
            
            current_batch.append(chunk)
            batch_duration += chunk.duration_seconds
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    @staticmethod
    def _failure_reason(error):
        if isinstance(error, ProviderAuthorizationError):
            return "authorization"
        if isinstance(error, httpx.HTTPStatusError):
            code = error.response.status_code
            if code in (401, 403):
                return "authorization"
            if code in (408, 429) or code >= 500:
                return "network"
        if isinstance(error, httpx.TransportError):
            return "network"
        return "provider"

    async def _process_batch(self, chunks: List[VideoChunk]):
        if not chunks:
            return None
        batch = AnalysisBatch(
            chunk_ids=[c.id for c in chunks if c.id],
            start_time=chunks[0].start_time,
            end_time=chunks[-1].end_time,
            status=BatchStatus.PROCESSING,
        )
        batch_id = self.storage.claim_analysis_batch(batch)
        if batch_id is None:
            return None

        try:
            observations = []
            readable = []
            for chunk in chunks:
                try:
                    records = None
                    if chunk.window_records_path:
                        try:
                            records = json.loads(Path(chunk.window_records_path).read_text(encoding="utf-8"))
                        except (OSError, ValueError):
                            logger.warning("切片 %s 的窗口记录不可读", chunk.id)
                    if not Path(chunk.file_path).is_file():
                        raise FileNotFoundError()
                    result = await self.provider.transcribe_video(
                        chunk.file_path, chunk.duration_seconds, window_records=records,
                    )
                except (FileNotFoundError, UnreadableChunkError):
                    self.storage.release_analysis_chunks(batch_id, [chunk.id], "unreadable_media", retryable=False)
                    continue
                valid = []
                offset = (local_time(chunk.start_time) - local_time(batch.start_time)).total_seconds()
                for item in result:
                    if not math.isfinite(item.start_ts) or not math.isfinite(item.end_ts):
                        continue
                    start = max(0, item.start_ts)
                    end = min(chunk.duration_seconds, item.end_ts)
                    if end > start:
                        item.start_ts, item.end_ts = start + offset, end + offset
                        valid.append(item)
                if not valid:
                    self.storage.release_analysis_chunks(batch_id, [chunk.id], "empty_observations", retryable=True)
                    continue
                readable.append(chunk)
                observations.extend(valid)

            if not observations:
                self.storage.release_analysis_chunks(batch_id, [], "empty_observations", retryable=False, finish_batch=True)
                return None

            cards = await self.provider.generate_activity_cards(
                observations, self.storage.get_recent_visual_cards(limit=5), start_time=batch.start_time,
            )
            # Only good results inside recorded time can complete a slice.
            intervals = []
            for chunk in sorted(readable, key=lambda c: local_time(c.start_time)):
                start, end = local_time(chunk.start_time), local_time(chunk.end_time)
                if intervals and start <= intervals[-1][1]:
                    intervals[-1] = (intervals[-1][0], max(intervals[-1][1], end))
                else:
                    intervals.append((start, end))
            clipped_cards = [
                clipped for card in cards for start, end in intervals
                if math.isfinite(card.productivity_score)
                and (clipped := clip_card(card, start, end)) is not None
            ]
            completed = [
                chunk for chunk in readable if any(
                    card.start_time < local_time(chunk.end_time)
                    and card.end_time > local_time(chunk.start_time)
                    for card in clipped_cards
                )
            ]
            if not completed:
                self.storage.release_analysis_chunks(batch_id, batch.chunk_ids, "empty_cards", retryable=True, finish_batch=True)
                return None
            completed_ids = {chunk.id for chunk in completed}
            uncovered = [chunk.id for chunk in readable if chunk.id not in completed_ids]
            if uncovered:
                self.storage.release_analysis_chunks(batch_id, uncovered, "empty_cards", retryable=True)

            self.storage.commit_analysis_batch(
                batch_id, list(completed_ids), [item.to_dict() for item in observations], clipped_cards,
            )
        except Exception as error:
            reason = self._failure_reason(error)
            self.storage.release_analysis_chunks(
                batch_id, batch.chunk_ids, reason, retryable=reason != "authorization", finish_batch=True,
            )
            self._auth_blocked = reason == "authorization"
            logger.warning("分析批次 %s 暂未完成: %s", batch_id, reason)
            return reason

        logger.info("批次 %s 已提交 %s 张卡片", batch_id, len(clipped_cards))
        # Cleanup follows the database commit and cannot change the outcome.
        if config.AUTO_DELETE_ANALYZED_CHUNKS:
            self._delete_chunk_files(completed)
        try:
            self._cleanup_if_over_limit()
        except OSError:
            logger.warning("缓存目录暂时无法清理")
        return None

    def _delete_chunk_files(self, chunks: List[VideoChunk]):
        """
        删除已分析完成的视频切片文件和窗口记录文件
        只在分析成功后调用，确保数据已保存到数据库
        """
        deleted_count = 0
        for chunk in chunks:
            try:
                # 删除视频文件
                chunk_path = Path(chunk.file_path)
                if chunk_path.exists():
                    chunk_path.unlink()
                    deleted_count += 1
                    logger.debug(f"已删除视频切片: {chunk_path.name}")
                
                # 删除窗口记录文件
                if chunk.window_records_path:
                    window_records_path = Path(chunk.window_records_path)
                    if window_records_path.exists():
                        window_records_path.unlink()
                        logger.debug(f"已删除窗口记录: {window_records_path.name}")
            except Exception as e:
                logger.warning(f"删除文件失败 {chunk.file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"已清理 {deleted_count} 个视频切片文件")

    def _cleanup_if_over_limit(self):
        """当缓存目录超过大小上限时，按时间从旧到新删除文件"""
        chunks_dir = config.CHUNKS_DIR
        if not chunks_dir.exists():
            return

        max_bytes = config.CHUNKS_MAX_SIZE_GB * 1024 ** 3

        try:
            files = list(chunk_files(chunks_dir))
            protected = protected_chunk_files(self.storage)
        except Exception as e:
            logger.warning(f"扫描缓存目录失败: {e}")
            return

        total_size = sum(f.stat().st_size for f in files)
        if total_size <= max_bytes:
            return

        # 按修改时间排序，最旧的在前
        files.sort(key=lambda f: f.stat().st_mtime)

        deleted_count = 0
        in_use_since = time.time() - config.CHUNK_DURATION_SECONDS - 5
        for f in files:
            if total_size <= max_bytes:
                break
            try:
                if f.resolve() in protected or f.stat().st_mtime >= in_use_since:
                    continue
                size = f.stat().st_size
                f.unlink()
                total_size -= size
                deleted_count += 1
                logger.debug(f"缓存清理: 删除 {f.name} ({size / 1024 / 1024:.1f}MB)")
            except Exception as e:
                logger.warning(f"缓存清理失败 {f.name}: {e}")

        if deleted_count > 0:
            logger.info(f"缓存清理完成: 删除 {deleted_count} 个文件，当前大小 {total_size / 1024 / 1024:.0f}MB")
    
    async def process_immediately(self):
        if self.is_running:
            return
        with analysis_worker_lock(self.storage.db_path) as acquired:
            if acquired:
                self.storage.recover_interrupted_analysis()
                try:
                    await self._scan_and_process()
                finally:
                    await self._close_provider()


class AnalysisManager:
    """
    分析管理器
    管理后台分析调度器生命周期
    """
    
    def __init__(self, storage: Optional[StorageManager] = None):
        self.storage = storage or StorageManager()
        self.scheduler = AnalysisScheduler(storage=self.storage)
    
    def start_scheduler(self):
        """启动自动调度"""
        self.scheduler.start()
    
    def stop_scheduler(self, deadline: Optional[float] = None):
        """停止自动调度"""
        return self.scheduler.stop(deadline=deadline)
    
    @property
    def is_running(self) -> bool:
        return self.scheduler.is_running
