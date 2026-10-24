"""
Dayflow - 开机自启动管理
使用 Windows 注册表实现
"""
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Windows 注册表路径
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Dayflow"


def is_frozen() -> bool:
    """检测是否为打包后的 EXE 运行"""
    return getattr(sys, 'frozen', False)


def get_exe_path() -> str:
    """获取当前可执行文件的完整路径（优先返回主程序 dayflow.exe）"""
    if is_frozen():
        exe = Path(sys.executable)
        dayflow = exe.parent / "dayflow.exe"
        if dayflow.is_file():
            return str(dayflow)
        return str(exe)
    else:
        # 开发模式下返回 python 解释器路径（不应用于自启动）
        return sys.executable


def is_autostart_enabled() -> bool:
    """检测是否已启用开机自启动"""
    if not is_frozen():
        return False
    
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            REG_PATH, 
            0, 
            winreg.KEY_READ
        )
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception as e:
        logger.warning(f"检测自启动状态失败: {e}")
        return False


def get_registered_path() -> str:
    """获取注册表中记录的启动路径"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            REG_PATH, 
            0, 
            winreg.KEY_READ
        )
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            # 移除引号
            return value.strip('"').split('" ')[0].strip('"')
        except FileNotFoundError:
            winreg.CloseKey(key)
            return ""
    except Exception as e:
        logger.warning(f"获取注册路径失败: {e}")
        return ""


def enable_autostart() -> tuple:
    """
    启用开机自启动
    
    Returns:
        (success: bool, message: str)
    """
    if not is_frozen():
        return False, "开发模式下无法启用自启动，请使用打包后的 EXE"
    
    try:
        import winreg
        exe_path = get_exe_path()
        
        # 添加 --minimized 参数，启动时直接最小化到托盘
        startup_command = f'"{exe_path}" --minimized'
        
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            REG_PATH, 
            0, 
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command)
        winreg.CloseKey(key)
        
        logger.info(f"已启用开机自启动: {startup_command}")
        return True, "开机自启动已启用"
        
    except PermissionError:
        logger.error("启用自启动失败: 权限不足")
        return False, "权限不足，请以管理员身份运行"
    except Exception as e:
        logger.error(f"启用自启动失败: {e}")
        return False, f"启用失败: {e}"


def disable_autostart() -> tuple:
    """
    禁用开机自启动
    
    Returns:
        (success: bool, message: str)
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            REG_PATH, 
            0, 
            winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, APP_NAME)
            logger.info("已禁用开机自启动")
        except FileNotFoundError:
            # 本来就没有，不算错误
            pass
        winreg.CloseKey(key)
        return True, "开机自启动已禁用"
        
    except PermissionError:
        logger.error("禁用自启动失败: 权限不足")
        return False, "权限不足，请以管理员身份运行"
    except Exception as e:
        logger.error(f"禁用自启动失败: {e}")
        return False, f"禁用失败: {e}"


def check_path_changed() -> tuple:
    """
    检测 EXE 路径是否发生变化
    
    Returns:
        (changed: bool, old_path: str, new_path: str)
    """
    if not is_frozen():
        return False, "", ""
    
    if not is_autostart_enabled():
        return False, "", ""
    
    registered_path = get_registered_path()
    current_path = get_exe_path()
    
    if registered_path and registered_path != current_path:
        return True, registered_path, current_path
    
    return False, "", ""


def update_autostart_path() -> tuple:
    """
    更新自启动路径（当 EXE 被移动后调用）
    
    Returns:
        (success: bool, message: str)
    """
    if not is_autostart_enabled():
        return False, "自启动未启用"
    
    # 重新启用即可更新路径
    return enable_autostart()
