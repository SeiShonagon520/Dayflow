"""
Dayflow - 配置集中化管理器
支持数据库存储用户配置，回退到 config.py 默认值
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, List, Tuple, Optional

from PySide6.QtCore import QObject, Signal

import config

logger = logging.getLogger(__name__)


@dataclass
class ConfigKey:
    """配置键定义"""
    EMAIL_SEND_TIMES: str = "email_send_times"  # JSON: ["12:00", "22:00"]
    VIDEO_MAX_FRAMES: str = "video_max_frames"  # int: 8
    API_TIMEOUT: str = "api_timeout"  # float: 120.0
    BATCH_DURATION_MINUTES: str = "batch_duration_minutes"  # int: 15
    LOG_MAX_SIZE_MB: str = "log_max_size_mb"  # int: 5
    LOG_BACKUP_COUNT: str = "log_backup_count"  # int: 5
    LOG_RETENTION_DAYS: str = "log_retention_days"  # int: 30
    DB_POOL_SIZE: str = "db_pool_size"  # int: 5
    DB_POOL_TIMEOUT: str = "db_pool_timeout"  # float: 30.0
    DB_IDLE_TIMEOUT: str = "db_idle_timeout"  # float: 300.0


# 默认值映射 (从 config.py 或硬编码)
DEFAULT_VALUES = {
    ConfigKey.EMAIL_SEND_TIMES: '["12:00", "22:00"]',
    ConfigKey.VIDEO_MAX_FRAMES: "8",
    ConfigKey.API_TIMEOUT: "120.0",
    ConfigKey.BATCH_DURATION_MINUTES: str(getattr(config, 'BATCH_DURATION_MINUTES', 15)),
    ConfigKey.LOG_MAX_SIZE_MB: "5",
    ConfigKey.LOG_BACKUP_COUNT: "5",
    ConfigKey.LOG_RETENTION_DAYS: "30",
    ConfigKey.DB_POOL_SIZE: "5",
    ConfigKey.DB_POOL_TIMEOUT: "30.0",
    ConfigKey.DB_IDLE_TIMEOUT: "300.0",
}


class ConfigManager(QObject):
    """
    集中配置管理器
    
    优先从数据库读取用户配置，回退到 config.py 默认值。
    配置变更时发出信号通知其他组件。
    """
    
    # 配置变更信号: (key, new_value)
    config_changed = Signal(str, object)
    
    def __init__(self, storage=None):
        """
        初始化配置管理器
        
        Args:
            storage: StorageManager 实例，用于读写数据库
        """
        super().__init__()
        self._storage = storage
        self._cache = {}  # 内存缓存
        logger.info("ConfigManager 初始化完成")
    
    def set_storage(self, storage):
        """设置 StorageManager（延迟注入）"""
        self._storage = storage
        self._cache.clear()  # 清空缓存，重新从数据库读取
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        优先级: 数据库 > config.py 默认值 > 传入的 default
        
        Args:
            key: 配置键
            default: 默认值（当数据库和默认映射都没有时使用）
        
        Returns:
            配置值（自动转换类型）
        """
        # 先检查缓存
        if key in self._cache:
            return self._cache[key]
        
        value = None
        
        # 尝试从数据库读取
        if self._storage:
            try:
                db_value = self._storage.get_setting(key, "")
                if db_value:
                    value = self._parse_value(key, db_value)
            except Exception as e:
                logger.warning(f"从数据库读取配置 {key} 失败: {e}")
        
        # 回退到默认值
        if value is None:
            default_str = DEFAULT_VALUES.get(key, "")
            if default_str:
                value = self._parse_value(key, default_str)
            else:
                value = default
        
        # 缓存结果
        if value is not None:
            self._cache[key] = value
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置值并持久化到数据库
        
        Args:
            key: 配置键
            value: 配置值
        """
        # 序列化值
        str_value = self._serialize_value(value)
        
        # 保存到数据库
        if self._storage:
            try:
                self._storage.set_setting(key, str_value)
                logger.info(f"配置已保存: {key} = {str_value}")
            except Exception as e:
                logger.error(f"保存配置 {key} 失败: {e}")
                return
        
        # 更新缓存
        self._cache[key] = value
        
        # 发出变更信号
        self.config_changed.emit(key, value)
    
    def get_email_send_times(self) -> List[Tuple[int, int]]:
        """
        获取邮件发送时间列表
        
        Returns:
            [(hour, minute), ...] 格式的时间列表
        """
        times_str = self.get(ConfigKey.EMAIL_SEND_TIMES, '["12:00", "22:00"]')
        
        result = []
        try:
            if isinstance(times_str, str):
                times_list = json.loads(times_str)
            else:
                times_list = times_str
            
            for time_str in times_list:
                if isinstance(time_str, str) and ':' in time_str:
                    parts = time_str.split(':')
                    hour = int(parts[0])
                    minute = int(parts[1])
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        result.append((hour, minute))
        except Exception as e:
            logger.warning(f"解析邮件发送时间失败: {e}，使用默认值")
            result = [(12, 0), (22, 0)]
        
        return result if result else [(12, 0), (22, 0)]
    
    def set_email_send_times(self, times: List[Tuple[int, int]]) -> None:
        """
        设置邮件发送时间列表
        
        Args:
            times: [(hour, minute), ...] 格式的时间列表
        """
        times_str_list = [f"{h:02d}:{m:02d}" for h, m in times]
        self.set(ConfigKey.EMAIL_SEND_TIMES, json.dumps(times_str_list))
    
    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数配置值"""
        value = self.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """获取浮点数配置值"""
        value = self.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    
    def _parse_value(self, key: str, str_value: str) -> Any:
        """
        解析字符串值为适当类型
        
        Args:
            key: 配置键（用于判断类型）
            str_value: 字符串值
        
        Returns:
            解析后的值
        """
        if not str_value:
            return None
        
        # JSON 类型的配置
        if key == ConfigKey.EMAIL_SEND_TIMES:
            try:
                return json.loads(str_value)
            except json.JSONDecodeError:
                return str_value
        
        # 整数类型
        int_keys = {
            ConfigKey.VIDEO_MAX_FRAMES,
            ConfigKey.BATCH_DURATION_MINUTES,
            ConfigKey.LOG_MAX_SIZE_MB,
            ConfigKey.LOG_BACKUP_COUNT,
            ConfigKey.LOG_RETENTION_DAYS,
            ConfigKey.DB_POOL_SIZE,
        }
        if key in int_keys:
            try:
                return int(str_value)
            except ValueError:
                return str_value
        
        # 浮点数类型
        float_keys = {
            ConfigKey.API_TIMEOUT,
            ConfigKey.DB_POOL_TIMEOUT,
            ConfigKey.DB_IDLE_TIMEOUT,
        }
        if key in float_keys:
            try:
                return float(str_value)
            except ValueError:
                return str_value
        
        return str_value
    
    def _serialize_value(self, value: Any) -> str:
        """
        序列化值为字符串
        
        Args:
            value: 任意值
        
        Returns:
            字符串表示
        """
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    
    def clear_cache(self) -> None:
        """清空配置缓存"""
        self._cache.clear()
        logger.debug("配置缓存已清空")
