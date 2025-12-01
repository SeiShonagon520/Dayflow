"""
Dayflow Windows - 配置文件
"""
import os
from pathlib import Path

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

# 数据目录
APP_DATA_DIR = Path(os.getenv("LOCALAPPDATA", "")) / "Dayflow"
CHUNKS_DIR = APP_DATA_DIR / "chunks"
DATABASE_PATH = APP_DATA_DIR / "dayflow.db"

# 确保目录存在
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# UI 配置
WINDOW_TITLE = "Dayflow"
WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 600
