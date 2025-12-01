"""
Dayflow Windows - API 交互层
使用 OpenAI 兼容格式调用心流 API
"""
import asyncio
import base64
import json
import logging
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime

import httpx
import cv2

import config
from core.types import Observation, ActivityCard, AppSite, Distraction

logger = logging.getLogger(__name__)

# 系统提示词
TRANSCRIBE_SYSTEM_PROMPT = """你是一个屏幕活动分析助手。分析用户提供的屏幕截图序列，识别用户正在进行的活动。

请以 JSON 格式返回观察记录列表，格式如下：
{
  "observations": [
    {
      "start_ts": 0,
      "end_ts": 10,
      "text": "用户正在使用 VS Code 编写 Python 代码",
      "app_name": "Visual Studio Code",
      "window_title": "main.py - Dayflow"
    }
  ]
}

注意：
- start_ts 和 end_ts 是相对于视频开始的秒数
- 识别出具体的应用程序名称和窗口标题
- 描述用户的具体操作行为
- 只返回 JSON，不要其他内容"""

GENERATE_CARDS_SYSTEM_PROMPT = """你是一个时间管理助手。根据屏幕活动观察记录，生成时间轴活动卡片。

请以 JSON 格式返回活动卡片列表，格式如下：
{
  "cards": [
    {
      "category": "工作",
      "title": "Python 开发",
      "summary": "使用 VS Code 进行 Dayflow 项目的 Python 开发工作",
      "start_time": "2024-01-01T10:00:00",
      "end_time": "2024-01-01T11:30:00",
      "app_sites": [
        {"name": "VS Code", "duration_seconds": 5400}
      ],
      "distractions": [],
      "productivity_score": 85
    }
  ]
}

类别包括：工作、学习、编程、会议、娱乐、社交、休息、其他
productivity_score 范围 0-100，代表生产力水平
只返回 JSON，不要其他内容"""


