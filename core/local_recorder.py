"""
本机结构化活动录制器（事件驱动 + 三态隐私分类 + 冲突优先聚类 + 30 秒分心吸收 + 崩溃安全落盘）。

设计要点：
- 无截屏、无 MP4、默认零模型调用；默认 context_mode = "app_only"，可显式开启 "structured"。
- 单写者串行状态机：每次时间推进、候选分心、吸收、提升或停录封口均通过 StorageManager 短事务落盘。
- 墙钟回拨 / DST 防护：启动恢复全局单调水位 `last_committed_end_time`，拒绝在水位之下开启重叠新卡。
- 停录确认：stop(deadline=...) 等待录制线程完成最终提交确认，并显式清理 WinEventWatcher 与 UIA 子进程。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
import logging
import threading
import time
import uuid
from typing import Callable, Optional, Tuple

import config
from core.activity_time import local_time
from core.context_extractor import APP_CATEGORIES, ContextExtractor, MicrophoneMonitor
from core.privacy_filter import PrivacyFilter
from core.session_clusterer import (
    ActiveSession,
    append_or_extend_segment,
    can_merge_context,
    compute_session_key,
    enrich_session_metadata,
    rebuild_app_sites,
    should_enter_distraction_candidate,
)
from core.types import ActivityCard, ActivitySegment, AppSite, CaptureState, Distraction, WindowContext
from core.uia_worker import UiaWorkerClient
from core.win_event_watcher import WinEventWatcher
from core.window_tracker import WindowInfo, get_tracker

logger = logging.getLogger(__name__)

# 兼容旧测试与模块导入
_APP_CATEGORIES = dict(APP_CATEGORIES)

DISTRACTION_ABSORB_MAX_S = 30.0
MIN_PRIMARY_FOR_ABSORB_S = 60.0
MAX_SAMPLE_GAP_S = 3.0
FLUSH_INTERVAL_S = 4.0
UIA_DEBOUNCE_S = 0.25


@dataclass
class _PendingCandidate:
    ctx: WindowContext
    start_time: datetime
    end_time: datetime
    started_mono: float
    last_mono: float


class LocalActivityRecorder:
    """Commit short intervals as they are observed, then extend or cluster safely."""

    def __init__(
        self,
        storage,
        *,
        context_mode: Optional[str] = None,
        uia_client=None,
        mic_monitor: Optional[MicrophoneMonitor] = None,
        watcher: Optional[WinEventWatcher] = None,
        use_win_events: bool = True,
        settings_gen_provider: Optional[Callable[[], int]] = None,
        clock_mono: Callable[[], float] = time.monotonic,
    ):
        self.storage = storage
        self.tracker = get_tracker()
        self.privacy = PrivacyFilter()
        self._context_mode = context_mode or self._read_context_mode(storage)
        self._owns_uia = uia_client is None and self._context_mode == "structured"
        self._uia_client = (
            uia_client
            if uia_client is not None
            else (UiaWorkerClient(gen_dir=config.APP_DATA_DIR / "comtypes_gen") if self._owns_uia else None)
        )
        self._watcher = watcher
        self._use_win_events = use_win_events
        self._settings_gen_provider = settings_gen_provider
        self._clock_mono = clock_mono
        self._mic_monitor = mic_monitor or MicrophoneMonitor()
        self.extractor = ContextExtractor(
            self.tracker,
            self.privacy,
            uia_client=self._uia_client,
            mic_monitor=self._mic_monitor,
            nav_token_provider=lambda: self._watcher.nav_token if self._watcher else 0,
            settings_gen_provider=self._settings_gen_provider,
        )

        self.is_recording = False
        self.is_paused = False
        self.is_privacy_paused = False
        self.is_event_hook_active = False
        self.degraded_reason: Optional[str] = None

        self._stop = threading.Event()
        self._break = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._session: Optional[ActiveSession] = None
        self._candidate: Optional[_PendingCandidate] = None
        self._last_wall: Optional[datetime] = None
        self._last_mono: Optional[float] = None
        self._saved_at: Optional[datetime] = None
        self._deleted = False
        self._watermark: Optional[datetime] = None
        self._last_uia_mono: float = 0.0
        self._last_uia_hwnd: int = 0

        self._stop_confirmed = False
        self._stop_error: Optional[str] = None
        self._stop_deadline: Optional[float] = None

    @staticmethod
    def _read_context_mode(storage) -> str:
        try:
            mode = storage.get_setting("local_context_mode", "app_only")
            return "structured" if mode == "structured" else "app_only"
        except Exception:
            return "app_only"

    @property
    def context_mode(self) -> str:
        return self._context_mode

    def start(self):
        if not self.tracker.is_available:
            raise RuntimeError("当前无法读取 Windows 前台应用")
        if self._thread and self._thread.is_alive():
            raise RuntimeError("请等待本机计时停止")
        if self._thread is not None and not self._stop_confirmed:
            confirmed, error = self.stop()
            if not confirmed:
                raise RuntimeError(error or "上一次本机计时尚未保存")

        # 启动前执行崩溃恢复并载入全局单调水位
        try:
            self.storage.recover_interrupted_local_sessions()
            self._watermark = self.storage.get_local_watermark()
        except Exception as exc:
            logger.warning("恢复本机计时水位失败: %s", exc)

        self.is_recording = True
        self.is_paused = False
        self.is_privacy_paused = False
        self._stop_confirmed = False
        self._stop_error = None
        self._stop_deadline = None
        self._stop.clear()
        self._break.clear()

        if self._use_win_events and self._watcher is None:
            self._watcher = WinEventWatcher()
        if self._watcher is not None:
            self.is_event_hook_active = self._watcher.start()
            self.degraded_reason = self._watcher.degraded_reason
            if not self.is_event_hook_active:
                logger.info("本机录制运行于 1 秒采样点轮询降级模式: %s", self.degraded_reason or "hook 未启用")

        self._thread = threading.Thread(target=self._run, daemon=True, name="LocalActivityRecorder")
        self._thread.start()

    def pause(self):
        self.is_paused = True
        self._break.set()
        if self._watcher is not None:
            self._watcher.bump_nav_token()

    def resume(self):
        self.is_paused = False
        self._mic_monitor.clear_cache()

    def stop(self, deadline: Optional[float] = None) -> Tuple[bool, Optional[str]]:
        """停止录制并等待最终事务提交确认，返回 (confirmed, error_message)。"""
        eff_deadline = deadline if deadline is not None else (time.monotonic() + 6.0)
        self._stop_deadline = eff_deadline
        self._stop.set()
        if self._watcher is not None:
            try:
                self._watcher.stop(timeout=min(1.0, max(0.2, eff_deadline - time.monotonic())))
            except Exception:
                pass

        confirmed = True
        err: Optional[str] = None
        if self._thread and self._thread.is_alive():
            wait_s = max(0.1, eff_deadline - time.monotonic())
            self._thread.join(timeout=wait_s)
            if self._thread.is_alive():
                confirmed = False
                err = "本机计时最终落盘超时"
            else:
                confirmed = self._stop_confirmed
                err = self._stop_error
        elif self._thread is not None:
            if not self._stop_confirmed:
                self._confirm_final_save(eff_deadline)
            confirmed = self._stop_confirmed
            err = self._stop_error

        if self._owns_uia and self._uia_client is not None:
            self._uia_client.close(timeout=max(0.2, min(1.0, eff_deadline - time.monotonic())))
        return confirmed, err

    # ==================== 内部持久化原语 ====================

    def _context_event_dict(
        self, ctx: WindowContext, start: datetime, end: datetime
    ) -> dict:
        dur = max(0.0, (local_time(end) - local_time(start)).total_seconds())
        return {
            "start_time": local_time(start),
            "end_time": local_time(end),
            "duration_seconds": dur,
            "app_name": ctx.app_name,
            "friendly_app": ctx.friendly_app,
            "category": ctx.category,
            "domain": ctx.domain if self._context_mode == "structured" else None,
            "project_name": ctx.project_name if self._context_mode == "structured" else None,
            "document_name": ctx.document_name if self._context_mode == "structured" else None,
            "meeting_active": ctx.meeting_active if self._context_mode == "structured" else False,
            "source": ctx.source,
        }

    def _update_watermark(self, dt: Optional[datetime]) -> None:
        if dt is None:
            return
        t = local_time(dt)
        if self._watermark is None or t > self._watermark:
            self._watermark = t

    def _flush_active_session(self, *, finalize: bool = False, deadline: Optional[float] = None) -> None:
        sess = self._session
        if self._deleted or sess is None:
            return
        card = sess.card
        if card.start_time is None or card.end_time is None:
            return
        if local_time(card.start_time) >= local_time(card.end_time):
            if finalize and card.id is not None:
                self.storage.extend_local_card(
                    card,
                    session_token=sess.session_token,
                    segments=sess.segments,
                    finalize=True,
                    deadline=deadline,
                )
            return
        if not finalize and self._saved_at == card.end_time:
            return

        card.app_sites = rebuild_app_sites(sess.segments)
        if not card.app_sites:
            card.app_sites = [
                AppSite(
                    name=sess.friendly_app,
                    duration_seconds=(local_time(card.end_time) - local_time(card.start_time)).total_seconds(),
                )
            ]

        if card.id is None:
            card.id = self.storage.start_local_card(
                card,
                sess.session_token,
                sess.segments,
                deadline=deadline,
            )
            if finalize:
                self.storage.extend_local_card(
                    card,
                    session_token=sess.session_token,
                    segments=sess.segments,
                    finalize=True,
                    deadline=deadline,
                )
        else:
            ok = self.storage.extend_local_card(
                card,
                session_token=sess.session_token,
                segments=sess.segments,
                finalize=finalize,
                deadline=deadline,
            )
            if not ok:
                self._deleted = True
                return

        self._saved_at = card.end_time
        self._update_watermark(card.end_time)

    def _promote_candidate(
        self,
        *,
        finalize_candidate: bool,
        deadline: Optional[float] = None,
    ) -> None:
        """在单事务中封口主卡并提交已确认的候选分心区间为独立卡片。"""
        cand = self._candidate
        sess = self._session
        self._candidate = None
        if cand is None:
            return

        cand_dur = (local_time(cand.end_time) - local_time(cand.start_time)).total_seconds()
        new_token = uuid.uuid4().hex
        cand_card: Optional[ActivityCard] = None
        cand_segs = []
        cand_ctx_event = None
        if cand_dur > 0:
            cand_segs = [
                ActivitySegment(
                    start_time=local_time(cand.start_time),
                    end_time=local_time(cand.end_time),
                    app_name=cand.ctx.friendly_app,
                    is_distraction=False,
                )
            ]
            cand_card = ActivityCard(
                category=cand.ctx.category,
                title=cand.ctx.friendly_app,
                summary="",
                start_time=local_time(cand.start_time),
                end_time=local_time(cand.end_time),
                app_sites=[AppSite(name=cand.ctx.friendly_app, duration_seconds=cand_dur)],
                distractions=[],
                productivity_score=0.0,
                source="local",
                session_key=compute_session_key(cand.ctx),
                is_finalized=finalize_candidate,
            )
            temp_sess = ActiveSession(
                card=cand_card,
                session_token=new_token,
                app_name=cand.ctx.app_name,
                friendly_app=cand.ctx.friendly_app,
                started_mono=cand.started_mono,
                segments=cand_segs,
            )
            enrich_session_metadata(temp_sess, cand.ctx, self._context_mode)
            cand_ctx_event = self._context_event_dict(cand.ctx, cand.start_time, cand.end_time)

        # 若主卡尚未首次落盘，先落盘以保证两段时间均完整无损
        if sess is not None and not self._deleted and sess.card.id is None:
            self._flush_active_session(finalize=False, deadline=deadline)

        new_id = self.storage.promote_recorder_candidate(
            session_token=sess.session_token if sess else "",
            primary_card=None if (sess is None or self._deleted) else sess.card,
            primary_segments=None if (sess is None or self._deleted) else sess.segments,
            candidate_card=cand_card,
            candidate_segments=cand_segs,
            candidate_finalize=finalize_candidate,
            new_session_token=None if finalize_candidate else new_token,
            candidate_context_event=cand_ctx_event,
            deadline=deadline,
        )

        if cand_card is not None:
            self._update_watermark(cand_card.end_time)
        if sess is not None and sess.card.end_time is not None:
            self._update_watermark(sess.card.end_time)

        if finalize_candidate or cand_card is None or new_id is None:
            self._session = None
            self._saved_at = None
            self._deleted = False
        else:
            cand_card.id = new_id
            self._session = ActiveSession(
                card=cand_card,
                session_token=new_token,
                app_name=cand.ctx.app_name,
                friendly_app=cand.ctx.friendly_app,
                started_mono=cand.started_mono,
                segments=cand_segs,
            )
            enrich_session_metadata(self._session, cand.ctx, self._context_mode)
            self._saved_at = cand_card.end_time
            self._deleted = False

    def _finish(self, deadline: Optional[float] = None) -> None:
        if self._candidate is not None:
            self._promote_candidate(finalize_candidate=True, deadline=deadline)
        else:
            self._flush_active_session(finalize=True, deadline=deadline)
        self._session = None
        self._candidate = None
        self._last_wall = None
        self._last_mono = None
        self._saved_at = None
        self._deleted = False

    def _confirm_final_save(self, deadline: Optional[float]) -> None:
        try:
            self._finish(deadline=deadline)
        except Exception as exc:
            self._stop_confirmed = False
            self._stop_error = f"最终保存失败: {type(exc).__name__}"
            logger.warning("本机计时停止落盘失败: %s", type(exc).__name__)
        else:
            self._stop_confirmed = True
            self._stop_error = None

    def _start_new_session(self, now: datetime, now_mono: float, ctx: WindowContext) -> None:
        token = uuid.uuid4().hex
        card = ActivityCard(
            category=ctx.category,
            title=ctx.friendly_app,
            summary="",
            start_time=now,
            end_time=now,
            app_sites=[AppSite(name=ctx.friendly_app, duration_seconds=0.0)],
            distractions=[],
            productivity_score=0.0,
            source="local",
            session_key=compute_session_key(ctx),
            is_finalized=False,
        )
        sess = ActiveSession(
            card=card,
            session_token=token,
            app_name=ctx.app_name,
            friendly_app=ctx.friendly_app,
            started_mono=now_mono,
            segments=[],
        )
        enrich_session_metadata(sess, ctx, self._context_mode)
        self._session = sess
        self._saved_at = None
        self._deleted = False

    def _commit_candidate_state(self, cand: _PendingCandidate) -> None:
        sess = self._session
        if sess is None or self._deleted:
            return
        if sess.card.id is None:
            self._flush_active_session(finalize=False)
        if self._deleted or sess.card.id is None:
            return
        ok = self.storage.upsert_recorder_candidate(
            session_token=sess.session_token,
            primary_card=sess.card,
            primary_segments=sess.segments,
            candidate={
                "start_time": cand.start_time,
                "end_time": cand.end_time,
                "app_name": cand.ctx.app_name,
                "friendly_app": cand.ctx.friendly_app,
                "category": cand.ctx.category,
                "context": {
                    "title": cand.ctx.friendly_app,
                    "session_key": compute_session_key(cand.ctx),
                },
            },
        )
        if not ok:
            # 主卡已被外部删除（删除事务已自动结算先前候选），清空本地旧主卡引用
            self._deleted = True
            self._candidate = None
            self._session = None
        else:
            self._update_watermark(cand.end_time)

    # ==================== 核心单步状态机 ====================

    def sample(
        self,
        now: datetime,
        window: Optional[WindowInfo],
        *,
        now_mono: Optional[float] = None,
        boundary_uncertain: bool = False,
        allow_uia: bool = True,
        expected_nav_token: Optional[int] = None,
        expected_settings_gen: Optional[int] = None,
    ) -> None:
        """Consume one foreground observation through the strict 3-state & clustering state machine."""
        now_local = local_time(now)
        if now_mono is None:
            if self._last_wall is not None and self._last_mono is not None:
                delta_s = (now_local - self._last_wall).total_seconds()
                now_mono = self._last_mono + (delta_s if delta_s >= 0 else 0.0)
            else:
                now_mono = self._clock_mono()

        # 1. 手动暂停 / 强制断点 / 边界不确定（队列溢出、事件延迟、目标已失效）
        if boundary_uncertain or self._break.is_set() or self.is_paused:
            self._break.clear()
            self._finish()
            if self.is_paused or boundary_uncertain:
                return

        # 2. 墙钟回拨 / DST 回退防护：若时间倒退或低于全局水位，立即封口并拒绝开重叠新卡
        if self._last_wall is not None and now_local < self._last_wall:
            self._finish()
            return
        if self._watermark is not None and now_local < self._watermark:
            self._finish()
            return

        # 3. 严格三态隐私与上下文判定
        ctx = self.extractor.extract(
            window,
            context_mode=self._context_mode,
            allow_uia=allow_uia,
            expected_nav_token=expected_nav_token,
            expected_settings_gen=expected_settings_gen,
        )
        self.is_privacy_paused = ctx.state == CaptureState.SENSITIVE_OR_UNKNOWN
        if self.is_privacy_paused:
            self._finish()
            return

        # 4. 休眠/长间隙断点（> 3s）
        if self._last_wall is not None:
            wall_gap = (now_local - self._last_wall).total_seconds()
            if not (0 < wall_gap <= MAX_SAMPLE_GAP_S):
                self._finish()

        # 5. 跨本地午夜切分
        if self._session is not None and self._session.card.start_time is not None:
            if now_local.date() != local_time(self._session.card.start_time).date():
                midnight = datetime.combine(now_local.date(), dt_time.min)
                if self._candidate is not None:
                    if local_time(self._candidate.start_time) < midnight:
                        self._candidate.end_time = midnight
                    self._promote_candidate(finalize_candidate=True)
                else:
                    if local_time(self._session.card.end_time) < midnight:
                        append_or_extend_segment(
                            self._session.segments,
                            start_time=self._session.card.end_time,
                            end_time=midnight,
                            app_name=self._session.friendly_app,
                            is_distraction=False,
                        )
                        self._session.card.end_time = midnight
                    self._finish()

        # 6. 若当前处于 30s 候选分心缓冲期
        if self._candidate is not None and self._session is not None:
            cand = self._candidate
            elapsed_mono = now_mono - cand.started_mono
            if can_merge_context(self._session, ctx) and elapsed_mono <= DISTRACTION_ABSORB_MAX_S:
                # <= 30s 回到原主会话：在单事务中吸收为分心段 + Distraction
                cand.end_time = now_local
                distraction_dur = (local_time(cand.end_time) - local_time(cand.start_time)).total_seconds()
                offset_s = (local_time(cand.start_time) - local_time(self._session.card.start_time)).total_seconds()
                if distraction_dur > 0:
                    append_or_extend_segment(
                        self._session.segments,
                        start_time=cand.start_time,
                        end_time=cand.end_time,
                        app_name=cand.ctx.friendly_app,
                        is_distraction=True,
                    )
                    self._session.card.distractions.append(
                        Distraction(
                            description=f"短暂切换到 {cand.ctx.friendly_app}",
                            timestamp=max(0.0, offset_s),
                            duration_seconds=distraction_dur,
                        )
                    )
                self._session.card.end_time = now_local
                self._session.card.app_sites = rebuild_app_sites(self._session.segments)
                enrich_session_metadata(self._session, ctx, self._context_mode)
                ok = self.storage.absorb_recorder_candidate(
                    session_token=self._session.session_token,
                    primary_card=self._session.card,
                    primary_segments=self._session.segments,
                )
                self._candidate = None
                if not ok:
                    self._deleted = True
                    self._session = None
                    self._start_new_session(now_local, now_mono, ctx)
                else:
                    self._saved_at = now_local
                    self._update_watermark(now_local)
                self._last_wall = now_local
                self._last_mono = now_mono
                return

            if cand.ctx.app_name == ctx.app_name and elapsed_mono <= DISTRACTION_ABSORB_MAX_S:
                # 仍在同一候选应用且未满 30s：推进已确认候选水位（不发第二张卡）
                cand.end_time = now_local
                cand.last_mono = now_mono
                self._commit_candidate_state(cand)
                self._last_wall = now_local
                self._last_mono = now_mono
                return

            # 超过 30s 或切向第三个任务 -> 封口主卡，将候选提升为独立卡片
            if cand.ctx.app_name == ctx.app_name:
                cand.end_time = now_local
                self._promote_candidate(finalize_candidate=False)
                self._last_wall = now_local
                self._last_mono = now_mono
                return
            else:
                cand.end_time = now_local
                self._promote_candidate(finalize_candidate=True)
                self._start_new_session(now_local, now_mono, ctx)
                self._last_wall = now_local
                self._last_mono = now_mono
                return

        # 7. 无活跃会话 -> 开启新会话（确保 start_time >= watermark）
        if self._session is None:
            start_ts = max(now_local, self._watermark) if self._watermark else now_local
            self._start_new_session(start_ts, now_mono, ctx)
            self._last_wall = now_local
            self._last_mono = now_mono
            return

        # 8. 活跃会话判断：可合并 vs 进入 30s 分心候选 vs 冲突直接拆卡
        if can_merge_context(self._session, ctx):
            prev_end = self._session.card.end_time or now_local
            append_or_extend_segment(
                self._session.segments,
                start_time=prev_end,
                end_time=now_local,
                app_name=ctx.friendly_app,
                is_distraction=False,
            )
            self._session.card.end_time = now_local
            self._session.card.app_sites = rebuild_app_sites(self._session.segments)
            enrich_session_metadata(self._session, ctx, self._context_mode)
            if self._saved_at is None or (now_local - self._saved_at) >= timedelta(seconds=FLUSH_INTERVAL_S):
                self._flush_active_session(finalize=False)
        else:
            # 先把主卡延伸至当前切换边界
            prev_end = self._session.card.end_time or now_local
            append_or_extend_segment(
                self._session.segments,
                start_time=prev_end,
                end_time=now_local,
                app_name=self._session.friendly_app,
                is_distraction=False,
            )
            self._session.card.end_time = now_local
            self._session.card.app_sites = rebuild_app_sites(self._session.segments)

            primary_dur = (local_time(now_local) - local_time(self._session.card.start_time)).total_seconds()
            if should_enter_distraction_candidate(
                self._session,
                ctx,
                session_duration_s=primary_dur,
                min_primary_seconds=MIN_PRIMARY_FOR_ABSORB_S,
            ):
                # 停住主卡在切出点并持久化候选区间
                cand = _PendingCandidate(
                    ctx=ctx,
                    start_time=now_local,
                    end_time=now_local,
                    started_mono=now_mono,
                    last_mono=now_mono,
                )
                self._candidate = cand
                self._commit_candidate_state(cand)
            else:
                # 冲突优先或主卡未满 60s -> 直接封口拆卡
                self._finish()
                start_ts = max(now_local, self._watermark) if self._watermark else now_local
                self._start_new_session(start_ts, now_mono, ctx)

        self._last_wall = now_local
        self._last_mono = now_mono

    # ==================== 主事件循环 ====================

    def _consume_win_events(self) -> bool:
        """按序消费有界 WinEvent 队列；隐私即时校验零防抖，仅对 UIA 提取做防抖。"""
        if self._watcher is None:
            return False
        events = self._watcher.drain()
        if not events:
            return False

        for ev in events:
            if self._stop.is_set():
                return True
            if ev.boundary_uncertain or ev.kind == "boundary_uncertain":
                # 队列溢出 / 投递延迟超限 -> 立刻封口留空档
                self.sample(ev.event_wall, None, now_mono=ev.event_mono, boundary_uncertain=True)
                continue

            # 事件时标题快照即时隐私判定（零防抖，防 正常 -> 敏感 -> 正常 被延迟恢复标题掩盖）
            if ev.title_snapshot and self.privacy.enabled:
                snap_window = WindowInfo("event-snapshot", ev.title_snapshot, 0, hwnd=ev.hwnd)
                if self.privacy.is_sensitive(snap_window):
                    self.is_privacy_paused = True
                    self.sample(ev.event_wall, None, now_mono=ev.event_mono, boundary_uncertain=True)
                    continue

            # 按事件目标 hwnd 校验当前进程身份与窗口；若目标已销毁/切换导致无法还原边界则封口
            window = self.tracker.get_window_info(ev.hwnd) if hasattr(self.tracker, "get_window_info") else self.tracker.get_active_window()
            if window is None or (ev.hwnd and window.hwnd and window.hwnd != ev.hwnd):
                self.sample(ev.event_wall, None, now_mono=ev.event_mono, boundary_uncertain=True)
                continue
            if ev.title_snapshot and window.window_title != ev.title_snapshot:
                # 标题在事件到消费之间已经变化，无法确认中间历史标题是否敏感 -> 封口留空档
                self.sample(ev.event_wall, None, now_mono=ev.event_mono, boundary_uncertain=True)
                continue

            # 仅对昂贵的 UIA 读取做短防抖
            allow_uia = True
            if ev.kind == "namechange" and ev.hwnd == self._last_uia_hwnd:
                if (ev.event_mono - self._last_uia_mono) < UIA_DEBOUNCE_S:
                    allow_uia = False
            if allow_uia:
                self._last_uia_mono = ev.event_mono
                self._last_uia_hwnd = ev.hwnd

            self.sample(
                ev.event_wall,
                None if self.is_paused else window,
                now_mono=ev.event_mono,
                allow_uia=allow_uia,
                expected_nav_token=ev.nav_token,
            )
        return True

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    consumed = self._consume_win_events()
                    if not consumed:
                        now_mono = self._clock_mono()
                        nav_tok = self._watcher.nav_token if self._watcher else 0
                        window = None if self.is_paused else self.tracker.get_active_window()
                        self.sample(
                            datetime.now(),
                            window,
                            now_mono=now_mono,
                            expected_nav_token=nav_tok,
                        )
                except Exception:
                    logger.warning("本机计时暂时无法保存")

                if self._watcher is not None and self.is_event_hook_active:
                    self._watcher.wait(1.0)
                else:
                    self._stop.wait(1.0)
        finally:
            try:
                self._confirm_final_save(self._stop_deadline)
            finally:
                self.is_recording = False
                self.is_privacy_paused = False
