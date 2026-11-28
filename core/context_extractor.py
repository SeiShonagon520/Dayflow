"""
本机结构化上下文提取器（严格三态隐私分类 + 浏览器适配器 + URL 安全校验 + IDE/Office 解析 + 辅助麦克风检测）。

契约要点：
1. 三态分离：
   - SENSITIVE_OR_UNKNOWN：空窗口、未知进程、隐私黑名单/敏感标题、无法确认非私密的浏览器窗口、
     或解码后 URL 路径命中隐私词 -> 封口留空档，绝不触碰 UIA。
   - APP_VERIFIED：已确认非私密，但处于 app_only / 浏览器不受支持 / 地址栏编辑态 / UIA 超时 / 标题格式不匹配。
   - CONTEXT_VERIFIED：structured 模式，已确认非私密且所有提取字段通过二次隐私检查。
2. 彻底禁止保存 page_title、原始 URL 路径/查询串/片段或本机文件绝对路径。
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Callable, Dict, Optional, Set, Tuple
from urllib.parse import unquote, urlsplit

from core.privacy_filter import PrivacyFilter
from core.types import CaptureState, WindowContext
from core.uia_worker import SUPPORTED_BROWSERS
from core.window_tracker import WindowInfo, WindowTracker

logger = logging.getLogger(__name__)

# 所有已知浏览器进程（用于统一执行非私密窗口预检查）
ALL_BROWSER_PROCESSES = {
    "chrome", "msedge", "firefox", "brave", "arc", "opera", "vivaldi", "iexplore",
}

# 受支持浏览器已知的非私密窗口标题后缀（确认窗口非空且非私密态）
_BROWSER_NON_PRIVATE_SUFFIXES = {
    "chrome": ("- google chrome", "— google chrome"),
    "msedge": ("- microsoft\u200b edge", "- microsoft edge", "— microsoft edge"),
    "firefox": ("— mozilla firefox", "- mozilla firefox"),
}

_PRIVATE_BROWSER_MARKERS = (
    "inprivate", "incognito", "private browsing", "in-private",
    "无痕", "私密浏览", "隐私浏览", "隐私窗口", "无痕模式",
)

# 固定应用级默认分类
APP_CATEGORIES: Dict[str, str] = {
    "code": "编程", "cursor": "编程", "windsurf": "编程", "zed": "编程",
    "devenv": "编程", "pycharm64": "编程", "idea64": "编程", "webstorm64": "编程",
    "clion64": "编程", "goland64": "编程", "rider64": "编程", "datagrip64": "编程",
    "windowsterminal": "编程", "powershell": "编程", "pwsh": "编程", "cmd": "编程",
    "postman": "编程",
    "winword": "工作", "excel": "工作", "powerpnt": "工作", "visio": "工作",
    "wps": "工作", "outlook": "工作", "notion": "工作", "figma": "工作",
    "obsidian": "学习", "typora": "学习",
    "ms-teams": "会议", "teams": "会议", "zoom": "会议", "webex": "会议", "wemeetapp": "会议",
    "wechat": "社交", "weixin": "社交", "qq": "社交", "dingtalk": "社交",
    "feishu": "社交", "lark": "社交", "slack": "社交", "discord": "社交", "telegram": "社交",
    "spotify": "娱乐", "cloudmusic": "娱乐", "qqmusic": "娱乐",
    "potplayer": "娱乐", "potplayer64": "娱乐", "vlc": "娱乐",
    "steam": "娱乐", "epicgameslauncher": "娱乐",
}

# 已知会议/通讯前台应用（仅用于辅助麦克风信号校验）
MEETING_CAPABLE_APPS = {
    "wemeetapp", "zoom", "ms-teams", "teams", "webex", "feishu", "lark", "dingtalk",
}

# 域名精确/标签边界分类映射（host == d or host.endswith("." + d)）
DOMAIN_CATEGORIES: Dict[str, str] = {
    "github.com": "编程",
    "gitlab.com": "编程",
    "stackoverflow.com": "编程",
    "docs.rs": "编程",
    "docs.python.org": "编程",
    "developer.mozilla.org": "编程",
    "tauri.app": "编程",
    "npmjs.com": "编程",
    "pypi.org": "编程",
    "crates.io": "编程",
    "localhost": "编程",
    "127.0.0.1": "编程",
    "arxiv.org": "学习",
    "wikipedia.org": "学习",
    "leetcode.cn": "学习",
    "leetcode.com": "学习",
    "kaggle.com": "学习",
    "coursera.org": "学习",
    "notion.so": "工作",
    "figma.com": "工作",
    "linear.app": "工作",
    "docs.google.com": "工作",
    "mail.google.com": "工作",
    "outlook.live.com": "工作",
    "feishu.cn": "工作",
    "meet.google.com": "会议",
    "zoom.us": "会议",
    "meeting.tencent.com": "会议",
    "teams.microsoft.com": "会议",
    "bilibili.com": "娱乐",
    "youtube.com": "娱乐",
    "netflix.com": "娱乐",
    "twitch.tv": "娱乐",
    "douyin.com": "娱乐",
    "iqiyi.com": "娱乐",
    "weibo.com": "娱乐",
    "reddit.com": "娱乐",
    "x.com": "娱乐",
    "twitter.com": "娱乐",
    "discord.com": "社交",
    "web.whatsapp.com": "社交",
}

_MEETING_DOMAINS = {"meet.google.com", "meeting.tencent.com"}
_MEETING_PATH_PREFIXES = (
    ("feishu.cn", "/vc"),
    ("zoom.us", "/j/"),
    ("zoom.us", "/wc/"),
    ("teams.microsoft.com", "/l/meetup-join"),
)

_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_CONTROL_OR_SPACE_RE = re.compile(r"[\x00-\x20\x7f]")

_VS_CODE_APPS = {"code", "cursor", "windsurf", "zed"}
_JETBRAINS_APPS = {"pycharm64", "idea64", "webstorm64", "clion64", "goland64", "rider64", "datagrip64"}
_OFFICE_DOC_APPS = {"winword", "excel", "powerpnt", "wps", "obsidian", "typora"}
_TERMINAL_APPS = {"windowsterminal", "powershell", "pwsh", "cmd"}
_GENERIC_EDITOR_SEGMENTS = {
    "visual studio code", "cursor", "windsurf", "zed", "microsoft word",
    "microsoft excel", "microsoft powerpoint", "wps office", "obsidian",
    "typora", "welcome", "get started", "settings", "untitled",
}


def domain_matches(host: str, rule: str) -> bool:
    """精确匹配或 DNS 标签边界匹配，避免 evilgithub.com 误命中 github.com。"""
    base_host = host.split(":", 1)[0].lower()
    rule_low = rule.lower()
    return base_host == rule_low or base_host.endswith("." + rule_low)


def classify_domain(host: str) -> Optional[str]:
    if not host:
        return None
    for rule, category in DOMAIN_CATEGORIES.items():
        if domain_matches(host, rule):
            return category
    return None


def _is_valid_hostname(host: str) -> bool:
    if not host or len(host) > 253:
        return False
    if host == "localhost":
        return True
    if _IPV4_RE.fullmatch(host):
        return all(0 <= int(part) <= 255 for part in host.split("."))
    if "." not in host:
        return False
    labels = host.split(".")
    return all(_HOST_LABEL_RE.fullmatch(lbl) for lbl in labels)


def sanitize_browser_url(
    raw_url: str,
    privacy_filter: PrivacyFilter,
) -> Tuple[str, Optional[str], bool]:
    """
    严格校验并脱敏浏览器地址栏输入。
    返回 (status, normalized_domain, is_meeting_url):
      - status == "sensitive": 命中隐私关键词，调用方必须升级为 SENSITIVE_OR_UNKNOWN
      - status == "ok": 返回安全规范化 hostname（或 "local-file"）
      - status == "invalid": 无法验证或内部协议，回退为 APP_VERIFIED
    原始路径/查询串/片段绝不返回、绝不落库。
    """
    text = (raw_url or "").strip()
    if not text or len(text) > 2048 or _CONTROL_OR_SPACE_RE.search(text):
        return "invalid", None, False

    lower = text.lower()
    if lower.startswith(("chrome:", "edge:", "about:", "devtools:", "chrome-extension:", "moz-extension:", "view-source:")):
        return "invalid", None, False
    if lower.startswith("file:"):
        # 对解码路径做有界隐私检查，不暴露本机路径
        decoded_file = unquote(lower[:512])
        if any(kw in decoded_file for kw in privacy_filter.title_keywords):
            return "sensitive", None, False
        return "ok", "local-file", False

    # 拒绝含 userinfo/凭据或反斜杠歧义
    candidate = text if "://" in text else f"https://{text}"
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return "invalid", None, False

    if parsed.scheme.lower() not in {"http", "https"}:
        return "invalid", None, False
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        return "invalid", None, False
    if "\\" in parsed.netloc or not parsed.hostname:
        return "invalid", None, False

    host = parsed.hostname.lower().rstrip(".")
    if not _is_valid_hostname(host):
        return "invalid", None, False

    # 内存中对 host + 解码路径（上限 512 字符）执行有界隐私检查
    decoded_check = f"{host}{unquote((parsed.path or '')[:512]).lower()}"
    if any(kw in decoded_check for kw in privacy_filter.title_keywords):
        return "sensitive", None, False

    # 仅 localhost / 127.0.0.1 保留有效端口，其他一律只留纯 hostname
    normalized = host
    if host in {"localhost", "127.0.0.1"} and parsed.port:
        normalized = f"{host}:{parsed.port}"

    path_low = (parsed.path or "").lower()
    is_meeting = any(domain_matches(host, d) for d in _MEETING_DOMAINS) or any(
        domain_matches(host, d) and path_low.startswith(prefix)
        for d, prefix in _MEETING_PATH_PREFIXES
    )
    return "ok", normalized, is_meeting


def _clean_token(value: Optional[str], max_len: int = 64) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(value.replace("●", "").replace("•", "").split()).strip(" -—_|[]()")
    if not cleaned or len(cleaned) <= 1:
        return None
    if cleaned.lower() in _GENERIC_EDITOR_SEGMENTS:
        return None
    return cleaned[:max_len]


def parse_ide_or_office_title(app_name: str, title: str) -> Tuple[Optional[str], Optional[str]]:
    """
    针对明确支持的 IDE / Office / 终端标题格式提取 (project_name, document_name)。
    格式不匹配一律返回 (None, None) 以回退 APP_VERIFIED。
    """
    text = (title or "").strip()
    if not text:
        return None, None

    if app_name in _VS_CODE_APPS:
        # 常见格式：file.py - Dayflow - Visual Studio Code 或 ● file.py - Dayflow [SSH: host] - Cursor
        parts = [p.strip() for p in re.split(r"\s+[—\-]\s+", text) if p.strip()]
        if len(parts) < 2:
            return None, None
        # 末段应为编辑器名称
        if parts[-1].lower() not in {"visual studio code", "cursor", "windsurf", "zed"}:
            return None, None
        core = parts[:-1]
        if len(core) >= 2:
            doc = _clean_token(core[0])
            proj_raw = re.sub(r"\s*\[[^\]]+\]\s*$", "", core[-1])
            proj = _clean_token(proj_raw)
            return proj, doc
        if len(core) == 1:
            proj_raw = re.sub(r"\s*\[[^\]]+\]\s*$", "", core[0])
            return _clean_token(proj_raw), None
        return None, None

    if app_name in _JETBRAINS_APPS:
        # 格式：Project – file.py 或 Project [D:\path] – file.py
        parts = [p.strip() for p in re.split(r"\s+[–—\-]\s+", text) if p.strip()]
        if len(parts) >= 2:
            proj_raw = re.sub(r"\s*\[[^\]]+\]\s*$", "", parts[0])
            proj = _clean_token(proj_raw)
            doc = _clean_token(parts[1])
            return proj, doc
        return None, None

    if app_name == "devenv":
        parts = [p.strip() for p in re.split(r"\s+[—\-]\s+", text) if p.strip()]
        if len(parts) >= 2 and "visual studio" in parts[-1].lower():
            return _clean_token(parts[0]), None
        return None, None

    if app_name in _OFFICE_DOC_APPS:
        parts = [p.strip() for p in re.split(r"\s+[—\-]\s+", text) if p.strip()]
        if len(parts) >= 2:
            doc = _clean_token(parts[0])
            return None, doc
        return None, None

    if app_name in _TERMINAL_APPS:
        # 仅在标题明确给出 Windows 绝对路径（如 D:\github\Dayflow）时提取末级目录名，不保存完整路径
        match = re.search(r"[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*([^\\/:*?\"<>|\r\n]+)", text)
        if match:
            proj = _clean_token(match.group(1))
            return proj, None
        return None, None

    return None, None


class MicrophoneMonitor:
    """
    可选 Windows 麦克风注册表辅助检测器（可缺失信号）。
    任何缺键、权限异常或异常时间戳均返回 None (unknown)，绝不误报。
    """

    _BASE_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

    def __init__(self, cache_ttl_s: float = 3.0):
        self._ttl = cache_ttl_s
        self._last_checked = 0.0
        self._cached: Optional[Set[str]] = None

    def clear_cache(self) -> None:
        self._last_checked = 0.0
        self._cached = None

    def active_apps(self, now_mono: Optional[float] = None) -> Optional[Set[str]]:
        if os.name != "nt":
            return None
        now = time.monotonic() if now_mono is None else now_mono
        if self._last_checked and (now - self._last_checked) < self._ttl:
            return self._cached
        self._last_checked = now
        try:
            import winreg

            active: Set[str] = set()
            for sub_path in (self._BASE_KEY, self._BASE_KEY + r"\NonPackaged"):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_path) as root:
                        count = winreg.QueryInfoKey(root)[0]
                        for i in range(count):
                            sub_name = winreg.EnumKey(root, i)
                            if sub_name == "NonPackaged":
                                continue
                            try:
                                with winreg.OpenKey(root, sub_name) as item:
                                    start_val, _ = winreg.QueryValueEx(item, "LastUsedTimeStart")
                                    stop_val, _ = winreg.QueryValueEx(item, "LastUsedTimeStop")
                                    if int(start_val) > 0 and int(stop_val) == 0:
                                        # NonPackaged 键名以 # 分隔路径，提取末段进程名
                                        tail = sub_name.split("#")[-1].lower()
                                        if tail.endswith(".exe"):
                                            tail = tail[:-4]
                                        if tail:
                                            active.add(tail)
                            except OSError:
                                continue
                except OSError:
                    continue
            self._cached = active
            return active
        except Exception:
            self._cached = None
            return None


class ContextExtractor:
    """严格三态结构化上下文采集器。"""

    def __init__(
        self,
        tracker: WindowTracker,
        privacy: PrivacyFilter,
        *,
        uia_client=None,
        mic_monitor: Optional[MicrophoneMonitor] = None,
        nav_token_provider: Optional[Callable[[], int]] = None,
        settings_gen_provider: Optional[Callable[[], int]] = None,
    ):
        self.tracker = tracker
        self.privacy = privacy
        self.uia_client = uia_client
        self.mic_monitor = mic_monitor or MicrophoneMonitor()
        self._nav_token_provider = nav_token_provider
        self._settings_gen_provider = settings_gen_provider

    def _has_sensitive_field(self, *values: Optional[str]) -> bool:
        if not self.privacy.enabled:
            return False
        for val in values:
            low = (val or "").lower()
            if low and any(kw in low for kw in self.privacy.title_keywords):
                return True
        return False

    def _verify_browser_non_private(self, app_name: str, window_title: str) -> Optional[bool]:
        """
        返回：
        - False: 明确私密窗口或无法排除私密状态 -> 调用方必须返回 SENSITIVE_OR_UNKNOWN
        - True: 已确认非私密窗口
        - None: 不在受支持适配器列表，但标题非空且未命中私密特征（仅允许 APP_VERIFIED）
        """
        title = (window_title or "").strip()
        if not title:
            # 浏览器标题为空时无法确认非私密状态，统一留空档
            return False
        low = title.lower()
        if any(marker in low for marker in _PRIVATE_BROWSER_MARKERS):
            return False
        if app_name in SUPPORTED_BROWSERS:
            suffixes = _BROWSER_NON_PRIVATE_SUFFIXES.get(app_name, ())
            if any(low.endswith(s) for s in suffixes):
                return True
            # 受支持浏览器但标题不匹配已知非私密后缀 -> 无法确认非私密，留空档
            return False
        return None

    def extract(
        self,
        window: Optional[WindowInfo],
        *,
        context_mode: str = "app_only",
        allow_uia: bool = True,
        expected_nav_token: Optional[int] = None,
        expected_settings_gen: Optional[int] = None,
    ) -> WindowContext:
        # 1. 隐私与身份前置门控（Fail-Closed）
        if window is None:
            return WindowContext(state=CaptureState.SENSITIVE_OR_UNKNOWN)

        app_name = window.get_clean_app_name().lower()
        if not app_name or app_name == "unknown":
            return WindowContext(state=CaptureState.SENSITIVE_OR_UNKNOWN)

        if self.privacy.is_sensitive(window):
            return WindowContext(state=CaptureState.SENSITIVE_OR_UNKNOWN)

        friendly_app = self.tracker.get_friendly_app_name(window)
        base_category = APP_CATEGORIES.get(app_name, "其他")

        # 2. 浏览器统一非私密预检（即使在 app_only 模式下，无法确认非私密的浏览器也应留空档）
        browser_non_private: Optional[bool] = None
        if app_name in ALL_BROWSER_PROCESSES:
            browser_non_private = self._verify_browser_non_private(app_name, window.window_title)
            if browser_non_private is False:
                return WindowContext(state=CaptureState.SENSITIVE_OR_UNKNOWN)

        # 3. app_only 模式：绝不持久化标题/域名/项目/文档，仅记录应用级数据
        if context_mode != "structured":
            return WindowContext(
                state=CaptureState.APP_VERIFIED,
                app_name=app_name,
                friendly_app=friendly_app,
                category=base_category,
                source="app_only",
            )

        # 4. 前台会议辅助麦克风信号（仅在前台为已知会议/通讯应用时生效）
        meeting_active = False
        if app_name in MEETING_CAPABLE_APPS:
            active_mic_apps = self.mic_monitor.active_apps()
            if active_mic_apps and any(app_name in m or m in app_name for m in active_mic_apps):
                meeting_active = True

        # 5. 受支持浏览器：经围栏调用独立 UIA 子进程读取地址栏，并严格校验脱敏 URL
        if app_name in ALL_BROWSER_PROCESSES:
            if browser_non_private is True and allow_uia and self.uia_client is not None and window.hwnd:
                nav_before = (
                    expected_nav_token
                    if expected_nav_token is not None
                    else (self._nav_token_provider() if self._nav_token_provider else 0)
                )
                gen_before = (
                    expected_settings_gen
                    if expected_settings_gen is not None
                    else (self._settings_gen_provider() if self._settings_gen_provider else 0)
                )
                raw_url = self.uia_client.query_browser_url(
                    hwnd=window.hwnd,
                    browser=app_name,
                    pid=window.process_id,
                    create_time=window.process_create_time,
                    title=window.window_title,
                )
                # 采样围栏：查询期间若发生导航/切换或设置变更，立即丢弃迟到结果
                nav_after = self._nav_token_provider() if self._nav_token_provider else nav_before
                gen_after = self._settings_gen_provider() if self._settings_gen_provider else gen_before
                if raw_url and nav_after == nav_before and gen_after == gen_before:
                    status, domain, is_meeting_url = sanitize_browser_url(raw_url, self.privacy)
                    if status == "sensitive":
                        return WindowContext(state=CaptureState.SENSITIVE_OR_UNKNOWN)
                    if status == "ok" and domain:
                        category = "会议" if is_meeting_url else (classify_domain(domain) or base_category)
                        return WindowContext(
                            state=CaptureState.CONTEXT_VERIFIED,
                            app_name=app_name,
                            friendly_app=friendly_app,
                            category=category,
                            domain=domain,
                            meeting_active=is_meeting_url,
                            source="uia",
                        )
            return WindowContext(
                state=CaptureState.APP_VERIFIED,
                app_name=app_name,
                friendly_app=friendly_app,
                category=base_category,
                source="app_only",
            )

        # 6. IDE / Office / 终端确定性标题解析（含二次隐私检查）
        project_name, document_name = parse_ide_or_office_title(app_name, window.window_title)
        if self._has_sensitive_field(project_name, document_name):
            return WindowContext(state=CaptureState.SENSITIVE_OR_UNKNOWN)

        if project_name or document_name or meeting_active:
            category = "会议" if meeting_active else base_category
            return WindowContext(
                state=CaptureState.CONTEXT_VERIFIED,
                app_name=app_name,
                friendly_app=friendly_app,
                category=category,
                project_name=project_name,
                document_name=document_name,
                meeting_active=meeting_active,
                source="mic" if meeting_active and not (project_name or document_name) else "title",
            )

        # 7. 未匹配到结构化规则 -> 退回 APP_VERIFIED
        return WindowContext(
            state=CaptureState.APP_VERIFIED,
            app_name=app_name,
            friendly_app=friendly_app,
            category=base_category,
            source="app_only",
        )
