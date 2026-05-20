"""
Dayflow Windows - 屏幕录制模块
使用 dxcam 实现低功耗 1FPS 录制
"""
import time
import logging
import threading
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List, Dict

import numpy as np
import dxcam
import cv2

import config
from core.types import VideoChunk, ChunkStatus
from core.window_tracker import get_tracker, WindowInfo

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
        on_chunk_saved: Optional[Callable[[VideoChunk], None]] = None,
        output_idx: int = 0,
    ):
        self.fps = fps or config.RECORD_FPS
        self.chunk_duration = chunk_duration or config.CHUNK_DURATION_SECONDS
        self.output_dir = output_dir or config.CHUNKS_DIR
        self.on_chunk_saved = on_chunk_saved
        self._all_screens = (output_idx == -1)
        self.output_idx = int(output_idx) if output_idx is not None else 0

        # 状态
        self._recording = False
        self._paused = False
        self._camera: Optional[dxcam.DXCamera] = None
        self._record_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 多相机模式（全部屏幕）
        self._cameras: list = []
        self._output_geometries: list = []
        self._canvas_shape: Optional[tuple] = None
        self._canvas_offset_x: int = 0
        self._canvas_offset_y: int = 0
        
        # 当前切片信息
        self._current_writer: Optional[cv2.VideoWriter] = None
        self._current_chunk_path: Optional[Path] = None
        self._current_chunk_start: Optional[datetime] = None
        self._frame_count = 0
        
        # 窗口追踪
        self._window_tracker = get_tracker()
        self._current_window_records: List[Dict] = []  # 当前切片的窗口记录
        
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

        if self._all_screens:
            logger.info("开始屏幕录制... (全部屏幕模式)")
            self._create_all_cameras()
        else:
            logger.info(f"开始屏幕录制... (显示器 output_idx={self.output_idx})")
            self._camera = self._create_camera_with_fallback()
        
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
        
        # 等待录制线程结束（缩短超时时间）
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=2)
            if self._record_thread.is_alive():
                logger.warning("录制线程未能在超时内停止")
        
        # 保存当前切片
        try:
            self._finalize_current_chunk()
        except Exception as e:
            logger.error(f"保存切片时出错: {e}")
        
        # 释放 dxcam
        try:
            if self._all_screens:
                for cam in self._cameras:
                    try:
                        del cam
                    except Exception as e:
                        logger.error(f"释放相机时出错: {e}")
                self._cameras = []
                self._output_geometries = []
                self._canvas_shape = None
            elif self._camera:
                del self._camera
                self._camera = None
        except Exception as e:
            logger.error(f"释放相机时出错: {e}")
        
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
    
    def _create_camera_with_fallback(self) -> dxcam.DXCamera:
        """创建 dxcam 相机，失败时尝试多种降级参数。"""
        attempts = [
            {"output_idx": self.output_idx, "output_color": "BGR"},
            {"output_idx": self.output_idx},
            {"device_idx": 0, "output_idx": self.output_idx, "output_color": "BGR"},
            {"device_idx": 0, "output_idx": self.output_idx},
            {},
        ]
        last_error = None

        for idx, kwargs in enumerate(attempts, start=1):
            try:
                logger.info(f"尝试初始化 dxcam ({idx}/{len(attempts)}): {kwargs}")
                camera = dxcam.create(**kwargs)
                # 部分环境 create 成功但首次 grab 才会炸，这里预抓一帧尽早暴露问题
                test_frame = camera.grab()
                if test_frame is None:
                    logger.warning("dxcam 初始化成功，但首次抓帧为空；继续使用并在录制循环中重试")
                logger.info("dxcam 初始化成功")
                return camera
            except Exception as e:
                last_error = e
                logger.warning(f"dxcam 初始化尝试失败 ({kwargs}): {e}")
                time.sleep(0.3)

        error_message = (
            "初始化屏幕录制失败。可能原因：显卡/显示器驱动异常、远程桌面环境、"
            "dxcam 与当前输出设备不兼容。建议重启应用、更新显卡驱动，或切换显示器后重试。"
        )
        logger.error(f"{error_message} 最后错误: {last_error}")
        raise RuntimeError(error_message) from last_error

    def _create_all_cameras(self):
        """为每个已连接的显示器创建 dxcam 相机，计算虚拟桌面画布。"""
        self._cameras = []
        self._output_geometries = []

        for output_idx in range(16):
            try:
                cam = dxcam.create(
                    device_idx=0,
                    output_idx=output_idx,
                    output_color="BGR",
                )
                output_obj = cam._output
                output_obj.update_desc()

                if not output_obj.attached_to_desktop:
                    del cam
                    continue

                coords = output_obj.desc.DesktopCoordinates
                geom = {
                    "output_idx": output_idx,
                    "left": coords.left,
                    "top": coords.top,
                    "width": output_obj.resolution[0],
                    "height": output_obj.resolution[1],
                }
                self._cameras.append(cam)
                self._output_geometries.append(geom)
                logger.info(
                    f"  显示器 {output_idx}: {geom['width']}x{geom['height']} "
                    f"at ({geom['left']}, {geom['top']})"
                )
            except Exception as e:
                logger.debug(f"枚举输出 {output_idx} 结束或失败: {e}")
                break

        if not self._cameras:
            raise RuntimeError("未找到任何可用的显示器输出")

        # 计算虚拟桌面边界框
        min_left = min(g["left"] for g in self._output_geometries)
        min_top = min(g["top"] for g in self._output_geometries)
        max_right = max(g["left"] + g["width"] for g in self._output_geometries)
        max_bottom = max(g["top"] + g["height"] for g in self._output_geometries)

        self._canvas_offset_x = min_left
        self._canvas_offset_y = min_top
        canvas_width = max_right - min_left
        canvas_height = max_bottom - min_top
        self._canvas_shape = (canvas_height, canvas_width, 3)

        logger.info(
            f"虚拟桌面: {canvas_width}x{canvas_height}, "
            f"偏移: ({min_left}, {min_top}), "
            f"显示器数: {len(self._cameras)}"
        )

    def _grab_all_screens(self) -> Optional[np.ndarray]:
        """从所有相机抓取帧并拼接到虚拟桌面画布。"""
        if not self._cameras or self._canvas_shape is None:
            return None

        canvas = np.zeros(self._canvas_shape, dtype=np.uint8)

        for cam, geom in zip(self._cameras, self._output_geometries):
            frame = cam.grab()
            if frame is None:
                continue

            x = geom["left"] - self._canvas_offset_x
            y = geom["top"] - self._canvas_offset_y
            h = geom["height"]
            w = geom["width"]

            fh, fw = frame.shape[:2]
            if fh != h or fw != w:
                frame = cv2.resize(frame, (w, h))

            canvas[y:y + h, x:x + w] = frame

        return canvas

    def _recording_loop(self):
        """录制主循环"""
        frame_interval = 1.0 / self.fps
        last_frame_time = 0
        last_window_info = None  # 缓存上次窗口信息
        
        while not self._stop_event.is_set():
            current_time = time.time()
            
            # 控制帧率 - 使用精确等待而非轮询
            time_to_wait = frame_interval - (current_time - last_frame_time)
            if time_to_wait > 0:
                self._stop_event.wait(min(time_to_wait, 0.5))  # 最多等待0.5秒，确保能响应停止信号
                continue
            
            # 暂停检查
            if self._paused:
                self._stop_event.wait(0.5)
                continue
            
            try:
                # 捕获屏幕
                if self._all_screens:
                    frame = self._grab_all_screens()
                else:
                    frame = self._camera.grab()
                if frame is None:
                    time.sleep(0.1)
                    continue
                
                # 先采集窗口信息（在帧捕获时立即采集，确保时间对齐）
                frame_capture_time = datetime.now()
                window_info = self._window_tracker.get_active_window()
                
                # 检查是否需要创建新切片
                if self._should_create_new_chunk():
                    self._finalize_current_chunk()
                    self._create_new_chunk(frame.shape)
                    last_window_info = None  # 重置窗口缓存
                
                # 记录窗口信息（仅在窗口变化时记录，减少数据量）
                if self._current_chunk_start and window_info:
                    # 检查窗口是否变化
                    window_changed = (
                        last_window_info is None or
                        last_window_info.app_name != window_info.app_name or
                        last_window_info.window_title != window_info.window_title
                    )
                    
                    if window_changed:
                        elapsed = (frame_capture_time - self._current_chunk_start).total_seconds()
                        self._current_window_records.append({
                            "timestamp": elapsed,
                            "app_name": self._window_tracker.get_friendly_app_name(window_info),
                            "window_title": window_info.window_title,
                            "process_name": window_info.app_name
                        })
                        last_window_info = window_info
                
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
        self._current_window_records = []  # 重置窗口记录
        
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
            
            # 保存窗口记录到 JSON 文件
            window_records_path = None
            if self._current_window_records:
                window_records_path = self._current_chunk_path.with_suffix('.json')
                try:
                    with open(window_records_path, 'w', encoding='utf-8') as f:
                        json.dump(self._current_window_records, f, ensure_ascii=False, indent=2)
                    logger.debug(f"窗口记录已保存: {window_records_path.name}")
                except Exception as e:
                    logger.warning(f"保存窗口记录失败: {e}")
                    window_records_path = None
            
            # 创建切片对象
            chunk = VideoChunk(
                file_path=str(self._current_chunk_path),
                start_time=self._current_chunk_start,
                end_time=end_time,
                duration_seconds=duration,
                status=ChunkStatus.PENDING,
                window_records_path=str(window_records_path) if window_records_path else None
            )
            
            logger.info(f"切片已保存: {self._current_chunk_path.name} ({duration:.1f}秒, {self._frame_count}帧, {len(self._current_window_records)}条窗口记录)")
            
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
        self._current_window_records = []


