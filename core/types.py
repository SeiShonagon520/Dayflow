"""
Dayflow Windows - 数据模型定义
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum
import json


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
    
    def to_dict(self) -> dict:
        return {
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "text": self.text,
            "app_name": self.app_name,
            "window_title": self.window_title
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Observation":
        return cls(
            start_ts=data.get("start_ts", 0),
            end_ts=data.get("end_ts", 0),
            text=data.get("text", ""),
            app_name=data.get("app_name"),
            window_title=data.get("window_title")
        )


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
            "icon_url": self.icon_url
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AppSite":
        return cls(
            name=data.get("name", ""),
            duration_seconds=data.get("duration_seconds", 0),
            icon_url=data.get("icon_url")
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
            "duration_seconds": self.duration_seconds
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Distraction":
        return cls(
            description=data.get("description", ""),
            timestamp=data.get("timestamp", 0),
            duration_seconds=data.get("duration_seconds", 0)
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
    productivity_score: float = 0.0  # 生产力评分 (0-100)
    
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
            "productivity_score": self.productivity_score
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ActivityCard":
        return cls(
            id=data.get("id"),
            category=data.get("category", ""),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            app_sites=[AppSite.from_dict(a) for a in data.get("app_sites", [])],
            distractions=[Distraction.from_dict(d) for d in data.get("distractions", [])],
            productivity_score=data.get("productivity_score", 0.0)
        )
    
    @property
    def duration_minutes(self) -> float:
        """活动持续时间（分钟）"""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
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
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value,
            "batch_id": self.batch_id
        }


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
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chunk_ids": self.chunk_ids,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "observations_json": self.observations_json,
            "error_message": self.error_message
        }
