"""
独立可回收的 MTA Windows UI Automation 工作进程。

设计要点：
- 子进程入口在首次 import comtypes 之前显式设置 sys.coinit_flags = 0 (COINIT_MULTITHREADED)，
  避免 comtypes 默认初始化 STA 导致死锁。
- 仅运行在受支持的浏览器（chrome / msedge / firefox）已确认非私密的窗口上。
- 浅层受限遍历（显式跳过 Document / WebArea，最大深度 8、最大节点 80）寻找唯一地址栏 Edit 控件；
  控件聚焦编辑中、存在联想弹窗或匹配数量 != 1 时回退。
- 双端夹逼校验：读取前后核对前台 hwnd、(pid, create_time)、窗口标题与地址文本一致且未聚焦。
- 父进程设 150ms 硬超时预算，超时即冷却该 hwnd 并强杀/重建卡死子进程；关闭时确保零残留进程。
"""
from __future__ import annotations

import logging
import multiprocessing
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# UIA ControlType IDs
UIA_EDIT_CONTROL_TYPE = 50004
UIA_DOCUMENT_CONTROL_TYPE = 50030
UIA_PANE_CONTROL_TYPE = 50033
UIA_TOOLBAR_CONTROL_TYPE = 50021
UIA_GROUP_CONTROL_TYPE = 50026
UIA_CUSTOM_CONTROL_TYPE = 50025
UIA_COMBOBOX_CONTROL_TYPE = 50003
UIA_LIST_CONTROL_TYPE = 50008
UIA_POPUP_TYPES = {UIA_LIST_CONTROL_TYPE}
UIA_CONTAINER_TYPES = {
    UIA_PANE_CONTROL_TYPE,
    UIA_TOOLBAR_CONTROL_TYPE,
    UIA_GROUP_CONTROL_TYPE,
    UIA_CUSTOM_CONTROL_TYPE,
    UIA_COMBOBOX_CONTROL_TYPE,
}
UIA_VALUE_PATTERN_ID = 10002

SUPPORTED_BROWSERS = {"chrome", "msedge", "firefox"}

_ADDRESS_NAME_HINTS = (
    "address and search bar",
    "address bar",
    "地址和搜索栏",
    "地址栏",
    "search or enter address",
    "搜索或输入网址",
    "使用",
)
_ADDRESS_AUTOMATION_IDS = {
    "chrome": {"view_1012", "omniboxviewviews"},
    "msedge": {"view_1022", "omniboxviewviews"},
    "firefox": {"urlbar-input"},
}


def ensure_uia_bindings(gen_dir: Optional[Path] = None):
    """加载预生成或运行时生成的 UIAutomationCore 类型库绑定。"""
    import comtypes
    import comtypes.client

    try:
        from comtypes.gen import UIAutomationClient  # type: ignore
        return UIAutomationClient
    except ImportError:
        pass

    if gen_dir is not None:
        gen_dir.mkdir(parents=True, exist_ok=True)
        comtypes.client.gen_dir = str(gen_dir)
    return comtypes.client.GetModule("UIAutomationCore.dll")


def _looks_like_address_bar(browser: str, name: str, automation_id: str) -> bool:
    aid = (automation_id or "").strip().lower()
    if aid and aid in _ADDRESS_AUTOMATION_IDS.get(browser, set()):
        return True
    lowered = (name or "").strip().lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in _ADDRESS_NAME_HINTS)


def _find_unique_address_bar(uia, root, browser: str, *, max_depth: int = 8, max_nodes: int = 80):
    """浅层受限 BFS，显式跳过 Document / WebArea，返回 (element, popup_detected, ambiguous)。"""
    walker = uia.ControlViewWalker
    matches = []
    popup_detected = False
    visited = 0
    queue = [(root, 0)]

    while queue and visited < max_nodes:
        elem, depth = queue.pop(0)
        if depth > max_depth:
            continue
        try:
            child = walker.GetFirstChildElement(elem)
        except Exception:
            continue

        while child is not None and visited < max_nodes:
            visited += 1
            try:
                ctype = int(child.CurrentControlType)
            except Exception:
                ctype = 0

            if ctype == UIA_DOCUMENT_CONTROL_TYPE:
                # 绝不进入 Web DOM 子树
                pass
            elif ctype == UIA_EDIT_CONTROL_TYPE:
                try:
                    name = child.CurrentName or ""
                    aid = child.CurrentAutomationId or ""
                except Exception:
                    name, aid = "", ""
                if _looks_like_address_bar(browser, name, aid):
                    matches.append(child)
                    if len(matches) > 1:
                        return None, popup_detected, True
            elif ctype in UIA_POPUP_TYPES:
                try:
                    name = (child.CurrentName or "").lower()
                    if "omnibox" in name or "popup" in name or "建议" in name or "search" in name:
                        popup_detected = True
                except Exception:
                    pass
            elif ctype in UIA_CONTAINER_TYPES and depth < max_depth:
                queue.append((child, depth + 1))

            try:
                child = walker.GetNextSiblingElement(child)
            except Exception:
                break

    if len(matches) == 1:
        return matches[0], popup_detected, False
    return None, popup_detected, len(matches) > 1