class RecordingManager:
    """
    录制管理器
    整合录制器和数据库存储，支持空闲自动暂停
    """

    def __init__(self, storage_manager=None):
        from database.storage import StorageManager
        self.storage = storage_manager or StorageManager()
        try:
            output_idx = int(self.storage.get_setting("record_output_idx", "0"))
        except Exception:
            output_idx = 0
        self.recorder = ScreenRecorder(on_chunk_saved=self._on_chunk_saved, output_idx=output_idx)

        self._idle_paused = False
        self._idle_detector = None

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
        self._start_idle_detector()

    def stop_recording(self):
        """停止录制"""
        self._stop_idle_detector()
        self.recorder.stop()

    def pause_recording(self):
        """暂停录制（手动）"""
        self._idle_paused = False
        self.recorder.pause()

    def resume_recording(self):
        """恢复录制（手动）"""
        self._idle_paused = False
        self.recorder.resume()

    @property
    def is_recording(self) -> bool:
        return self.recorder.is_recording

    @property
    def is_paused(self) -> bool:
        return self.recorder.is_paused

    @property
    def is_idle_paused(self) -> bool:
        return self._idle_paused

    def _start_idle_detector(self):
        """启动空闲检测"""
        if not config.IDLE_PAUSE_ENABLED:
            return

        try:
            from core.idle_detector import IdleDetector
            timeout = config.IDLE_PAUSE_TIMEOUT_SECONDS
            self._idle_detector = IdleDetector(
                timeout_seconds=timeout,
                check_interval=5,
                on_idle=self._on_idle,
                on_active=self._on_active
            )
            self._idle_detector.start()
        except Exception as e:
            logger.warning(f"空闲检测启动失败: {e}")

    def _stop_idle_detector(self):
        """停止空闲检测"""
        if self._idle_detector:
            try:
                self._idle_detector.stop()
            except Exception as e:
                logger.warning(f"空闲检测停止失败: {e}")
            self._idle_detector = None
        self._idle_paused = False

    def _on_idle(self):
        """空闲回调 - 自动暂停录制"""
        if self.recorder.is_recording and not self.recorder.is_paused:
            self.recorder.pause()
            self._idle_paused = True
            logger.info(f"检测到空闲 {config.IDLE_PAUSE_TIMEOUT_SECONDS} 秒，录制已自动暂停")

    def _on_active(self):
        """活动恢复回调 - 自动恢复录制"""
        if self._idle_paused:
            self.recorder.resume()
            self._idle_paused = False
            logger.info("检测到活动恢复，录制已自动恢复")
