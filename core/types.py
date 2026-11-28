"""
Dayflow Windows - 数据模型定义
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum


class ChunkStatus(Enum):
    """视频切片状态"""
    PENDING = "pending"  # 等待分析
    PROCESSING = "processing"  # 分析中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class BatchStatus(Enum):
    """分析批次状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CaptureState(Enum):
    """本机上下文三态隐私判定"""
    SENSITIVE_OR_UNKNOWN = "sensitive_or_unknown"
    APP_VERIFIED = "app_verified"
    CONTEXT_VERIFIED = "context_verified"


@dataclass(frozen=True)
class WindowContext:
    """结构化脱敏窗口上下文（不含原始 URL 路径/查询串或 page_title）"""
    state: CaptureState
    app_name: str = ""
    friendly_app: str = ""
    category: str = "其他"
    domain: Optional[str] = None
    project_name: Optional[str] = None
    document_name: Optional[str] = None
    meeting_active: bool = False
    source: str = "app_only"  # app_only | title | uia | mic


@dataclass
class ActivitySegment:
    """卡片内精确记账分段（与 timeline_cards 同寿命，无重叠覆盖卡片区间）"""
    start_time: datetime
    end_time: datetime
    app_name: str
    is_distraction: bool = False

    def to_dict(self) -> dict:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "app_name": self.app_name,
            "is_distraction": bool(self.is_distraction),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActivitySegment":
        start = data["start_time"]
        end = data["end_time"]
        return cls(
            start_time=datetime.fromisoformat(start) if isinstance(start, str) else start,
            end_time=datetime.fromisoformat(end) if isinstance(end, str) else end,
            app_name=str(data.get("app_name", "")),
            is_distraction=bool(data.get("is_distraction", False)),
        )


@dataclass
class Observation:
    """
    观察记录 - 对应视频转录结果
    """
    start_ts: float  # 开始时间戳(秒)
    end_ts: float  # 结束时间戳(秒)
    text: str  # 观察描述
    app_name: Optional[str] = None  # 应用名称
    window_title: Optional[str] = None  # 窗口标题
    file_hint: Optional[str] = None  # 从窗口标题提取出的文件名/页面名线索

    def to_dict(self) -> dict:
        return {
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "text": self.text,
            "app_name": self.app_name,
            "window_title": self.window_title,
            "file_hint": self.file_hint,
        }


@dataclass
class AppSite:
    """应用/网站信息"""
    name: str
    duration_seconds: float = 0
    icon_url: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration_seconds": self.duration_seconds,
            "icon_url": self.icon_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppSite":
        return cls(
            name=data.get("name", ""),
            duration_seconds=data.get("duration_seconds", 0),
            icon_url=data.get("icon_url"),
        )


@dataclass
class Distraction:
    """分心记录"""
    description: str
    timestamp: float
    duration_seconds: float = 0

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Distraction":
        return cls(
            description=data.get("description", ""),
            timestamp=data.get("timestamp", 0),
            duration_seconds=data.get("duration_seconds", 0),
        )


@dataclass
class ActivityCard:
    """
    时间轴活动卡片 - 展示在时间轴上的主要元素
    """
    id: Optional[int] = None
    category: str = ""  # 活动类别 (工作/学习/娱乐等)
    title: str = ""  # 活动标题
    summary: str = ""  # 活动摘要
    start_time: Optional[datetime] = None  # 开始时间
    end_time: Optional[datetime] = None  # 结束时间
    app_sites: List[AppSite] = field(default_factory=list)  # 使用的应用/网站
    distractions: List[Distraction] = field(default_factory=list)  # 分心记录
    productivity_score: float = 0.0  # 生产力评分 (0 表示未评分；模型评分 1-100)
    # 内部记账与状态字段（不破坏公开 to_dict() 契约）
    source: str = "visual"  # visual | local | local_refined | manual
    user_edited: bool = False
    session_key: Optional[str] = None
    is_finalized: bool = True
    version: int = 1
    segments: List[ActivitySegment] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "app_sites": [a.to_dict() for a in self.app_sites],
            "distractions": [d.to_dict() for d in self.distractions],
            "productivity_score": self.productivity_score,
        }

    @property
    def duration_minutes(self) -> float:
        """活动持续时间（分钟）"""
        if self.start_time and self.end_time:
            start = self.start_time.replace(tzinfo=None) if self.start_time.tzinfo else self.start_time
            end = self.end_time.replace(tzinfo=None) if self.end_time.tzinfo else self.end_time
            delta = end - start
            return delta.total_seconds() / 60
        return 0


@dataclass
class VideoChunk:
    """视频切片"""
    id: Optional[int] = None
    file_path: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0
    status: ChunkStatus = ChunkStatus.PENDING
    batch_id: Optional[int] = None
    window_records_path: Optional[str] = None  # 窗口记录 JSON 文件路径


@dataclass
class AnalysisBatch:
    """分析批次"""
    id: Optional[int] = None
    chunk_ids: List[int] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: BatchStatus = BatchStatus.PENDING
    observations_json: str = "[]"
    error_message: Optional[str] = None
