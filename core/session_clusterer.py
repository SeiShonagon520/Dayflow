"""
本机任务会话聚类与分段投影规则（冲突优先 + 精确分段记账）。

核心不变量：
1. 会话保留已验证上下文（verified_project / verified_document / verified_domain / verified_meeting），
   中间短时上下文缺失（APP_VERIFIED）绝不擦除已有值，确保 `项目 P -> 缺失 -> 项目 Q` 必拆卡。
2. 冲突优先于 30 秒分心吸收：任何与当前会话已验证上下文冲突的切换立即拆卡，绝不吸收。
3. card_segments 完整无重叠覆盖卡片 [start_time, end_time)。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from core.activity_time import local_time
from core.types import ActivityCard, ActivitySegment, AppSite, CaptureState, WindowContext


@dataclass
class ActiveSession:
    card: ActivityCard
    session_token: str
    app_name: str
    friendly_app: str
    started_mono: float
    verified_project: Optional[str] = None
    verified_document: Optional[str] = None
    verified_domain: Optional[str] = None
    verified_meeting: bool = False
    documents: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    segments: List[ActivitySegment] = field(default_factory=list)


def has_context_conflict(session: ActiveSession, ctx: WindowContext) -> bool:
    """检查新观测是否与会话已验证上下文存在明确冲突。"""
    if ctx.state != CaptureState.CONTEXT_VERIFIED:
        return False

    # 会议状态冲突（已验证非会议 <-> 已验证会议）
    if ctx.meeting_active != session.verified_meeting and (ctx.meeting_active or session.verified_meeting):
        return True

    # 项目名冲突
    if ctx.project_name and session.verified_project:
        if ctx.project_name.lower() != session.verified_project.lower():
            return True

    # 域名冲突
    if ctx.domain and session.verified_domain:
        if ctx.domain.lower() != session.verified_domain.lower():
            return True

    # 文档名冲突：仅在没有共享相同 project_name 时视为冲突（同一 IDE 项目内切换文件属同一项目任务）
    same_project = bool(
        ctx.project_name
        and session.verified_project
        and ctx.project_name.lower() == session.verified_project.lower()
    )
    if not same_project and ctx.document_name and session.verified_document:
        if ctx.document_name.lower() != session.verified_document.lower():
            return True

    # 不同维度的已验证上下文冲突（例如正在做项目 P，突然切到已验证域名或独立文档）
    if session.verified_project and ctx.domain and not ctx.project_name:
        return True
    if session.verified_domain and (ctx.project_name or ctx.document_name) and not ctx.domain:
        return True

    return False


def can_merge_context(session: ActiveSession, ctx: WindowContext) -> bool:
    """
    严格合并条件：
    1. 存在已验证上下文冲突 -> 必拆卡；
    2. 同应用且无冲突 -> 合并；
    3. 跨应用 -> 仅在双方具备已验证且一致的非空 project_name 时合并。
    """
    if has_context_conflict(session, ctx):
        return False
    if ctx.app_name == session.app_name:
        return True
    if (
        ctx.state == CaptureState.CONTEXT_VERIFIED
        and ctx.project_name
        and session.verified_project
        and ctx.project_name.lower() == session.verified_project.lower()
    ):
        return True
    return False


def should_enter_distraction_candidate(
    session: ActiveSession,
    ctx: WindowContext,
    *,
    session_duration_s: float,
    min_primary_seconds: float = 60.0,
) -> bool:
    """
    冲突优先于 30 秒吸收：
    - 只要新窗口带有与主会话冲突的已验证上下文（如项目 Q / 独立域名 / 文档 / 会议），一律直接拆卡，不进入吸收缓冲。
    - 仅当主会话已持续 >= 60s，且切往的是无冲突已验证工作上下文的异类应用（如社交/娱乐/其他或 app_only 异类应用），
      才进入 30s 候选分心缓冲。
    """
    if session_duration_s < min_primary_seconds:
        return False
    if has_context_conflict(session, ctx):
        return False
    if ctx.state == CaptureState.CONTEXT_VERIFIED and (
        ctx.project_name or ctx.document_name or ctx.domain or ctx.meeting_active
    ):
        return False
    return True


def compute_session_key(ctx: WindowContext) -> str:
    if ctx.state == CaptureState.CONTEXT_VERIFIED:
        if ctx.meeting_active:
            return f"meeting:{ctx.app_name}"
        if ctx.project_name:
            return f"project:{ctx.project_name.lower()}"
        if ctx.domain:
            return f"domain:{ctx.domain.lower()}"
        if ctx.document_name:
            return f"doc:{ctx.app_name}:{ctx.document_name.lower()}"
    return f"app:{ctx.app_name}"


def enrich_session_metadata(session: ActiveSession, ctx: WindowContext, context_mode: str) -> None:
    """单调补全会话已验证上下文（缺失不擦除），并刷新卡片语义展示字段。"""
    if ctx.state == CaptureState.CONTEXT_VERIFIED:
        if ctx.project_name and not session.verified_project:
            session.verified_project = ctx.project_name
        if ctx.document_name and not session.verified_document:
            session.verified_document = ctx.document_name
        if ctx.domain and not session.verified_domain:
            session.verified_domain = ctx.domain
        if ctx.meeting_active:
            session.verified_meeting = True
        if ctx.document_name and ctx.document_name not in session.documents:
            session.documents.append(ctx.document_name)
        if ctx.domain and ctx.domain not in session.domains:
            session.domains.append(ctx.domain)
        if ctx.category and ctx.category != "其他" and session.card.category == "其他":
            session.card.category = ctx.category
        if ctx.meeting_active:
            session.card.category = "会议"

    if context_mode != "structured":
        session.card.title = session.friendly_app
        session.card.summary = ""
        session.card.session_key = f"app:{session.app_name}"
        return

    category = session.card.category or "其他"
    if session.verified_meeting:
        session.card.title = f"{session.friendly_app} · 会议"
        session.card.session_key = f"meeting:{session.app_name}"
    elif session.verified_project:
        session.card.title = f"{session.verified_project} · {category}"
        session.card.session_key = f"project:{session.verified_project.lower()}"
    elif session.verified_domain:
        session.card.title = f"{session.verified_domain} · {category}"
        session.card.session_key = f"domain:{session.verified_domain.lower()}"
    elif session.verified_document:
        session.card.title = f"{session.verified_document} · {session.friendly_app}"
        session.card.session_key = f"doc:{session.app_name}:{session.verified_document.lower()}"
    else:
        session.card.title = session.friendly_app
        session.card.session_key = f"app:{session.app_name}"

    parts = []
    if session.verified_project:
        parts.append(f"项目：{session.verified_project}")
    if session.documents:
        parts.append("文档：" + "、".join(session.documents[:4]))
    if session.domains:
        parts.append("站点：" + "、".join(session.domains[:4]))
    if session.verified_meeting:
        parts.append("包含语音/视频会议")
    if session.card.distractions:
        parts.append(f"短暂切出 {len(session.card.distractions)} 次")
    session.card.summary = "；".join(parts)[:240]


def append_or_extend_segment(
    segments: List[ActivitySegment],
    *,
    start_time: datetime,
    end_time: datetime,
    app_name: str,
    is_distraction: bool = False,
) -> None:
    """保持 segments 严格递增、无重叠连续覆盖。"""
    s = local_time(start_time)
    e = local_time(end_time)
    if e <= s:
        return
    if segments:
        last = segments[-1]
        last_end = local_time(last.end_time)
        if s < last_end:
            s = last_end
        if e <= s:
            return
        if last.app_name == app_name and bool(last.is_distraction) == bool(is_distraction) and s == last_end:
            last.end_time = e
            return
    segments.append(ActivitySegment(start_time=s, end_time=e, app_name=app_name, is_distraction=is_distraction))


def rebuild_app_sites(segments: List[ActivitySegment]) -> List[AppSite]:
    totals = defaultdict(float)
    order: List[str] = []
    for seg in segments:
        dur = (local_time(seg.end_time) - local_time(seg.start_time)).total_seconds()
        if dur <= 0:
            continue
        if seg.app_name not in totals:
            order.append(seg.app_name)
        totals[seg.app_name] += dur
    return [AppSite(name=name, duration_seconds=totals[name]) for name in order]
