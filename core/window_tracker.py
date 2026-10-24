"""
Dayflow Windows - 窗口信息追踪模块
使用 Windows API 获取当前活动窗口的进程名和标题
"""
import logging
from dataclasses import dataclass
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# 尝试导入 Windows 相关库
try:
    import win32gui
    import win32process
    import psutil
    WINDOWS_API_AVAILABLE = True
except ImportError:
    WINDOWS_API_AVAILABLE = False
    logger.warning("win32gui/psutil 未安装，窗口追踪功能不可用")


@dataclass
class WindowInfo:
    """窗口信息"""
    app_name: str  # 进程名，如 "chrome.exe"
    window_title: str  # 窗口标题
    process_id: int  # 进程 ID
    
    def get_clean_app_name(self) -> str:
        """获取干净的应用名称（去掉 .exe 后缀）"""
        name = self.app_name
        if name.lower().endswith('.exe'):
            name = name[:-4]
        return name


class WindowTracker:
    """
    窗口追踪器
    获取当前活动窗口的信息
    """
    
    def __init__(self):
        self._available = WINDOWS_API_AVAILABLE
        # PID -> 进程名 缓存，避免每秒重复调用 psutil.Process(pid)
        self._pid_cache: Dict[int, str] = {}
        self._pid_cache_max_size = 256
        # 应用名称映射表，用于标准化常见应用名称
        self._app_name_map = {
            "code": "Visual Studio Code",
            "cursor": "Cursor",
            "chrome": "Google Chrome",
            "msedge": "Microsoft Edge",
            "firefox": "Firefox",
            "wechat": "微信",
            "weixin": "微信",
            "qq": "QQ",
            "dingtalk": "钉钉",
            "feishu": "飞书",
            "lark": "飞书",
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
            "outlook": "Microsoft Outlook",
            "notepad": "记事本",
            "notepad++": "Notepad++",
            "sublime_text": "Sublime Text",
            "idea64": "IntelliJ IDEA",
            "pycharm64": "PyCharm",
            "webstorm64": "WebStorm",
            "datagrip64": "DataGrip",
            "explorer": "文件资源管理器",
            "windowsterminal": "Windows Terminal",
            "cmd": "命令提示符",
            "powershell": "PowerShell",
            "spotify": "Spotify",
            "cloudmusic": "网易云音乐",
            "qqmusic": "QQ音乐",
            "potplayer": "PotPlayer",
            "potplayer64": "PotPlayer",
            "vlc": "VLC",
            "steam": "Steam",
            "epicgameslauncher": "Epic Games",
        }
    
    @property
    def is_available(self) -> bool:
        """检查窗口追踪功能是否可用"""
        return self._available
    
    def get_active_window(self) -> Optional[WindowInfo]:
        """
        获取当前活动窗口的信息
        
        Returns:
            WindowInfo 或 None（如果获取失败）
        """
        if not self._available:
            return None
        
        try:
            # 获取前台窗口句柄
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            
            # 获取窗口标题
            window_title = win32gui.GetWindowText(hwnd)
            
            # 获取进程 ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            # 获取进程名（使用带缓存的方法）
            app_name = self.get_process_name(pid)
            
            return WindowInfo(
                app_name=app_name,
                window_title=window_title,
                process_id=pid
            )
            
        except Exception as e:
            logger.debug(f"获取窗口信息失败: {e}")
            return None

    def get_process_name(self, pid: int) -> str:
        """根据 PID 获取进程名（带缓存，避免频繁创建 psutil.Process）"""
        if pid in self._pid_cache:
            return self._pid_cache[pid]

        try:
            process = psutil.Process(pid)
            app_name = process.name()
            if len(self._pid_cache) >= self._pid_cache_max_size:
                self._pid_cache.clear()
            self._pid_cache[pid] = app_name
            return app_name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "Unknown"
        except Exception:
            return "Unknown"
    
    def get_friendly_app_name(self, window_info: Optional[WindowInfo]) -> str:
        """
        获取友好的应用名称
        
        Args:
            window_info: 窗口信息
            
        Returns:
            友好的应用名称
        """
        if not window_info:
            return "Unknown"
        
        # 获取干净的进程名（去掉 .exe）
        clean_name = window_info.get_clean_app_name().lower()
        
        # 查找映射表
        if clean_name in self._app_name_map:
            return self._app_name_map[clean_name]
        
        # 返回原始名称（首字母大写）
        return window_info.get_clean_app_name().title()


# 全局单例
_tracker: Optional[WindowTracker] = None


def get_tracker() -> WindowTracker:
    """获取窗口追踪器单例"""
    global _tracker
    if _tracker is None:
        _tracker = WindowTracker()
    return _tracker


def get_active_window_info() -> Optional[WindowInfo]:
    """便捷函数：获取当前活动窗口信息"""
    return get_tracker().get_active_window()
