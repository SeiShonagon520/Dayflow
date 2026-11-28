"""
Dayflow Windows - API 交互层
使用 OpenAI 兼容格式调用视觉与文本模型接口
"""
import base64
import json
import logging
import re
import secrets
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from urllib.parse import unquote, urlsplit

import httpx
import cv2
import numpy as np

import config
from core.types import Observation, ActivityCard, AppSite, Distraction

logger = logging.getLogger(__name__)

# 系统提示词
TRANSCRIBE_SYSTEM_PROMPT = """你是屏幕活动分析助手。根据截图和窗口信息，描述用户的具体行为。

返回 JSON 格式：
{
  "observations": [
    {"start_ts": 0, "end_ts": 10, "text": "编写 Python 代码，实现用户登录功能"}
  ]
}

规则：
- start_ts/end_ts 是相对秒数
- text 只描述行为（写什么代码、看什么内容、做什么操作），不要写应用名称
- 优先参考窗口标题里的文件名、网页标题、文档名、聊天对象来提高描述精度
- 如果能判断具体正在编辑/查看的文件或页面，请在 text 中自然体现
- 只返回 JSON"""

GENERATE_CARDS_SYSTEM_PROMPT = """你是时间管理助手。根据观察记录生成活动卡片。

JSON 格式：
{
  "cards": [
    {
      "category": "编程",
      "title": "Dayflow 项目开发",
      "summary": "实现用户登录功能，编写单元测试",
      "start_time": "2024-01-01T10:00:00",
      "end_time": "2024-01-01T11:30:00",
      "app_sites": [{"name": "VS Code", "duration_seconds": 5400}],
      "distractions": [],
      "productivity_score": 85
    }
  ]
}

类别定义：
- 编程：写代码、调试、代码审查
- 工作：文档、邮件、项目管理、设计
- 学习：看教程、读文档、做笔记
- 会议：视频会议、语音通话
- 社交：聊天、社交媒体
- 娱乐：视频、游戏、音乐
- 休息：无明显活动
- 其他：无法归类

productivity_score 评分标准：
- 90-100：高度专注的核心工作（编程、写作、设计）
- 70-89：一般工作（邮件、文档、会议）
- 50-69：低效工作（频繁切换、碎片化任务）
- 30-49：轻度娱乐（浏览、社交）
- 0-29：纯娱乐（游戏、视频）

合并规则：连续相同应用且相似活动 → 合并为一张卡片
拆分规则：同一时段内切换不同类型活动 → 拆分为多张卡片

跨批次连续性：
- 如果"前序活动卡片"的最后一张与当前观察记录的开头是同类活动，考虑延续而非新建
- 检查前序卡片的 category 和 title，如果当前活动是其延续，在 title 中体现连续性

只返回 JSON"""


class ProviderAuthorizationError(ValueError):
    """The model service rejected the current credentials."""


class UnreadableChunkError(ValueError):
    """The recorded media has no decodable frame."""


