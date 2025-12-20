"""
Dayflow - 日志轮转管理器
支持文件大小限制、自动轮转、过期清理
"""
import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LogManager:
    """
    日志管理器
    
    功能:
    - 使用 RotatingFileHandler 实现日志轮转
    - 支持可配置的文件大小限制
    - 支持可配置的备份文件数量
    - 支持按保留天数清理过期日志
    """
    
    def __init__(
        self,
        log_dir: Path,
        log_filename: str = "dayflow.log",
        max_size_mb: int = 5,
        backup_count: int = 5,
        retention_days: int = 30,
        log_level: int = logging.INFO
    ):
        """
        初始化日志管理器
        
        Args:
            log_dir: 日志目录路径
            log_filename: 日志文件名
            max_size_mb: 单个日志文件最大大小 (MB)
            backup_count: 保留的备份文件数量
            retention_days: 日志保留天数
            log_level: 日志级别
        """
        self.log_dir = Path(log_dir)
        self.log_filename = log_filename
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.backup_count = backup_count
        self.retention_days = retention_days
        self.log_level = log_level
        
        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self._file_handler: Optional[RotatingFileHandler] = None
        self._console_handler: Optional[logging.StreamHandler] = None
    
    @property
    def log_file_path(self) -> Path:
        """获取主日志文件路径"""
        return self.log_dir / self.log_filename
    
    def setup(self) -> logging.Logger:
        """
        配置并返回根日志记录器
        
        Returns:
            配置好的根日志记录器
        """
        # 获取根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # 清除现有处理器
        root_logger.handlers.clear()
        
        # 日志格式
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        formatter = logging.Formatter(log_format)
        
        # 创建轮转文件处理器
        self._file_handler = self._create_rotating_handler()
        self._file_handler.setFormatter(formatter)
        root_logger.addHandler(self._file_handler)
        
        # 创建控制台处理器
        self._console_handler = logging.StreamHandler()
        self._console_handler.setFormatter(formatter)
        root_logger.addHandler(self._console_handler)
        
        # 降低第三方库日志级别
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        
        logger.info(f"日志管理器已初始化: {self.log_file_path}")
        logger.info(f"日志配置: 最大 {self.max_size_bytes // (1024*1024)}MB, "
                   f"保留 {self.backup_count} 个备份, "
                   f"保留 {self.retention_days} 天")
        
        return root_logger
    
    def _create_rotating_handler(self) -> RotatingFileHandler:
        """
        创建轮转文件处理器
        
        Returns:
            配置好的 RotatingFileHandler
        """
        handler = RotatingFileHandler(
            filename=str(self.log_file_path),
            maxBytes=self.max_size_bytes,
            backupCount=self.backup_count,
            encoding="utf-8"
        )
        return handler
    
    def cleanup_old_logs(self) -> int:
        """
        清理过期日志文件
        
        删除超过 retention_days 天的日志文件
        
        Returns:
            删除的文件数量
        """
        if self.retention_days <= 0:
            return 0
        
        deleted_count = 0
        cutoff_time = datetime.now() - timedelta(days=self.retention_days)
        
        try:
            # 遍历日志目录
            for file_path in self.log_dir.iterdir():
                if not file_path.is_file():
                    continue
                
                # 只处理日志文件 (dayflow.log, dayflow.log.1, dayflow.log.2, ...)
                if not file_path.name.startswith(self.log_filename.replace('.log', '')):
                    continue
                
                if not ('.log' in file_path.name):
                    continue
                
                # 检查文件修改时间
                try:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff_time:
                        file_path.unlink()
                        deleted_count += 1
                        logger.info(f"已删除过期日志: {file_path.name}")
                except OSError as e:
                    logger.warning(f"删除日志文件失败 {file_path}: {e}")
        
        except Exception as e:
            logger.error(f"清理过期日志失败: {e}")
        
        if deleted_count > 0:
            logger.info(f"共清理 {deleted_count} 个过期日志文件")
        
        return deleted_count
    
    def get_log_files(self) -> list:
        """
        获取所有日志文件列表
        
        Returns:
            日志文件路径列表，按修改时间排序（最新在前）
        """
        log_files = []
        
        try:
            for file_path in self.log_dir.iterdir():
                if not file_path.is_file():
                    continue
                
                if not file_path.name.startswith(self.log_filename.replace('.log', '')):
                    continue
                
                if '.log' in file_path.name:
                    log_files.append(file_path)
            
            # 按修改时间排序（最新在前）
            log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        except Exception as e:
            logger.error(f"获取日志文件列表失败: {e}")
        
        return log_files
    
    def get_total_log_size(self) -> int:
        """
        获取所有日志文件的总大小
        
        Returns:
            总大小（字节）
        """
        total_size = 0
        for file_path in self.get_log_files():
            try:
                total_size += file_path.stat().st_size
            except OSError:
                pass
        return total_size
    
    def force_rotate(self) -> bool:
        """
        强制执行日志轮转
        
        Returns:
            是否成功
        """
        if self._file_handler:
            try:
                self._file_handler.doRollover()
                logger.info("已强制执行日志轮转")
                return True
            except Exception as e:
                logger.error(f"强制日志轮转失败: {e}")
                return False
        return False
    
    def close(self) -> None:
        """关闭日志处理器"""
        if self._file_handler:
            self._file_handler.close()
            self._file_handler = None
        
        if self._console_handler:
            self._console_handler.close()
            self._console_handler = None
