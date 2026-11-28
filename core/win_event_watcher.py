"""
Win32 SetWinEventHook 事件监听器。

设计要点：
- 两个独立的 WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS 钩子分别订阅
  EVENT_SYSTEM_FOREGROUND (0x0003) 与 EVENT_OBJECT_NAMECHANGE (0x800C)。
- 显式声明 64 位 Win32 ctypes 函数签名并在实例上持有回调强引用，防止 GC 崩溃。
- 消息泵线程先调用 PeekMessageW 建队列后再置 ready，处理 GetMessageW 的 0 与 -1，
  在安装线程 finally 中逐个 UnhookWinEvent。
- 有界顺序队列保存每次事件的 target hwnd、事件时标题快照、单调/墙钟时间、
  nav_token 和基于 dwmsEventTime 的投递延迟检查；溢出/钩子重建/投递超限一律标记
  boundary_uncertain，确保不会吞掉 A -> 敏感窗口 -> A 或 正常 -> 敏感 -> 正常 的边界。
"""
from __future__ import annotations

from collections import deque
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
import logging
import os
import threading
import time
from typing import Deque, List, Optional

logger = logging.getLogger(__name__)

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_NAMECHANGE = 0x800C
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
OBJID_WINDOW = 0
CHILDID_SELF = 0
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000

DEFAULT_QUEUE_MAXLEN = 64
DEFAULT_DELIVERY_LAG_MS = 250


@dataclass(frozen=True)
class WinEventItem:
    kind: str  # "foreground" | "namechange" | "boundary_uncertain"
    hwnd: int
    event_mono: float
    event_wall: datetime
    event_seq: int
    nav_token: int
    title_snapshot: str = ""
    delivery_lag_ms: int = 0
    boundary_uncertain: bool = False


def compute_tick_lag_ms(current_tick_32: int, event_time_ms: int) -> int:
    """计算 32 位 GetTickCount 与 dwmsEventTime 之间的无符号回环延迟（毫秒）。"""
    return (int(current_tick_32) - int(event_time_ms)) & 0xFFFFFFFF