class DayflowBackendProvider:
    """
    心流 API 交互类 (OpenAI 兼容格式)
    使用 Chat Completions 接口进行视频分析
    """
    
    def __init__(
        self,
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0
    ):
        self.api_base_url = (api_base_url or config.API_BASE_URL).rstrip("/")
        self.api_key = api_key or config.API_KEY
        self.model = model or config.API_MODEL
        self.timeout = timeout
        
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def headers(self) -> dict:
        """请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建异步 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers=self.headers
            )
        return self._client
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _extract_frames_from_video(self, video_path: str, max_frames: int = 10) -> List[str]:
        """
        从视频中提取关键帧并编码为 base64
        
        Args:
            video_path: 视频文件路径
            max_frames: 最大提取帧数
            
        Returns:
            List[str]: base64 编码的图片列表
        """
        frames_base64 = []
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"无法打开视频文件: {video_path}")
            return frames_base64
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            cap.release()
            return frames_base64
        
        # 均匀采样帧
        frame_indices = [int(i * total_frames / max_frames) for i in range(max_frames)]
        
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            
            # 压缩图片以减少传输大小
            frame = cv2.resize(frame, (1280, 720))
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            base64_image = base64.b64encode(buffer).decode('utf-8')
            frames_base64.append(base64_image)
        
        cap.release()
        return frames_base64
    
    async def _chat_completion(
        self,
        messages: List[dict],
        temperature: float = 0.3
    ) -> str:
        """
        调用 Chat Completions API
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            
        Returns:
            str: 模型返回的内容
        """
        client = await self._get_client()
        
        request_body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096
        }
        
        try:
            response = await client.post(
                f"{self.api_base_url}/chat/completions",
                json=request_body
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except httpx.HTTPStatusError as e:
            logger.error(f"API 请求失败: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"API 请求异常: {e}")
            raise
    
    async def transcribe_video(
        self,
        video_path: str,
        duration: float,
        prompt: Optional[str] = None
    ) -> List[Observation]:
        """
        分析视频切片，获取观察记录
        
        Args:
            video_path: 视频文件路径
            duration: 视频时长（秒）
            prompt: 额外提示词（可选）
            
        Returns:
            List[Observation]: 观察记录列表
        """
        video_file = Path(video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        # 提取视频帧
        frames = self._extract_frames_from_video(video_path, max_frames=8)
        if not frames:
            logger.warning(f"无法从视频提取帧: {video_path}")
            return []
        
        # 构建消息内容（包含多张图片）
        content = []
        content.append({
            "type": "text",
            "text": f"以下是一段 {duration:.0f} 秒屏幕录制的 {len(frames)} 个关键帧，请分析用户的活动。{prompt or ''}"
        })
        
        for i, frame_base64 in enumerate(frames):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{frame_base64}",
                    "detail": "low"
                }
            })
        
        messages = [
            {"role": "system", "content": TRANSCRIBE_SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ]
        
        try:
            response_text = await self._chat_completion(messages)
            return self._parse_observations_from_text(response_text, duration)
        except Exception as e:
            logger.error(f"视频分析失败: {e}")
            return []
    
    async def generate_activity_cards(
        self,
        observations: List[Observation],
        context_cards: Optional[List[ActivityCard]] = None,
        start_time: Optional[datetime] = None,
        prompt: Optional[str] = None
    ) -> List[ActivityCard]:
        """
        根据观察记录生成时间轴卡片
        
        Args:
            observations: 观察记录列表
            context_cards: 前序卡片（用于上下文）
            start_time: 开始时间
            prompt: 额外提示词（可选）
            
        Returns:
            List[ActivityCard]: 活动卡片列表
        """
        if not observations:
            return []
        
        # 构建观察记录文本
        obs_text = "观察记录：\n"
        for obs in observations:
            obs_text += f"- [{obs.start_ts:.0f}s - {obs.end_ts:.0f}s] {obs.text}"
            if obs.app_name:
                obs_text += f" (应用: {obs.app_name})"
            obs_text += "\n"
        
        # 添加时间上下文
        if start_time:
            obs_text += f"\n录制开始时间: {start_time.isoformat()}"
        
        # 添加前序卡片上下文
        if context_cards:
            obs_text += "\n\n前序活动卡片：\n"
            for card in context_cards[-3:]:  # 只取最近3个
                obs_text += f"- {card.category}: {card.title}\n"
        
        if prompt:
            obs_text += f"\n{prompt}"
        
        messages = [
            {"role": "system", "content": GENERATE_CARDS_SYSTEM_PROMPT},
            {"role": "user", "content": obs_text}
        ]
        
        try:
            response_text = await self._chat_completion(messages)
            return self._parse_cards_from_text(response_text, start_time)
        except Exception as e:
            logger.error(f"卡片生成失败: {e}")
            return []
    
    def _parse_observations_from_text(self, text: str, duration: float) -> List[Observation]:
        """从文本响应中解析观察记录"""
        observations = []
        
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                items = data.get("observations", [])
                
                for item in items:
                    obs = Observation(
                        start_ts=float(item.get("start_ts", 0)),
                        end_ts=float(item.get("end_ts", duration)),
                        text=item.get("text", ""),
                        app_name=item.get("app_name"),
                        window_title=item.get("window_title")
                    )
                    observations.append(obs)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}, 原文: {text[:200]}")
            # 如果 JSON 解析失败，创建一个基于整段文本的观察记录
            observations.append(Observation(
                start_ts=0,
                end_ts=duration,
                text=text[:500]
            ))
        
        return observations
    
    def _parse_cards_from_text(self, text: str, start_time: Optional[datetime]) -> List[ActivityCard]:
        """从文本响应中解析活动卡片"""
        cards = []
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                items = data.get("cards", [])
                
                for item in items:
                    # 解析时间
                    card_start = None
                    card_end = None
                    
                    if item.get("start_time"):
                        try:
                            card_start = datetime.fromisoformat(item["start_time"].replace("Z", "+00:00"))
                        except:
                            card_start = start_time
                    else:
                        card_start = start_time
                    
                    if item.get("end_time"):
                        try:
                            card_end = datetime.fromisoformat(item["end_time"].replace("Z", "+00:00"))
                        except:
                            pass
                    
                    # 解析应用列表
                    app_sites = []
                    for app in item.get("app_sites", []):
                        app_sites.append(AppSite(
                            name=app.get("name", ""),
                            duration_seconds=app.get("duration_seconds", 0)
                        ))
                    
                    # 解析分心记录
                    distractions = []
                    for dist in item.get("distractions", []):
                        distractions.append(Distraction(
                            description=dist.get("description", ""),
                            timestamp=dist.get("timestamp", 0),
                            duration_seconds=dist.get("duration_seconds", 0)
                        ))
                    
                    card = ActivityCard(
                        category=item.get("category", "其他"),
                        title=item.get("title", "未命名活动"),
                        summary=item.get("summary", ""),
                        start_time=card_start,
                        end_time=card_end,
                        app_sites=app_sites,
                        distractions=distractions,
                        productivity_score=float(item.get("productivity_score", 0))
                    )
                    cards.append(card)
                    
        except json.JSONDecodeError as e:
            logger.warning(f"卡片 JSON 解析失败: {e}")
        
        return cards
    
    async def health_check(self) -> bool:
        """检查 API 连接状态"""
        try:
            messages = [{"role": "user", "content": "hi"}]
            await self._chat_completion(messages)
            return True
        except Exception as e:
            logger.warning(f"API 健康检查失败: {e}")
            return False
    
    async def test_connection(self) -> tuple[bool, str]:
        """
        测试 API 连接
        
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        if not self.api_key:
            return False, "API Key 未配置"
        
        try:
            messages = [{"role": "user", "content": "你好，请回复'测试成功'"}]
            response = await self._chat_completion(messages)
            return True, f"连接成功！模型: {self.model}\n回复: {response[:100]}"
        except httpx.HTTPStatusError as e:
            return False, f"HTTP 错误 {e.response.status_code}: {e.response.text[:200]}"
        except httpx.ConnectError:
            return False, "连接失败：无法连接到服务器"
        except httpx.TimeoutException:
            return False, "连接超时"
        except Exception as e:
            return False, f"错误: {str(e)}"


# 便捷函数：同步调用
def transcribe_video_sync(video_path: str, duration: float, **kwargs) -> List[Observation]:
    """同步版本的视频分析"""
    provider = DayflowBackendProvider(**kwargs)
    try:
        return asyncio.run(provider.transcribe_video(video_path, duration))
    finally:
        asyncio.run(provider.close())


def generate_cards_sync(
    observations: List[Observation],
    context_cards: Optional[List[ActivityCard]] = None,
    **kwargs
) -> List[ActivityCard]:
    """同步版本的卡片生成"""
    provider = DayflowBackendProvider(**kwargs)
    try:
        return asyncio.run(provider.generate_activity_cards(observations, context_cards))
    finally:
        asyncio.run(provider.close())
