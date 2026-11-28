"""
Dayflow Windows - 窗口信息追踪模块
使用 Windows API 获取当前活动窗口的进程名、进程创建时间、句柄和标题
"""
import logging
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# 尝试导入 Windows 相关库
try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import psutil
    WINDOWS_API_AVAILABLE = True
except ImportError:
    WINDOWS_API_AVAILABLE = False
    logger.warning("win32gui/psutil 未安装，窗口追踪功能不可用")


UNKNOWN_OUTBOUND_APP_LABEL = "其他应用"


@dataclass
class WindowInfo:
    """窗口信息（保留三参构造向后兼容，新增可选 hwnd 与 process_create_time）"""
    app_name: str  # 进程名，如 "chrome.exe"
    window_title: str  # 窗口标题
    process_id: int  # 进程 ID
    hwnd: int = 0  # 窗口句柄
    process_create_time: float = 0.0  # 进程创建时间戳，防止 PID 复用串台

    def get_clean_app_name(self) -> str:
        """获取干净的应用名称（去掉 .exe 后缀）"""
        name = self.app_name
        if name.lower().endswith(".exe"):
            name = name[:-4]
        return name


APP_NAME_MAP: Dict[str, str] = {
    "code": "Visual Studio Code",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "zed": "Zed",
    "devenv": "Visual Studio",
    "chrome": "Google Chrome",
    "msedge": "Microsoft Edge",
    "firefox": "Firefox",
    "brave": "Brave",
    "arc": "Arc",
    "wechat": "微信",
    "weixin": "微信",
    "qq": "QQ",
    "dingtalk": "钉钉",
    "feishu": "飞书",
    "lark": "飞书",
    "wemeetapp": "腾讯会议",
    "zoom": "Zoom",
    "ms-teams": "Microsoft Teams",
    "teams": "Microsoft Teams",
    "webex": "Webex",
    "slack": "Slack",
    "discord": "Discord",
    "telegram": "Telegram",
    "notion": "Notion",
    "obsidian": "Obsidian",
    "typora": "Typora",
    "word": "Microsoft Word",
    "winword": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpnt": "Microsoft PowerPoint",
    "visio": "Microsoft Visio",
    "wps": "WPS Office",
    "outlook": "Microsoft Outlook",
    "notepad": "记事本",
    "notepad++": "Notepad++",
    "sublime_text": "Sublime Text",
    "idea64": "IntelliJ IDEA",
    "pycharm64": "PyCharm",
    "webstorm64": "WebStorm",
    "clion64": "CLion",
    "goland64": "GoLand",
    "rider64": "Rider",
    "datagrip64": "DataGrip",
    "figma": "Figma",
    "postman": "Postman",
    "explorer": "文件资源管理器",
    "windowsterminal": "Windows Terminal",
    "cmd": "命令提示符",
    "powershell": "PowerShell",
    "pwsh": "PowerShell",
    "spotify": "Spotify",
    "cloudmusic": "网易云音乐",
    "qqmusic": "QQ音乐",
    "potplayer": "PotPlayer",
    "potplayer64": "PotPlayer",
    "vlc": "VLC",
    "steam": "Steam",
    "epicgameslauncher": "Epic Games",
}

_CANONICAL_FRIENDLY_LABELS = set(APP_NAME_MAP.values())


def get_outbound_app_label(raw_name: str) -> str:
    """
    为外发纯文本精炼返回固定白名单应用标签；
    未知进程或自由文本一律折叠为固定常量，避免泄露自定义可执行文件名或域名。
    """
    text = (raw_name or "").strip()
    if not text:
        return UNKNOWN_OUTBOUND_APP_LABEL
    if text in _CANONICAL_FRIENDLY_LABELS:
        return text
    clean = text[:-4].lower() if text.lower().endswith(".exe") else text.lower()
    if clean in APP_NAME_MAP:
        return APP_NAME_MAP[clean]
    return UNKNOWN_OUTBOUND_APP_LABEL