class WinEventWatcher:
    """Win32 前台与窗口标题变更监听器；不可用时记录明确降级状态，由调用方退回 1s 点采样。"""

    def __init__(
        self,
        *,
        queue_maxlen: int = DEFAULT_QUEUE_MAXLEN,
        delivery_lag_ms: int = DEFAULT_DELIVERY_LAG_MS,
    ):
        self._queue_maxlen = max(8, int(queue_maxlen))
        self._delivery_lag_ms = max(50, int(delivery_lag_ms))
        self._lock = threading.Lock()
        self._queue: Deque[WinEventItem] = deque()
        self._wake = threading.Event()
        self._ready = threading.Event()
        self._event_seq = 0
        self._nav_token = 0
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._hook_active = False
        self._degraded_reason: Optional[str] = None
        self._callback_ref = None
        self._stop_requested = False

    @property
    def is_hook_active(self) -> bool:
        return self._hook_active

    @property
    def degraded_reason(self) -> Optional[str]:
        return self._degraded_reason

    @property
    def nav_token(self) -> int:
        with self._lock:
            return self._nav_token

    def bump_nav_token(self) -> int:
        with self._lock:
            self._nav_token += 1
            return self._nav_token

    def wait(self, timeout: float) -> bool:
        triggered = self._wake.wait(timeout=timeout)
        self._wake.clear()
        return triggered

    def drain(self) -> List[WinEventItem]:
        with self._lock:
            if not self._queue:
                return []
            items = list(self._queue)
            self._queue.clear()
            return items

    def push_synthetic_event(
        self,
        *,
        kind: str,
        hwnd: int,
        title_snapshot: str = "",
        event_mono: Optional[float] = None,
        event_wall: Optional[datetime] = None,
        delivery_lag_ms: int = 0,
        boundary_uncertain: bool = False,
    ) -> WinEventItem:
        """供测试或故障注入推入事件，复用与真实 WinEvent 完全相同的队列与溢出逻辑。"""
        now_mono = time.monotonic() if event_mono is None else event_mono
        now_wall = datetime.now() if event_wall is None else event_wall
        lagged = delivery_lag_ms > self._delivery_lag_ms
        uncertain = bool(boundary_uncertain or lagged)
        with self._lock:
            self._event_seq += 1
            self._nav_token += 1
            if len(self._queue) >= self._queue_maxlen:
                # 队列溢出：清空不可验证的积压，发出明确 boundary_uncertain 并作废在途 nav_token
                self._queue.clear()
                self._nav_token += 1
                item = WinEventItem(
                    kind="boundary_uncertain",
                    hwnd=0,
                    event_mono=now_mono,
                    event_wall=now_wall,
                    event_seq=self._event_seq,
                    nav_token=self._nav_token,
                    title_snapshot="",
                    delivery_lag_ms=delivery_lag_ms,
                    boundary_uncertain=True,
                )
                self._queue.append(item)
            else:
                item = WinEventItem(
                    kind="boundary_uncertain" if uncertain else kind,
                    hwnd=int(hwnd),
                    event_mono=now_mono,
                    event_wall=now_wall,
                    event_seq=self._event_seq,
                    nav_token=self._nav_token,
                    title_snapshot=title_snapshot,
                    delivery_lag_ms=delivery_lag_ms,
                    boundary_uncertain=uncertain,
                )
                self._queue.append(item)
        self._wake.set()
        return item

    def start(self) -> bool:
        """启动消息泵线程并安装两个 WinEvent 钩子；失败时自动清理并返回 False（降级为 1s 轮询）。"""
        if os.name != "nt":
            self._degraded_reason = "非 Windows 平台，降级为 1 秒采样点轮询"
            return False
        if self._thread and self._thread.is_alive():
            return self._hook_active
        self._stop_requested = False
        self._ready.clear()
        self._hook_active = False
        self._degraded_reason = None
        self._thread = threading.Thread(target=self._run_pump, daemon=True, name="WinEventWatcher")
        self._thread.start()
        self._ready.wait(timeout=2.0)
        if not self._hook_active and not self._degraded_reason:
            self._degraded_reason = "WinEvent 消息线程初始化超时，降级为 1 秒采样点轮询"
        return self._hook_active

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_requested = True
        tid = self._thread_id
        if os.name == "nt" and tid:
            try:
                user32 = ctypes.windll.user32
                user32.PostThreadMessageW.argtypes = [
                    wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
                ]
                user32.PostThreadMessageW.restype = wintypes.BOOL
                user32.PostThreadMessageW(wintypes.DWORD(tid), WM_QUIT, 0, 0)
            except Exception as exc:
                logger.debug("发送 WM_QUIT 失败: %s", exc)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        self._thread_id = None
        self._hook_active = False
        self._callback_ref = None
        self._wake.set()

    def _run_pump(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        HWINEVENTHOOK = wintypes.HANDLE
        WINEVENTPROC = ctypes.WINFUNCTYPE(
            None,
            HWINEVENTHOOK,
            wintypes.DWORD,
            wintypes.HWND,
            wintypes.LONG,
            wintypes.LONG,
            wintypes.DWORD,
            wintypes.DWORD,
        )

        user32.SetWinEventHook.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HMODULE,
            WINEVENTPROC,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        user32.SetWinEventHook.restype = HWINEVENTHOOK

        user32.UnhookWinEvent.argtypes = [HWINEVENTHOOK]
        user32.UnhookWinEvent.restype = wintypes.BOOL

        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND

        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int

        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int

        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT
        ]
        user32.PeekMessageW.restype = wintypes.BOOL

        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
        ]
        user32.GetMessageW.restype = ctypes.c_int

        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        kernel32.GetTickCount.argtypes = []
        kernel32.GetTickCount.restype = wintypes.DWORD

        def _read_title_fast(hwnd_val: int) -> str:
            if not hwnd_val:
                return ""
            length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd_val))
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(min(length, 512) + 1)
            user32.GetWindowTextW(wintypes.HWND(hwnd_val), buf, len(buf))
            return buf.value

        def _on_win_event(hook, event, hwnd, id_object, id_child, event_thread, event_time):
            try:
                hwnd_int = int(hwnd or 0)
                if event == EVENT_OBJECT_NAMECHANGE:
                    if id_object != OBJID_WINDOW or id_child != CHILDID_SELF or not hwnd_int:
                        return
                    fg = int(user32.GetForegroundWindow() or 0)
                    if hwnd_int != fg:
                        return
                    kind = "namechange"
                elif event == EVENT_SYSTEM_FOREGROUND:
                    kind = "foreground"
                else:
                    return

                tick_now = int(kernel32.GetTickCount())
                lag_ms = compute_tick_lag_ms(tick_now, int(event_time))
                title_snap = _read_title_fast(hwnd_int) if hwnd_int else ""
                self.push_synthetic_event(
                    kind=kind,
                    hwnd=hwnd_int,
                    title_snapshot=title_snap,
                    delivery_lag_ms=lag_ms,
                )
            except Exception:
                # 回调绝不抛出到 Win32 消息循环
                pass

        self._callback_ref = WINEVENTPROC(_on_win_event)
        hooks = []
        try:
            self._thread_id = int(kernel32.GetCurrentThreadId())
            # 先调用 PeekMessageW 创建本线程 Win32 消息队列，再置 ready
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)

            flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
            for ev in (EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_NAMECHANGE):
                h = user32.SetWinEventHook(ev, ev, None, self._callback_ref, 0, 0, flags)
                if not h:
                    raise OSError(f"SetWinEventHook 失败 (event=0x{ev:04X})")
                hooks.append(h)

            self._hook_active = True
            self.bump_nav_token()
            self._ready.set()

            while not self._stop_requested:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0:
                    # WM_QUIT
                    break
                if ret == -1:
                    logger.warning("WinEvent GetMessageW 返回 -1，退出消息泵并降级为轮询")
                    self._degraded_reason = "WinEvent 消息循环异常，已降级为 1 秒采样点轮询"
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self._degraded_reason = f"SetWinEventHook 不可用（{type(exc).__name__}），降级为 1 秒采样点轮询"
            logger.warning("%s", self._degraded_reason)
            self._hook_active = False
            self._ready.set()
        finally:
            for h in hooks:
                try:
                    user32.UnhookWinEvent(h)
                except Exception:
                    pass
            self._hook_active = False
            self._ready.set()
