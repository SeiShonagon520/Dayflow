"""
Dayflow for Windows - 启动入口
智能时间追踪与生产力分析
"""
import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

import config
from ui.main_window import MainWindow


def setup_logging():
    """配置日志"""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_file = config.APP_DATA_DIR / "dayflow.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    
    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    """应用入口"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 50)
    logger.info("Dayflow for Windows 启动")
    logger.info(f"数据目录: {config.APP_DATA_DIR}")
    logger.info("=" * 50)
    
    # 启用高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Dayflow")
    app.setApplicationVersion("1.1.0")
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
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    logger.info("主窗口已显示")
    
    # 运行应用
    exit_code = app.exec()
    
    logger.info(f"Dayflow 退出，代码: {exit_code}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
