"""
Dayflow Windows - 用户空闲检测模块
使用 Windows GetLastInputInfo API 检测键盘/鼠标输入空闲时间
"""
import logging
import threading
import time
from ctypes import Structure, c_uint, sizeof, byref, windll
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class LASTINPUTINFO(Structure):
    _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]


class IdleDetector:
    """
    用户空闲检测器
    基于 Windows GetLastInputInfo API，轻量、无需全局钩子
    """

    def __init__(
        self,
        timeout_seconds: int = 600,
        check_interval: int = 5,
        on_idle: Optional[Callable[[], None]] = None,
        on_active: Optional[Callable[[], None]] = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.check_interval = check_interval
        self.on_idle = on_idle
        self.on_active = on_active

        self._running = False
        self._is_idle = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def is_idle(self) -> bool:
        return self._is_idle

    def start(self):
        """启动空闲检测"""
        if self._running:
            return

        self._running = True
        self._is_idle = False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"空闲检测已启动 - 超时: {self.timeout_seconds}秒, 检查间隔: {self.check_interval}秒")

    def stop(self):
        """停止空闲检测"""
        if not self._running:
            return

        self._stop_event.set()
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        self._is_idle = False
        logger.info("空闲检测已停止")

    def _get_idle_seconds(self) -> float:
        """获取当前空闲秒数"""
        lii = LASTINPUTINFO()
        lii.cbSize = sizeof(LASTINPUTINFO)
        if not windll.user32.GetLastInputInfo(byref(lii)):
            return 0.0

        tick_count = windll.kernel32.GetTickCount()
        idle_millis = tick_count - lii.dwTime
        return idle_millis / 1000.0

    def _loop(self):
        """检测主循环"""
        while not self._stop_event.is_set():
            try:
                idle_seconds = self._get_idle_seconds()

                if not self._is_idle and idle_seconds >= self.timeout_seconds:
                    self._is_idle = True
                    logger.info(f"检测到用户空闲 {idle_seconds:.0f} 秒，触发空闲回调")
                    if self.on_idle:
                        try:
                            self.on_idle()
                        except Exception as e:
                            logger.error(f"空闲回调错误: {e}")

                elif self._is_idle and idle_seconds < self.timeout_seconds:
                    self._is_idle = False
                    logger.info(f"检测到用户活动恢复，空闲 {idle_seconds:.0f} 秒")
                    if self.on_active:
                        try:
                            self.on_active()
                        except Exception as e:
                            logger.error(f"活动恢复回调错误: {e}")

            except Exception as e:
                logger.error(f"空闲检测循环错误: {e}")

            self._stop_event.wait(self.check_interval)
