"""
Dayflow Windows - 隐私保护与敏感窗口过滤模块
当检测到密码管理器、私密浏览器或敏感内容时，对录制帧进行模糊/遮罩处理并对标题脱敏
"""
import logging
from typing import Optional, List, Set
import cv2
import numpy as np

import config
from core.window_tracker import WindowInfo

logger = logging.getLogger(__name__)


class PrivacyFilter:
    """
    隐私过滤器
    提供敏感应用/窗口检测、画面遮罩脱敏及窗口标题脱敏能力
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        action: Optional[str] = None,
        app_blacklist: Optional[List[str]] = None,
        title_keywords: Optional[List[str]] = None,
    ):
        self.enabled = config.PRIVACY_PROTECTION_ENABLED if enabled is None else enabled
        self.action = (action or config.PRIVACY_ACTION).lower()  # "blur", "blackout", "pause"
        
        # 敏感应用黑名单（小写存储）
        raw_apps = app_blacklist if app_blacklist is not None else config.PRIVACY_APP_BLACKLIST
        self.app_blacklist: Set[str] = {app.strip().lower() for app in raw_apps if app.strip()}

        # 敏感窗口标题关键词（小写存储）
        raw_keywords = title_keywords if title_keywords is not None else config.PRIVACY_TITLE_KEYWORDS
        self.title_keywords: List[str] = [kw.strip().lower() for kw in raw_keywords if kw.strip()]

    def is_sensitive(self, window_info: Optional[WindowInfo]) -> bool:
        """
        判断当前窗口是否属于隐私敏感内容
        
        Args:
            window_info: 活动窗口信息
            
        Returns:
            bool: True 表示匹配敏感规则
        """
        if not self.enabled or not window_info:
            return False

        # 1. 检查应用进程名
        clean_app = window_info.get_clean_app_name().lower()
        if clean_app in self.app_blacklist:
            return True

        for blocked_app in self.app_blacklist:
            if blocked_app and blocked_app in clean_app:
                return True

        # 2. 检查窗口标题关键词
        title_lower = (window_info.window_title or "").lower()
        if title_lower:
            for keyword in self.title_keywords:
                if keyword in title_lower:
                    return True

        return False

    def sanitize_window_title(self, window_info: Optional[WindowInfo]) -> str:
        """
        获取脱敏后的窗口标题
        若为敏感窗口，返回通用脱敏占位符，避免在 JSON 记录和 LLM 提示词中泄露隐私信息
        """
        if not window_info:
            return ""

        if self.is_sensitive(window_info):
            return "[隐私保护内容]"

        return window_info.window_title

    def mask_frame(self, frame: np.ndarray, action: Optional[str] = None) -> np.ndarray:
        """
        对视频帧执行隐私脱敏遮罩处理
        
        Args:
            frame: 原始图像帧 (BGR numpy 数组)
            action: 遮罩类型 ("blur" 或 "blackout")，默认为初始化设定的 action
            
        Returns:
            np.ndarray: 脱敏后的图像帧
        """
        if frame is None or frame.size == 0:
            return frame

        act = (action or self.action).lower()
        h, w = frame.shape[:2]

        if act == "blackout":
            # 全黑遮罩
            masked = np.zeros_like(frame)
        else:
            # 高斯模糊 / 马赛克磨砂玻璃效果（下采样再上采样 + 模糊，性能开销极低且完全无法辨识）
            small_w = max(w // 24, 16)
            small_h = max(h // 24, 16)
            small = cv2.resize(frame, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
            masked = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
            # 添加适度高斯模糊消除马赛克尖锐边缘
            masked = cv2.GaussianBlur(masked, (25, 25), 0)

        # 绘制居中隐私保护横幅
        banner_text = "Dayflow Privacy Protection Active"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.8, min(w, h) / 1000.0)
        thickness = max(2, int(font_scale * 2.5))
        
        (text_w, text_h), baseline = cv2.getTextSize(banner_text, font, font_scale, thickness)
        center_x = w // 2
        center_y = h // 2

        # 绘制半透明背景底框
        box_pad = 20
        box_left = max(0, center_x - text_w // 2 - box_pad)
        box_top = max(0, center_y - text_h // 2 - box_pad)
        box_right = min(w, center_x + text_w // 2 + box_pad)
        box_bottom = min(h, center_y + text_h // 2 + box_pad)

        overlay = masked.copy()
        cv2.rectangle(overlay, (box_left, box_top), (box_right, box_bottom), (20, 20, 25), -1)
        cv2.addWeighted(overlay, 0.75, masked, 0.25, 0, masked)

        # 绘制提示文字 (金黄色/白色)
        text_x = center_x - text_w // 2
        text_y = center_y + text_h // 2
        cv2.putText(masked, banner_text, (text_x, text_y), font, font_scale, (0, 215, 255), thickness, cv2.LINE_AA)

        return masked