def _read_value_pattern(mod, elem) -> Optional[str]:
    try:
        raw = elem.GetCurrentPattern(UIA_VALUE_PATTERN_ID)
        if not raw:
            return None
        vp = raw.QueryInterface(mod.IUIAutomationValuePattern)
        val = vp.CurrentValue
        return str(val) if val is not None else None
    except Exception:
        return None


def _verify_hwnd_identity(hwnd: int, expected_pid: int, expected_create_time: float, expected_title: str) -> bool:
    import psutil
    import win32gui
    import win32process

    fg = int(win32gui.GetForegroundWindow() or 0)
    if fg != hwnd:
        return False
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if int(pid) != int(expected_pid):
        return False
    try:
        ctime = float(psutil.Process(pid).create_time())
    except Exception:
        return False
    if expected_create_time > 0 and abs(ctime - expected_create_time) > 0.05:
        return False
    if expected_title and win32gui.GetWindowText(hwnd) != expected_title:
        return False
    return True


def _worker_main(conn, gen_dir_str: str) -> None:
    """独立子进程主循环：在首次 import comtypes 之前强制设置 MTA 模式。"""
    # 必须在 import comtypes 之前设置 COINIT_MULTITHREADED (0)
    sys.coinit_flags = 0
    com_initialized = False
    uia = None
    mod = None
    try:
        import comtypes
        import comtypes.client

        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        com_initialized = True
        mod = ensure_uia_bindings(Path(gen_dir_str) if gen_dir_str else None)
        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=mod.IUIAutomation,
        )
        # 若系统支持 IUIAutomation2，设置 120ms 事务超时作为辅助退避
        try:
            uia2 = uia.QueryInterface(mod.IUIAutomation2)
            uia2.TransactionTimeout = 120
            uia2.ConnectionTimeout = 120
        except Exception:
            pass

        conn.send({"ready": True})
        while True:
            try:
                req = conn.recv()
            except (EOFError, OSError):
                break
            if not isinstance(req, dict) or req.get("cmd") == "shutdown":
                break

            req_id = req.get("req_id")
            hwnd = int(req.get("hwnd") or 0)
            browser = str(req.get("browser") or "")
            pid = int(req.get("pid") or 0)
            ctime = float(req.get("create_time") or 0.0)
            expected_title = str(req.get("title") or "")

            result: Dict[str, Any] = {"req_id": req_id, "status": "fallback", "url": None}
            try:
                if browser not in SUPPORTED_BROWSERS or not hwnd:
                    result["status"] = "unsupported"
                elif not _verify_hwnd_identity(hwnd, pid, ctime, expected_title):
                    result["status"] = "stale"
                else:
                    root = uia.ElementFromHandle(hwnd)
                    addr, popup, ambiguous = _find_unique_address_bar(uia, root, browser)
                    if ambiguous or popup or addr is None:
                        result["status"] = "ambiguous" if ambiguous else ("popup" if popup else "not_found")
                    else:
                        if bool(addr.CurrentHasKeyboardFocus):
                            result["status"] = "editing"
                        else:
                            url_before = _read_value_pattern(mod, addr)
                            still_focused = bool(addr.CurrentHasKeyboardFocus)
                            url_after = _read_value_pattern(mod, addr)
                            # 双端夹逼：读取前后地址一致、未进入编辑态且窗口/进程/标题未变
                            if (
                                not still_focused
                                and url_before
                                and url_before == url_after
                                and _verify_hwnd_identity(hwnd, pid, ctime, expected_title)
                            ):
                                result["status"] = "ok"
                                result["url"] = url_before
                            else:
                                result["status"] = "stale"
            except Exception:
                # 绝不将 UIA 异常细节或窗口内容返回到日志或数据库
                result["status"] = "error"
                result["url"] = None

            try:
                conn.send(result)
            except (BrokenPipeError, OSError):
                break
    except Exception:
        try:
            conn.send({"ready": False})
        except Exception:
            pass
    finally:
        uia = None
        mod = None
        try:
            conn.close()
        except Exception:
            pass
        if com_initialized:
            try:
                import comtypes
                comtypes.CoUninitialize()
            except Exception:
                pass


