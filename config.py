"""
Dayflow Windows - 配置文件
"""
import os
from pathlib import Path

# 版本信息
VERSION = "1.5.1"
GITHUB_REPO = "SeiShonagon520/Dayflow"

# API 配置 (OpenAI 兼容格式)
API_BASE_URL = os.getenv("DAYFLOW_API_URL", "https://apis.iflow.cn/v1")
API_KEY = os.getenv("DAYFLOW_API_KEY", "")
API_MODEL = os.getenv("DAYFLOW_API_MODEL", "qwen3-vl-plus")  # 支持视觉输入的模型

# 录屏配置
RECORD_FPS = 1  # 每秒1帧
CHUNK_DURATION_SECONDS = 60  # 每60秒一个切片
VIDEO_BITRATE = "500k"  # 低码率
VIDEO_CODEC = "libx264"

# 分析配置
BATCH_DURATION_MINUTES = 15  # 批次时长约15分钟
ANALYSIS_INTERVAL_SECONDS = 60  # 每分钟扫描一次

# 存储清理配置
AUTO_DELETE_ANALYZED_CHUNKS = True  # 分析完成后自动删除视频切片（节省磁盘空间）

# 数据目录 - 使用更可靠的方式获取 AppData 路径
def _get_app_data_dir() -> Path:
    """获取应用数据目录"""
    # 优先使用 LOCALAPPDATA
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Dayflow"
    
    # 备选：使用 USERPROFILE
    user_profile = os.getenv("USERPROFILE")
    if user_profile:
        return Path(user_profile) / "AppData" / "Local" / "Dayflow"
    
    # 最后备选：使用 Path.home()
    return Path.home() / "AppData" / "Local" / "Dayflow"

APP_DATA_DIR = _get_app_data_dir()
CHUNKS_DIR = APP_DATA_DIR / "chunks"
DATABASE_PATH = APP_DATA_DIR / "dayflow.db"

# 确保目录存在
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# 打印数据目录路径（用于调试）
print(f"[Dayflow] 数据目录: {APP_DATA_DIR}")

# UI 配置
WINDOW_TITLE = "Dayflow"
WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 600