class DayflowBackendProvider:
    """
    心流 API 交互类 (OpenAI 兼容格式)
    使用 Chat Completions 接口进行视频分析
    """

    FILE_HINT_BLACKLIST = {
        "visual studio code", "cursor", "google chrome", "microsoft edge", "firefox",
        "wechat", "qq", "telegram", "discord", "notion", "obsidian", "typora",
        "microsoft word", "microsoft excel", "powerpoint", "outlook",
        "文件资源管理器", "windows terminal", "powershell", "cmd", "unknown"
    }

    def __init__(
        self,
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0
    ):
        raw_url = (api_base_url or config.API_BASE_URL).rstrip("/")
        # 兼容 Ollama：若输入的是 http://localhost:11434 则自动补齐 /v1 OpenAI 端点
        self.is_ollama = "11434" in raw_url or "ollama" in raw_url.lower()
        if self.is_ollama and not raw_url.endswith("/v1"):
            raw_url = f"{raw_url}/v1"

        self.api_base_url = raw_url
        self.api_key = config.API_KEY if api_key is None else api_key
        self.model = model or config.API_MODEL
        # 本地模型通常耗时较长，放宽超时时间
        if self.is_ollama and timeout == 120.0:
            self.timeout = 180.0
        else:
            self.timeout = timeout

        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> dict:
        """请求头"""
        auth = self.api_key or ("ollama" if self.is_ollama else "")
        h = {"Content-Type": "application/json"}
        if auth:
            h["Authorization"] = f"Bearer {auth}"
        return h

    async def _get_client(self, pre_send_hook=None) -> httpx.AsyncClient:
        """获取或创建异步 HTTP 客户端"""
        if pre_send_hook is not None:
            return httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers=self.headers,
                event_hooks={"request": [pre_send_hook]},
            )
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

    @staticmethod
    def _spread(items, limit):
        if len(items) <= limit:
            return list(items)
        if limit <= 1:
            return list(items[:limit])
        return [items[round(i * (len(items) - 1) / (limit - 1))] for i in range(limit)]

    def _extract_frames_from_video(
        self, video_path: str, max_frames: int = 4, diff_threshold: float = 2.5,
        window_records: Optional[List[Dict]] = None,
    ) -> List[str]:
        """Reserve frames for window switches, then fill the budget with visual changes."""
        if max_frames < 1:
            return []
        capture = cv2.VideoCapture(video_path)
        try:
            total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            if total < 1:
                return []
            fps = capture.get(cv2.CAP_PROP_FPS) or 1
            events = {0}
            if np.isfinite(fps) and fps > 0:
                for record in window_records or ():
                    timestamp = record.get("timestamp")
                    if isinstance(timestamp, (int, float)) and np.isfinite(timestamp) and timestamp >= 0:
                        # Use the frame closest to the window event.
                        events.add(min(total - 1, round(timestamp * fps)))
            anchors = self._spread(sorted(events), max_frames)
            grid = self._spread(range(total), 2 * max_frames)
            candidates = sorted(set(anchors) | set(grid))
            encoded = {}
            previous = None
            for index in candidates:
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                thumb = cv2.cvtColor(cv2.resize(frame, (64, 36)), cv2.COLOR_BGR2GRAY)
                if index not in anchors and previous is not None and diff_threshold > 0:
                    if float(np.mean(cv2.absdiff(thumb, previous))) < diff_threshold:
                        continue
                previous = thumb
                height, width = frame.shape[:2]
                scale = min(1.0, 1280 / width, 720 / height)
                if scale < 1:
                    frame = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
                ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    encoded[index] = base64.b64encode(jpeg).decode("ascii")
            selected = [index for index in anchors if index in encoded]
            rest = [index for index in encoded if index not in selected]
            selected.extend(self._spread(rest, max_frames - len(selected)))
            return [encoded[index] for index in sorted(selected)]
        finally:
            capture.release()

    def _extract_message_content(self, message_content) -> str:
        """兼容不同 OpenAI/Gemini 兼容服务的 message.content 返回格式。"""
        if isinstance(message_content, str):
            return message_content

        if isinstance(message_content, list):
            parts = []
            for item in message_content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    # 常见兼容格式：{"type":"text","text":"..."}
                    text = item.get("text")
                    if text:
                        parts.append(text)
            return "\n".join(parts).strip()

        if message_content is None:
            return ""

        return str(message_content)

    def _extract_file_hint(self, window_title: Optional[str], app_name: Optional[str] = None) -> Optional[str]:
        """从窗口标题中提取较像“文件名/页面标题/文档名”的线索。"""
        if not window_title:
            return None

        title = unquote(str(window_title)).strip()
        if not title:
            return None

        # 常见编辑器/浏览器标题分隔符
        candidates = [seg.strip(" -—_|•·[]()") for seg in re.split(r"\s*[\-|—|_|·|•|:：]\s*", title) if seg.strip()]
        if not candidates:
            candidates = [title]

        app_name_norm = (app_name or "").strip().lower()

        scored = []
        for part in candidates:
            part_norm = part.strip().lower()
            if not part_norm:
                continue
            if len(part_norm) <= 1:
                continue
            if part_norm == app_name_norm:
                continue
            if part_norm in self.FILE_HINT_BLACKLIST:
                continue

            score = 0
            if re.search(r"\.[a-z0-9]{1,8}$", part_norm):
                score += 4  # 像文件名
            if any(ch in part for ch in ('/', '\\')):
                score += 3  # 像路径
            if re.search(r"[\u4e00-\u9fffA-Za-z0-9].{2,}", part):
                score += 1
            if len(part) >= 6:
                score += 1
            if 'github' in app_name_norm or 'code' in app_name_norm or 'cursor' in app_name_norm:
                score += 1

            scored.append((score, part.strip()))

        if not scored:
            return None

        best_score, best_part = max(scored, key=lambda x: x[0])
        if best_score < 2:
            return None

        return best_part[:200]

    async def _chat_completion(
        self,
        messages: List[dict],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        pre_send_hook=None,
    ) -> str:
        """
        调用 Chat Completions API
        """
        ephemeral = pre_send_hook is not None
        client = await self._get_client(pre_send_hook=pre_send_hook)

        request_body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096
        }

        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens

        try:
            response = await client.post(
                f"{self.api_base_url}/chat/completions",
                json=request_body
            )
            response.raise_for_status()

            result = response.json()
            if isinstance(result, dict):
                if result.get("status") in ("434", 434) or "invalid apikey" in str(result).lower():
                    raise ProviderAuthorizationError("API Key 无效或已过期，请前往「设置」页面检查并更新")
                if "error" in result and result["error"]:
                    err = result["error"]
                    err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    raise ValueError(f"接口返回错误: {err_msg}")

            choices = result.get("choices") or []
            if not choices:
                raise ValueError(f"响应中缺少 choices: {result}")

            message = choices[0].get("message") or {}
            content = self._extract_message_content(message.get("content"))
            if content:
                return content

            fallback_text = choices[0].get("text") or result.get("output_text") or ""
            if fallback_text:
                return fallback_text

            raise ValueError(f"无法从响应中提取文本内容: {result}")

        except httpx.HTTPStatusError as e:
            logger.error("模型 HTTP 请求失败: %s", e.response.status_code)
            raise
        except Exception as e:
            logger.error("模型请求异常: %s", type(e).__name__)
            raise
        finally:
            if ephemeral:
                await client.aclose()

    async def transcribe_video(
        self,
        video_path: str,
        duration: float,
        prompt: Optional[str] = None,
        window_records: Optional[List[Dict]] = None
    ) -> List[Observation]:
        """
        分析视频切片，获取观察记录

        Args:
            video_path: 视频文件路径
            duration: 视频时长（秒）
            prompt: 额外提示词（可选）
            window_records: 窗口记录列表（可选）

        Returns:
            List[Observation]: 观察记录列表
        """
        video_file = Path(video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 提取视频帧
        frames = self._extract_frames_from_video(video_path, max_frames=4, window_records=window_records)
        if not frames:
            raise UnreadableChunkError("无法从视频提取帧")

        # 构建窗口信息文本（包含窗口标题/文件名/页面标题）
        window_info_text = ""
        if window_records:
            window_info_text = "\n\n窗口信息（窗口标题里可能包含文件名、网页标题、聊天对象、文档名）：\n"
            # 按时间段聚合相同的应用
            current_app = None
            current_title = None
            current_start = 0
            for record in window_records:
                app_name = record.get("app_name", "Unknown")
                window_title = record.get("window_title", "")
                if app_name != current_app or window_title != current_title:
                    if current_app:
                        title_part = f": {current_title}" if current_title else ""
                        window_info_text += f"- [{current_start:.0f}s - {record['timestamp']:.0f}s] {current_app}{title_part}\n"
                    current_app = app_name
                    current_title = window_title
                    current_start = record.get("timestamp", 0)
            # 添加最后一个
            if current_app:
                title_part = f": {current_title}" if current_title else ""
                window_info_text += f"- [{current_start:.0f}s - {duration:.0f}s] {current_app}{title_part}\n"

        # 构建消息内容（包含多张图片）
        content = []
        content.append({
            "type": "text",
            "text": f"以下是一段 {duration:.0f} 秒屏幕录制的 {len(frames)} 个关键帧，请分析用户的活动。{window_info_text}{prompt or ''}"
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

        response_text = await self._chat_completion(messages)
        observations = self._parse_observations_from_text(response_text, duration)
        if window_records and observations:
            observations = self._apply_window_records(observations, window_records, duration)
        return observations

    def _apply_window_records(
        self,
        observations: List[Observation],
        window_records: List[Dict],
        duration: float
    ) -> List[Observation]:
        """
        用真实窗口记录覆盖 AI 返回的 app_name

        根据时间戳匹配，找到每个 observation 对应时间段内使用最多的应用
        """
        if not window_records:
            return observations

        # 预处理：构建时间段到应用的映射
        # 格式: [(start_ts, end_ts, app_name, window_title), ...]
        time_segments = []
        current_app = None
        current_title = None
        current_start = 0

        for record in window_records:
            app_name = record.get("app_name", "Unknown")
            window_title = record.get("window_title", "")
            timestamp = record.get("timestamp", 0)

            if app_name != current_app:
                if current_app:
                    time_segments.append((current_start, timestamp, current_app, current_title))
                current_app = app_name
                current_title = window_title
                current_start = timestamp

        # 添加最后一个时间段
        if current_app:
            time_segments.append((current_start, duration, current_app, current_title))

        # 为每个 observation 找到对应的应用
        for obs in observations:
            obs_start = obs.start_ts
            obs_end = obs.end_ts

            # 统计这个时间段内各应用的占用时长
            app_durations: Dict[str, float] = {}
            app_titles: Dict[str, str] = {}

            for seg_start, seg_end, app_name, window_title in time_segments:
                # 计算重叠时间
                overlap_start = max(obs_start, seg_start)
                overlap_end = min(obs_end, seg_end)

                if overlap_end > overlap_start:
                    overlap_duration = overlap_end - overlap_start
                    app_durations[app_name] = app_durations.get(app_name, 0) + overlap_duration
                    if app_name not in app_titles:
                        app_titles[app_name] = window_title

            # 找到占用时间最长的应用
            if app_durations:
                main_app = max(app_durations, key=app_durations.get)
                obs.app_name = main_app
                obs.window_title = app_titles.get(main_app, obs.window_title)
                obs.file_hint = self._extract_file_hint(obs.window_title, main_app)
                logger.debug(f"后处理: [{obs_start:.0f}s-{obs_end:.0f}s] app_name -> {main_app}, file_hint -> {obs.file_hint}")

        return observations

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
            extras = []
            if obs.app_name:
                extras.append(f"应用: {obs.app_name}")
            if obs.file_hint:
                extras.append(f"文件/页面线索: {obs.file_hint}")
            elif obs.window_title:
                extras.append(f"窗口标题: {obs.window_title[:120]}")
            if extras:
                obs_text += f" ({'；'.join(extras)})"
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

        response_text = await self._chat_completion(messages)
        return self._parse_cards_from_text(response_text, start_time)

    async def generate_report_insights(self, summary: str, evidence: list[dict]) -> str:
        """Generate a brief interpretation limited to the displayed evidence."""
        messages = [
            {"role": "system", "content": (
                "你整理个人活动日报。写 1 到 4 条简短观察，每条占一行，以 - 开头，并用 [活动 #ID] 标注依据，"
                "只能使用输入列出的 ID。区分观察与推断，应用打开不等于任务完成。"
                "保留本机统计口径，避免重复计分或编造任务产出。"
            )},
            {"role": "user", "content": summary + "\n\n相关活动：\n" + json.dumps(evidence, ensure_ascii=False)},
        ]
        response = (await self._chat_completion(messages, temperature=0.2, max_tokens=500)).strip()
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        allowed = {item["id"] for item in evidence}
        if len(response) > 2400 or not 1 <= len(lines) <= 4:
            raise ValueError("补充内容超出范围")
        for line in lines:
            references = {int(value) for value in re.findall(r"\[活动 #(\d+)\]", line)}
            if not line.startswith("- ") or not references or not references <= allowed:
                raise ValueError("补充内容缺少有效活动依据")
        return response

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
                        window_title=item.get("window_title"),
                        file_hint=item.get("file_hint")
                    )
                    observations.append(obs)
        except json.JSONDecodeError as e:
            logger.warning("观察记录 JSON 解析失败: %s", e.msg)

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

    async def refine_local_cards(
        self,
        cards_payload: List[dict],
        *,
        max_tokens: int = 1024,
        pre_send_hook=None,
    ) -> List[dict]:
        """纯文本精炼已封口本机卡片（仅接收最小白名单应用与时长，不传图像）。"""
        if not cards_payload:
            return []
        system_prompt = (
            "你是个人时间记录整理助手。仅根据输入的脱敏应用类别与时长，为每张活动卡片生成简洁客观的中文标题、"
            "简短摘要、规范类别与 1 到 100 的专注评分。禁止编造输入未提及的文件名、网页内容或任务产出。\n"
            "类别只能从：编程、工作、学习、会议、社交、娱乐、休息、其他 中选择。\n"
            '只返回严格 JSON：{"cards":[{"id":1,"category":"编程","title":"...","summary":"...","productivity_score":80}]}'
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"cards": cards_payload}, ensure_ascii=False)},
        ]
        response = await self._chat_completion(
            messages,
            temperature=0.2,
            max_tokens=max_tokens,
            pre_send_hook=pre_send_hook,
        )
        match = re.search(r"\{[\s\S]*\}", response)
        if not match:
            raise ValueError("精炼响应缺少 JSON")
        data = json.loads(match.group())
        items = data.get("cards")
        if not isinstance(items, list):
            raise ValueError("精炼响应缺少 cards 列表")
        return items

    async def test_connection(self, require_vision: bool = True) -> tuple[bool, str]:
        """Verify model input capability (image for visual mode, synthetic JSON for local text mode)."""
        local = urlsplit(self.api_base_url).hostname in {"localhost", "127.0.0.1", "::1"}
        if not self.api_key and not local:
            return False, "请填写模型服务的接口密钥，或选择本机 Ollama"
        challenge = str(1000 + secrets.randbelow(9000))
        if require_vision:
            image = np.full((104, 288, 3), 255, dtype=np.uint8)
            cv2.putText(image, challenge, (26, 76), cv2.FONT_HERSHEY_SIMPLEX, 2.4, (18, 35, 65), 4, cv2.LINE_AA)
            ok, png = cv2.imencode(".png", image)
            if not ok:
                return False, "生成测试样图失败"
            encoded = base64.b64encode(png).decode("ascii")
            content = [
                {"type": "text", "text": '读出样图上的四位数字。请只返回 JSON，字段名为 code，值是图片中的四位数字。'},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "low"}},
            ]
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{
                "role": "user",
                "content": f'请只返回严格 JSON，字段名为 code，值为 "{challenge}"，不要包含其他文字。',
            }]
        try:
            response = await self._chat_completion(messages, temperature=0, max_tokens=64)
            result = re.search(r"\{[^{}]*\}", response)
            if result:
                value = json.loads(result.group()).get("code")
                if str(value) == challenge:
                    return True, ("模型通过了测试样图识别" if require_vision else "模型通过了纯文本连接与 JSON 响应测试")
            return False, (
                "服务已连通，模型未能正确识别样图，请选择支持图片的模型"
                if require_vision
                else "服务已连通，但模型未能按要求返回纯文本 JSON 挑战码"
            )
        except (json.JSONDecodeError, AttributeError):
            return False, ("模型未按要求返回可解析的识图结果" if require_vision else "模型未按要求返回可解析的 JSON 结果")
        except ProviderAuthorizationError:
            return False, "接口密钥无效或已过期"
        except httpx.HTTPStatusError as error:
            return False, (
                f"{'识图' if require_vision else '文本'}请求失败（HTTP {error.response.status_code}），请核对模型与服务设置"
            )
        except httpx.ConnectError:
            return False, "无法连接模型服务，请确认地址正确且服务已启动"
        except httpx.TimeoutException:
            return False, ("识图测试超时，请重试" if require_vision else "连接测试超时，请重试")
        except Exception:
            return False, ("识图测试未通过，请检查接口和模型名称" if require_vision else "文本连接测试未通过，请检查接口和模型名称")
