"""
Dayflow Windows - 屏幕录制模块
使用 dxcam 实现低功耗 1FPS 录制
"""
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
from queue import Queue, Empty

import dxcam
import numpy as np
import cv2

import config
from core.types import VideoChunk, ChunkStatus

logger = logging.getLogger(__name__)


class ScreenRecorder:
    """
    屏幕录制器
    - 1 FPS 低功耗录制
    - 每 60 秒自动切片
    - H.264 编码，低码率
    """
    
    def __init__(
        self,
        fps: int = None,
        chunk_duration: int = None,
        output_dir: Path = None,
        on_chunk_saved: Optional[Callable[[VideoChunk], None]] = None
    ):
        self.fps = fps or config.RECORD_FPS
        self.chunk_duration = chunk_duration or config.CHUNK_DURATION_SECONDS
        self.output_dir = output_dir or config.CHUNKS_DIR
        self.on_chunk_saved = on_chunk_saved
        
        # 状态
        self._recording = False
        self._paused = False
        self._camera: Optional[dxcam.DXCamera] = None
        self._record_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 当前切片信息
        self._current_writer: Optional[cv2.VideoWriter] = None
        self._current_chunk_path: Optional[Path] = None
        self._current_chunk_start: Optional[datetime] = None
        self._frame_count = 0
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_recording(self) -> bool:
        return self._recording
    
    @property
    def is_paused(self) -> bool:
        return self._paused
    
    def start(self):
        """开始录制"""
        if self._recording:
            logger.warning("录制已在进行中")
            return
        
        logger.info("开始屏幕录制...")
        
        # 初始化 dxcam
        try:
            self._camera = dxcam.create(output_idx=0, output_color="BGR")
        except Exception as e:
            logger.error(f"初始化 dxcam 失败: {e}")
            raise
        
        self._recording = True
        self._paused = False
        self._stop_event.clear()
        
        # 启动录制线程
        self._record_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self._record_thread.start()
        
        logger.info(f"录制已启动 - FPS: {self.fps}, 切片时长: {self.chunk_duration}秒")
    
    def stop(self):
        """停止录制"""
        if not self._recording:
            return
        
        logger.info("停止屏幕录制...")
        
        self._stop_event.set()
        self._recording = False
        
        # 等待录制线程结束
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=5)
        
        # 保存当前切片
        self._finalize_current_chunk()
        
        # 释放 dxcam
        if self._camera:
            del self._camera
            self._camera = None
        
        logger.info("录制已停止")
    
    def pause(self):
        """暂停录制"""
        if self._recording and not self._paused:
            self._paused = True
            logger.info("录制已暂停")
    
    def resume(self):
        """恢复录制"""
        if self._recording and self._paused:
            self._paused = False
            logger.info("录制已恢复")
    
    def _recording_loop(self):
        """录制主循环"""
        frame_interval = 1.0 / self.fps
        last_frame_time = 0
        
        while not self._stop_event.is_set():
            current_time = time.time()
            
            # 控制帧率
            if current_time - last_frame_time < frame_interval:
                time.sleep(0.1)  # 短暂休眠以降低 CPU 占用
                continue
            
            # 暂停检查
            if self._paused:
                time.sleep(0.5)
                continue
            
            try:
                # 捕获屏幕
                frame = self._camera.grab()
                if frame is None:
                    time.sleep(0.1)
                    continue
                
                # 检查是否需要创建新切片
                if self._should_create_new_chunk():
                    self._finalize_current_chunk()
                    self._create_new_chunk(frame.shape)
                
                # 写入帧
                if self._current_writer:
                    self._current_writer.write(frame)
                    self._frame_count += 1
                
                last_frame_time = current_time
                
            except Exception as e:
                logger.error(f"录制帧错误: {e}")
                time.sleep(1)
    
    def _should_create_new_chunk(self) -> bool:
        """检查是否需要创建新切片"""
        if self._current_chunk_start is None:
            return True
        
        elapsed = (datetime.now() - self._current_chunk_start).total_seconds()
        return elapsed >= self.chunk_duration
    
    def _create_new_chunk(self, frame_shape: tuple):
        """创建新的视频切片"""
        timestamp = datetime.now()
        filename = f"chunk_{timestamp.strftime('%Y%m%d_%H%M%S')}.mp4"
        self._current_chunk_path = self.output_dir / filename
        self._current_chunk_start = timestamp
        self._frame_count = 0
        
        # 创建 VideoWriter
        height, width = frame_shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        self._current_writer = cv2.VideoWriter(
            str(self._current_chunk_path),
            fourcc,
            self.fps,
            (width, height)
        )
        
        logger.debug(f"创建新切片: {filename}")
    
    def _finalize_current_chunk(self):
        """完成当前切片"""
        if self._current_writer is None:
            return
        
        self._current_writer.release()
        
        if self._current_chunk_path and self._current_chunk_path.exists():
            end_time = datetime.now()
            duration = (end_time - self._current_chunk_start).total_seconds()
            
            # 创建切片对象
            chunk = VideoChunk(
                file_path=str(self._current_chunk_path),
                start_time=self._current_chunk_start,
                end_time=end_time,
                duration_seconds=duration,
                status=ChunkStatus.PENDING
            )
            
            logger.info(f"切片已保存: {self._current_chunk_path.name} ({duration:.1f}秒, {self._frame_count}帧)")
            
            # 回调通知
            if self.on_chunk_saved:
                try:
                    self.on_chunk_saved(chunk)
                except Exception as e:
                    logger.error(f"切片保存回调错误: {e}")
        
        self._current_writer = None
        self._current_chunk_path = None
        self._current_chunk_start = None
        self._frame_count = 0


class RecordingManager:
    """
    录制管理器
    整合录制器和数据库存储
    """
    
    def __init__(self, storage_manager=None):
        from database.storage import StorageManager
        self.storage = storage_manager or StorageManager()
        self.recorder = ScreenRecorder(on_chunk_saved=self._on_chunk_saved)
    
    def _on_chunk_saved(self, chunk: VideoChunk):
        """切片保存回调 - 写入数据库"""
        try:
            chunk_id = self.storage.save_chunk(chunk)
            logger.info(f"切片已入库: ID={chunk_id}")
        except Exception as e:
            logger.error(f"切片入库失败: {e}")
    
    def start_recording(self):
        """开始录制"""
        self.recorder.start()
    
    def stop_recording(self):
        """停止录制"""
        self.recorder.stop()
    
    def pause_recording(self):
        """暂停录制"""
        self.recorder.pause()
    
    def resume_recording(self):
        """恢复录制"""
        self.recorder.resume()
    
    @property
    def is_recording(self) -> bool:
        return self.recorder.is_recording
    
    @property
    def is_paused(self) -> bool:
        return self.recorder.is_paused