class WindowTracker:
    """
    窗口追踪器
    获取当前活动窗口的信息，并通过 (pid, create_time) 防止 PID 复用绕过隐私规则。
    """

    def __init__(self):
        self._available = WINDOWS_API_AVAILABLE
        # 向后兼容的 PID 缓存（仅用于 get_process_name）
        self._pid_cache: Dict[int, str] = {}
        self._pid_cache_max_size = 256
        # (pid, create_time) -> 进程名，用于结构化隐私校验，彻底避免 PID 复用串台
        self._proc_cache: Dict[Tuple[int, float], str] = {}
        self._proc_cache_max_size = 256
        self._app_name_map = dict(APP_NAME_MAP)

    @property
    def is_available(self) -> bool:
        """检查窗口追踪功能是否可用"""
        return self._available

    def get_window_info(self, hwnd: int) -> Optional[WindowInfo]:
        """根据指定窗口句柄获取已校验进程身份的 WindowInfo。"""
        if not self._available or not hwnd:
            return None
        try:
            if not win32gui.IsWindow(hwnd):
                return None
            window_title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return None
            app_name, create_time = self.get_process_identity(pid)
            if not app_name or app_name == "Unknown" or create_time <= 0:
                return None
            return WindowInfo(
                app_name=app_name,
                window_title=window_title,
                process_id=pid,
                hwnd=int(hwnd),
                process_create_time=create_time,
            )
        except Exception as e:
            logger.debug("获取指定窗口信息失败: %s", e)
            return None

    def get_active_window(self) -> Optional[WindowInfo]:
        """获取当前活动窗口的信息"""
        if not self._available:
            return None
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            return self.get_window_info(hwnd)
        except Exception as e:
            logger.debug("获取窗口信息失败: %s", e)
            return None

    def get_process_identity(self, pid: int) -> Tuple[str, float]:
        """返回 (process_name, create_time)，避免 PID 复用串台。"""
        try:
            process = psutil.Process(pid)
            create_time = float(process.create_time()) if hasattr(process, "create_time") else 0.0
            if create_time > 0:
                key = (int(pid), create_time)
                cached = self._proc_cache.get(key)
                if cached is not None:
                    return cached, create_time
                app_name = process.name()
                if len(self._proc_cache) >= self._proc_cache_max_size:
                    self._proc_cache.clear()
                self._proc_cache[key] = app_name
                return app_name, create_time
            return process.name(), 0.0
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "Unknown", 0.0
        except Exception:
            return "Unknown", 0.0

    def get_process_name(self, pid: int) -> str:
        """根据 PID 获取进程名（保留缓存以兼容旧调用方）。"""
        if pid in self._pid_cache:
            return self._pid_cache[pid]
        try:
            app_name = psutil.Process(pid).name()
            if len(self._pid_cache) >= self._pid_cache_max_size:
                self._pid_cache.clear()
            self._pid_cache[pid] = app_name
            return app_name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "Unknown"
        except Exception:
            return "Unknown"

    def capture_monitor_bounds(self):
        """Return monitor bounds in physical pixels, matching DXGI and DWM."""
        if not self._available:
            return None
        try:
            bounds = set()
            for handle, _, _ in win32api.EnumDisplayMonitors():
                name = win32api.GetMonitorInfo(handle)["Device"]
                mode = win32api.EnumDisplaySettings(name, win32con.ENUM_CURRENT_SETTINGS)
                x, y = mode.Position_x, mode.Position_y
                bounds.add((x, y, x + mode.PelsWidth, y + mode.PelsHeight))
            return bounds or None
        except Exception:
            return None

    def visible_windows(self, monitor_bounds):
        """Include non-foreground windows on the captured displays."""
        if not self._available:
            return None
        result = []
        try:
            read_attribute = ctypes.windll.dwmapi.DwmGetWindowAttribute
            read_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            read_attribute.restype = ctypes.c_long
            get_shell_window = ctypes.windll.user32.GetShellWindow
            get_shell_window.restype = wintypes.HWND
            desktop_windows = {get_shell_window(), win32gui.GetDesktopWindow()}

            def collect(hwnd, _):
                if hwnd in desktop_windows or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                    return True
                cloaked = wintypes.DWORD()
                if read_attribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0:
                    raise OSError("DWM window visibility unavailable")
                if cloaked.value:
                    return True
                rect = wintypes.RECT()
                if read_attribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
                    raise OSError("DWM window bounds unavailable")
                if rect.right <= rect.left or rect.bottom <= rect.top:
                    return True
                if any(
                    rect.left < right and rect.right > left and rect.top < bottom and rect.bottom > top
                    for left, top, right, bottom in monitor_bounds
                ):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    name, create_time = self.get_process_identity(pid)
                    result.append(
                        WindowInfo(name, win32gui.GetWindowText(hwnd), pid, hwnd=int(hwnd), process_create_time=create_time)
                    )
                return True

            win32gui.EnumWindows(collect, None)
            return result
        except Exception:
            return None

    def get_friendly_app_name(self, window_info: Optional[WindowInfo]) -> str:
        """获取友好的应用名称"""
        if not window_info:
            return "Unknown"
        clean_name = window_info.get_clean_app_name().lower()
        if clean_name in self._app_name_map:
            return self._app_name_map[clean_name]
        return window_info.get_clean_app_name().title()


# 全局单例
_tracker: Optional[WindowTracker] = None


def get_tracker() -> WindowTracker:
    """获取窗口追踪器单例"""
    global _tracker
    if _tracker is None:
        _tracker = WindowTracker()
    return _tracker
