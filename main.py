"""
Dayflow for Windows - 启动入口
智能时间追踪与生产力分析
"""
import sys
import logging
import argparse
from pathlib import Path

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

import config
from ui.main_window import MainWindow
from core.log_manager import LogManager

# 全局日志管理器实例
_log_manager = None


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Dayflow - 智能时间追踪")
    parser.add_argument(
        '--minimized', 
        action='store_true',
        help='启动时最小化到系统托盘（用于开机自启动）'
    )
    return parser.parse_args()


def setup_logging():
    """配置日志（使用 LogManager 实现轮转）"""
    global _log_manager
    
    _log_manager = LogManager(
        log_dir=config.APP_DATA_DIR,
        log_filename="dayflow.log",
        max_size_mb=5,
        backup_count=5,
        retention_days=30,
        log_level=logging.INFO
    )
    
    # 配置日志系统
    _log_manager.setup()
    
    # 启动时清理过期日志
    _log_manager.cleanup_old_logs()


def check_pending_update():
    """检查是否有待安装的更新"""
    from core.updater import UpdateManager
    
    manager = UpdateManager()
    if manager.has_pending_update():
        logger = logging.getLogger(__name__)
        logger.info("检测到待安装更新，启动更新程序...")
        if manager.apply_update():
            return True  # 需要退出，让 updater 接管
    return False


def check_autostart_path():
    """检测自启动路径是否变化"""
    from core.autostart import check_path_changed, update_autostart_path
    
    changed, old_path, new_path = check_path_changed()
    if changed:
        logger = logging.getLogger(__name__)
        logger.warning(f"检测到 EXE 路径变化: {old_path} -> {new_path}")
        
        # 弹窗询问用户是否更新
        reply = QMessageBox.question(
            None,
            "路径变化",
            f"检测到程序位置已变化：\n\n"
            f"原路径：{old_path}\n"
            f"新路径：{new_path}\n\n"
            f"是否更新开机自启动设置？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success, msg = update_autostart_path()
            if success:
                QMessageBox.information(None, "成功", "自启动路径已更新")
            else:
                QMessageBox.warning(None, "失败", msg)


def main():
    """应用入口"""
    # 解析命令行参数
    args = parse_args()
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 50)
    logger.info(f"Dayflow for Windows v{config.VERSION} 启动")
    logger.info(f"数据目录: {config.APP_DATA_DIR}")
    if args.minimized:
        logger.info("启动模式: 最小化到托盘")
    logger.info("=" * 50)
    
    # 检查待安装更新
    if check_pending_update():
        logger.info("更新程序已启动，主程序退出")
        return 0
    
    # 启用高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Dayflow")
    app.setApplicationVersion(config.VERSION)
    app.setOrganizationName("Dayflow")
    
    # 设置默认字体
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    # 加载并应用保存的主题
    from database.storage import StorageManager
    from ui.themes import get_theme_manager, DARK_THEME, LIGHT_THEME
    
    storage = StorageManager()
    saved_theme = storage.get_setting("theme", "dark")
    theme_manager = get_theme_manager()
    if saved_theme == "light":
        theme_manager.set_theme(LIGHT_THEME)
    else:
        theme_manager.set_theme(DARK_THEME)
    
    # 检测自启动路径变化
    check_autostart_path()
    
    # 创建主窗口
    window = MainWindow()
    
    # 根据参数决定是否显示窗口
    if args.minimized:
        # 最小化启动：不显示窗口，只显示托盘图标
        logger.info("静默启动，最小化到托盘")
        # 自启动后自动开始录制
        window.auto_start_recording()
    else:
        window.show()
        logger.info("主窗口已显示")
    
    # 运行应用
    exit_code = app.exec()
    
    logger.info(f"Dayflow 退出，代码: {exit_code}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