class UiaWorkerClient:
    """管理单个可回收 UIA 子进程，提供硬超时与按 hwnd 冷却退避。"""

    def __init__(
        self,
        *,
        timeout_s: float = 0.15,
        cooldown_s: float = 30.0,
        gen_dir: Optional[Path] = None,
    ):
        self.timeout_s = max(0.05, float(timeout_s))
        self.cooldown_s = max(1.0, float(cooldown_s))
        self._gen_dir = gen_dir
        self._lock = threading.Lock()
        self._proc = None
        self._conn = None
        self._req_id = 0
        self._cooldown_until: Dict[int, float] = {}
        self._closed = False

    def _start_worker_locked(self) -> bool:
        if self._closed or os.name != "nt":
            return False
        if self._proc is not None and self._proc.is_alive() and self._conn is not None:
            return True
        self._terminate_locked()
        try:
            ctx = multiprocessing.get_context("spawn")
            parent_conn, child_conn = ctx.Pipe(duplex=True)
            gen_str = str(self._gen_dir) if self._gen_dir else ""
            proc = ctx.Process(
                target=_worker_main,
                args=(child_conn, gen_str),
                daemon=True,
                name="Dayflow-UIA-Worker",
            )
            proc.start()
            child_conn.close()
            if parent_conn.poll(3.0):
                hello = parent_conn.recv()
                if isinstance(hello, dict) and hello.get("ready"):
                    self._proc = proc
                    self._conn = parent_conn
                    return True
            parent_conn.close()
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1.0)
        except Exception as exc:
            logger.warning("启动 UIA 工作进程失败: %s", type(exc).__name__)
        return False

    def _terminate_locked(self, timeout: float = 0.8) -> None:
        conn, proc = self._conn, self._proc
        self._conn = None
        self._proc = None
        if conn is not None:
            try:
                conn.send({"cmd": "shutdown"})
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        if proc is not None:
            try:
                proc.join(timeout=min(0.3, timeout))
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=max(0.2, timeout - 0.3))
                if proc.is_alive() and hasattr(proc, "kill"):
                    proc.kill()
                    proc.join(timeout=0.2)
            except Exception:
                pass

    def query_browser_url(
        self,
        *,
        hwnd: int,
        browser: str,
        pid: int,
        create_time: float,
        title: str,
    ) -> Optional[str]:
        """在硬超时内向可回收 UIA 子进程查询地址栏原文（仅在内存中校验，不落盘）。"""
        if browser not in SUPPORTED_BROWSERS or not hwnd or os.name != "nt":
            return None
        now = time.monotonic()
        with self._lock:
            if self._closed:
                return None
            if self._cooldown_until.get(hwnd, 0.0) > now:
                return None
            if not self._start_worker_locked():
                self._cooldown_until[hwnd] = now + self.cooldown_s
                return None
            self._req_id += 1
            rid = self._req_id
            try:
                self._conn.send({
                    "cmd": "query",
                    "req_id": rid,
                    "hwnd": int(hwnd),
                    "browser": browser,
                    "pid": int(pid),
                    "create_time": float(create_time),
                    "title": title,
                })
                if not self._conn.poll(self.timeout_s):
                    # COM 调用卡死：冷却该 hwnd 并回收子进程
                    self._cooldown_until[hwnd] = time.monotonic() + self.cooldown_s
                    self._terminate_locked()
                    return None
                resp = self._conn.recv()
            except Exception:
                self._cooldown_until[hwnd] = time.monotonic() + self.cooldown_s
                self._terminate_locked()
                return None

            if not isinstance(resp, dict) or resp.get("req_id") != rid:
                self._terminate_locked()
                return None
            if resp.get("status") == "ok":
                return resp.get("url")
            return None

    def close(self, timeout: float = 1.0) -> None:
        with self._lock:
            self._closed = True
            self._terminate_locked(timeout=timeout)
