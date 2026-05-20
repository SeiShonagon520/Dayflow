"""
Dayflow Windows - 分析调度器
批量处理视频切片，调用 API 生成时间轴卡片
"""
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

import config
from core.types import (
    VideoChunk, ChunkStatus,
    AnalysisBatch, BatchStatus,
    Observation, ActivityCard
)
from core.llm_provider import DayflowBackendProvider
from database.storage import StorageManager

logger = logging.getLogger(__name__)


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
        scan_interval_seconds: int = None
    ):
        self.storage = storage or StorageManager()
        self.provider = provider or DayflowBackendProvider()
        self.batch_duration = batch_duration_minutes or config.BATCH_DURATION_MINUTES
        self.scan_interval = scan_interval_seconds or config.ANALYSIS_INTERVAL_SECONDS
        
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 事件循环（用于异步 API 调用）
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("调度器已在运行")
            return
        
        logger.info("启动分析调度器...")
        
        self._running = True
        self._stop_event.clear()
        
        # 创建新的事件循环
        self._loop = asyncio.new_event_loop()
        
        # 启动调度线程
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        logger.info(f"调度器已启动 - 扫描间隔: {self.scan_interval}秒, 批次时长: {self.batch_duration}分钟")
    
    def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        logger.info("停止分析调度器...")
        
        self._stop_event.set()
        self._running = False
        
        # 使用较短的超时时间，避免阻塞太久
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=2)
            if self._scheduler_thread.is_alive():
                logger.warning("调度器线程未能在超时内停止")
        
        # 安全关闭事件循环
        if self._loop:
            try:
                if self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)
                if not self._loop.is_closed():
                    self._loop.close()
            except Exception as e:
                logger.warning(f"关闭事件循环时出错: {e}")
            self._loop = None
        
        logger.info("调度器已停止")
    
    def _scheduler_loop(self):
        """调度主循环"""
        asyncio.set_event_loop(self._loop)
        
        while not self._stop_event.is_set():
            try:
                # 扫描并处理
                self._loop.run_until_complete(self._scan_and_process())
            except Exception as e:
                logger.error(f"调度循环错误: {e}")
            
            # 等待下一次扫描
            self._stop_event.wait(self.scan_interval)
    
    async def _scan_and_process(self):
        """扫描并处理待分析的切片"""
        # 获取待分析的切片
        pending_chunks = self.storage.get_pending_chunks()
        
        if not pending_chunks:
            logger.debug("没有待分析的切片")
            return
        
        logger.info(f"发现 {len(pending_chunks)} 个待分析切片")
        
        # 将切片打包成批次
        batches = self._create_batches(pending_chunks)
        
        for batch_chunks in batches:
            if self._stop_event.is_set():
                break
            
            try:
                await self._process_batch(batch_chunks)
            except Exception as e:
                logger.error(f"处理批次失败: {e}")
    
    def _create_batches(self, chunks: List[VideoChunk]) -> List[List[VideoChunk]]:
        """将切片分组为批次"""
        if not chunks:
            return []
        
        batches = []
        current_batch = []
        batch_duration = 0
        max_duration = self.batch_duration * 60  # 转换为秒
        
        for chunk in chunks:
            if batch_duration + chunk.duration_seconds > max_duration and current_batch:
                batches.append(current_batch)
                current_batch = []
                batch_duration = 0
            
            current_batch.append(chunk)
            batch_duration += chunk.duration_seconds
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    async def _process_batch(self, chunks: List[VideoChunk]):
        """处理单个批次"""
        if not chunks:
            return
        
        # 创建批次记录
        batch = AnalysisBatch(
            chunk_ids=[c.id for c in chunks if c.id],
            start_time=chunks[0].start_time,
            end_time=chunks[-1].end_time,
            status=BatchStatus.PENDING
        )
        batch_id = self.storage.create_batch(batch)
        
        # 更新切片状态
        for chunk in chunks:
            if chunk.id:
                self.storage.update_chunk_status(chunk.id, ChunkStatus.PROCESSING, batch_id)
        
        try:
            # 更新批次状态为处理中
            self.storage.update_batch(batch_id, BatchStatus.PROCESSING)
            
            # 转录所有切片
            all_observations = []
            for chunk in chunks:
                if not Path(chunk.file_path).exists():
                    logger.warning(f"切片文件不存在: {chunk.file_path}")
                    continue
                
                # 读取窗口记录
                window_records = None
                if chunk.window_records_path:
                    window_records_file = Path(chunk.window_records_path)
                    if window_records_file.exists():
                        try:
                            import json
                            with open(window_records_file, 'r', encoding='utf-8') as f:
                                window_records = json.load(f)
                            logger.debug(f"已加载 {len(window_records)} 条窗口记录")
                        except Exception as e:
                            logger.warning(f"读取窗口记录失败: {e}")
                
                observations = await self.provider.transcribe_video(
                    chunk.file_path,
                    chunk.duration_seconds,
                    window_records=window_records
                )
                
                # 调整时间戳（相对于批次开始时间）
                if chunk.start_time and batch.start_time:
                    offset = (chunk.start_time - batch.start_time).total_seconds()
                    for obs in observations:
                        obs.start_ts += offset
                        obs.end_ts += offset
                
                all_observations.extend(observations)
            
            if not all_observations:
                logger.warning(f"批次 {batch_id} 没有生成任何观察记录")
                self.storage.update_batch(batch_id, BatchStatus.COMPLETED, "[]")
                return
            
            # 获取上下文（最近的卡片）
            context_cards = self.storage.get_recent_cards(limit=5)
            
            # 生成活动卡片
            cards = await self.provider.generate_activity_cards(
                all_observations,
                context_cards,
                start_time=batch.start_time
            )
            
            # 保存卡片
            for card in cards:
                # 将相对时间转换为绝对时间
                if batch.start_time:
                    if card.start_time is None and hasattr(card, '_relative_start'):
                        card.start_time = batch.start_time + timedelta(seconds=card._relative_start)
                    if card.end_time is None and hasattr(card, '_relative_end'):
                        card.end_time = batch.start_time + timedelta(seconds=card._relative_end)
                
                self.storage.save_card(card, batch_id)
            
            # 更新状态
            import json
            observations_json = json.dumps([o.to_dict() for o in all_observations])
            self.storage.update_batch(batch_id, BatchStatus.COMPLETED, observations_json)
            
            for chunk in chunks:
                if chunk.id:
                    self.storage.update_chunk_status(chunk.id, ChunkStatus.COMPLETED)
            
            logger.info(f"批次 {batch_id} 处理完成 - 生成 {len(cards)} 张卡片")
            
            # 分析完成后删除视频切片文件（节省磁盘空间）
            if config.AUTO_DELETE_ANALYZED_CHUNKS:
                self._delete_chunk_files(chunks)

            # 基于大小的缓存清理
            self._cleanup_if_over_limit()
            
        except Exception as e:
            logger.error(f"批次 {batch_id} 处理失败: {e}")
            
            self.storage.update_batch(batch_id, BatchStatus.FAILED, error_message=str(e))
            
            for chunk in chunks:
                if chunk.id:
                    self.storage.update_chunk_status(chunk.id, ChunkStatus.FAILED)
            
            raise
    
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
            files = [f for f in chunks_dir.iterdir() if f.is_file()]
        except Exception as e:
            logger.warning(f"扫描缓存目录失败: {e}")
            return

        total_size = sum(f.stat().st_size for f in files)
        if total_size <= max_bytes:
            return

        # 按修改时间排序，最旧的在前
        files.sort(key=lambda f: f.stat().st_size)
        files.sort(key=lambda f: f.stat().st_mtime)

        deleted_count = 0
        for f in files:
            if total_size <= max_bytes:
                break
            try:
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
        """立即处理所有待分析的切片（手动触发）"""
        await self._scan_and_process()


class AnalysisManager:
    """
    分析管理器
    整合调度器和手动触发功能
    """
    
    def __init__(self, storage: Optional[StorageManager] = None):
        self.storage = storage or StorageManager()
        self.scheduler = AnalysisScheduler(storage=self.storage)
    
    def start_scheduler(self):
        """启动自动调度"""
        self.scheduler.start()
    
    def stop_scheduler(self):
        """停止自动调度"""
        self.scheduler.stop()
    
    def analyze_now(self):
        """立即分析（同步）"""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.scheduler.process_immediately())
        finally:
            loop.close()
    
    @property
    def is_running(self) -> bool:
        return self.scheduler.is_running
