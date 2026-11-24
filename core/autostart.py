"""Windows sign-in registration for the installed Tauri host."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Dayflow"


def get_exe_path() -> str:
    host = os.getenv("DAYFLOW_HOST_EXE", "")
    path = Path(host)
    return str(path) if host and path.is_file() and path.name.lower() == "dayflow.exe" else ""


def get_registered_path() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
    except (ImportError, OSError):
        return ""
    if not isinstance(value, str):
        return ""
    if value.startswith('"'):
        return value.split('"', 2)[1]
    return value.removesuffix(" --minimized").strip()


def is_autostart_enabled() -> bool:
    return bool(get_exe_path() and get_registered_path())


def enable_autostart() -> tuple[bool, str]:
    path = get_exe_path()
    if not path:
        return False, "请使用安装版设置开机自启"
    try:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{path}" --minimized')
    except (ImportError, OSError):
        logger.warning("无法写入 Dayflow 开机启动项")
        return False, "无法写入开机启动项"
    return True, "开机自启已开启"


def disable_autostart() -> tuple[bool, str]:
    if not get_exe_path():
        return False, "请使用安装版设置开机自启"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        pass
    except (ImportError, OSError):
        logger.warning("无法移除 Dayflow 开机启动项")
        return False, "无法移除开机启动项"
    return True, "开机自启已关闭"


def check_path_changed() -> tuple[bool, str, str]:
    previous = get_registered_path()
    current = get_exe_path()
    changed = bool(previous and current and os.path.normcase(previous) != os.path.normcase(current))
    return changed, previous, current


def update_autostart_path() -> tuple[bool, str]:
    if not is_autostart_enabled():
        return False, "开机自启未启用"
    return enable_autostart()
