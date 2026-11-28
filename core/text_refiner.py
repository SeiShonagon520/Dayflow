"""
可选纯文本 LLM 批处理精炼调度器（默认关闭，录制中可随时关停）。

核心安全与并发契约：
1. 原子代次门控（_gate_lock + settings_gen）：
   - 关闭开关或修改模型配置时持锁置 _enabled=False、递增 settings_gen 并取消在途任务；
   - httpx 异步请求发射钩子在字节发出前持锁校验 _enabled and claimed_gen == settings_gen；
   - 短事务回写同样持锁线性化校验 _enabled and claimed_gen == settings_gen，并用 SQL
     `WHERE id=? AND version=? AND user_edited=0 AND source='local' AND refinement_lease_id=?` 兜底。
2. 最小固定应用标签外发清单：
   - 仅发送 {id, start, end, duration_minutes, category, app_sites[{固定应用标签, minutes}], distraction_minutes}；
   - 未知进程一律折叠为固定常量 "其他应用"；绝不发送 domain / project_name / document_name / 自由标题 / 用户编辑卡片。
3. 硬预算与持久额度：
   - 单批 <= 10 卡、输入 <= 8 KB、max_tokens=1024、每日 24 批持久化在 SQLite、单卡最多 3 次尝试（租约过期收口为终态 failed）。
4. 独立异步 HTTP 客户端：
   - Worker 拥有独立的 DayflowBackendProvider，在其专属事件循环 finally 中关闭，且早于 StorageManager.close()。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
import json
import logging
import math
import threading
import time
import uuid
from typing import Callable, Dict, List, Optional

import config
from core.activity_time import local_time
from core.llm_provider import DayflowBackendProvider
from core.types import ActivityCard
from core.window_tracker import get_outbound_app_label

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"编程", "工作", "学习", "会议", "社交", "娱乐", "休息", "其他"}
MAX_CARDS_PER_BATCH = 10
MAX_INPUT_BYTES = 8192
MAX_OUTPUT_TOKENS = 1024
DAILY_BATCH_LIMIT = 24
MAX_ATTEMPTS_PER_CARD = 3
LEASE_TTL_SECONDS = 180.0
DEFAULT_SCAN_INTERVAL_SECONDS = 300.0


class RefinementCancelledError(RuntimeError):
    """精炼在请求发射前被停用或设置变更拦截。"""


def build_minimal_outbound_payload(cards: List[ActivityCard]) -> List[dict]:
    """
    构建最小外发纯文本清单：
    - 仅含固定应用标签、时长、类别和分心时长；
    - 严格排除 title / summary / domain / project_name / document_name / 未知进程名。
    """
    payload = []
    for card in cards[:MAX_CARDS_PER_BATCH]:
        if card.id is None or card.start_time is None or card.end_time is None:
            continue
        app_totals: Dict[str, float] = defaultdict(float)
        distraction_seconds = 0.0
        if card.segments:
            for seg in card.segments:
                dur = max(0.0, (local_time(seg.end_time) - local_time(seg.start_time)).total_seconds())
                if dur <= 0:
                    continue
                label = get_outbound_app_label(seg.app_name)
                app_totals[label] += dur
                if seg.is_distraction:
                    distraction_seconds += dur
        else:
            for site in card.app_sites:
                dur = max(0.0, float(site.duration_seconds or 0.0))
                if dur > 0:
                    app_totals[get_outbound_app_label(site.name)] += dur
            for dist in card.distractions:
                distraction_seconds += max(0.0, float(dist.duration_seconds or 0.0))

        app_list = [
            {"name": name, "minutes": round(sec / 60.0, 1)}
            for name, sec in sorted(app_totals.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        item = {
            "id": int(card.id),
            "start": local_time(card.start_time).strftime("%H:%M"),
            "end": local_time(card.end_time).strftime("%H:%M"),
            "duration_minutes": round(card.duration_minutes, 1),
            "category": card.category if card.category in VALID_CATEGORIES else "其他",
            "app_sites": app_list,
            "distraction_minutes": round(distraction_seconds / 60.0, 1),
        }
        # 硬字节预算控制
        tentative = payload + [item]
        if len(json.dumps(tentative, ensure_ascii=False).encode("utf-8")) > MAX_INPUT_BYTES:
            break
        payload.append(item)
    return payload


def validate_refinement_response(
    raw_items: List[dict],
    claimed_cards: Dict[int, ActivityCard],
) -> tuple[List[dict], List[int]]:
    """
    严格校验模型返回：
    - 拒绝重复 ID、越权 ID、非法分类、非有限分数、不在 1..100 范围内的分数、空标题；
    - 返回 (valid_updates, failed_ids)。
    """
    seen: set[int] = set()
    updates: List[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        cid = item.get("id")
        if not isinstance(cid, int) or isinstance(cid, bool) or cid not in claimed_cards or cid in seen:
            continue
        category = str(item.get("category") or "").strip()
        title = " ".join(str(item.get("title") or "").split())[:60]
        summary = " ".join(str(item.get("summary") or "").split())[:240]
        score = item.get("productivity_score")
        if category not in VALID_CATEGORIES or not title:
            continue
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            continue
        score_f = float(score)
        if not math.isfinite(score_f) or not (1.0 <= score_f <= 100.0):
            continue
        seen.add(cid)
        updates.append({
            "id": cid,
            "expected_version": int(claimed_cards[cid].version),
            "category": category,
            "title": title,
            "summary": summary,
            "productivity_score": round(score_f, 1),
        })

    failed_ids = [cid for cid in claimed_cards if cid not in seen]
    return updates, failed_ids


class TextRefinementWorker:
    """定时与手动触发共用的单一纯文本精炼 Worker。"""

    def __init__(
        self,
        storage,
        *,
        provider_factory: Optional[Callable[[], DayflowBackendProvider]] = None,
        scan_interval_seconds: float = DEFAULT_SCAN_INTERVAL_SECONDS,
        daily_limit: int = DAILY_BATCH_LIMIT,
    ):
        self.storage = storage
        self._provider_factory = provider_factory
        self.scan_interval = max(5.0, float(scan_interval_seconds))
        self.daily_limit = max(1, int(daily_limit))

        self._gate_lock = threading.RLock()
        self._enabled = False
        self._settings_gen = 0
        self._active_loop: Optional[asyncio.AbstractEventLoop] = None
        self._active_task: Optional[asyncio.Task] = None
        self._active_run_lock = threading.Lock()

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    @property
    def settings_gen(self) -> int:
        with self._gate_lock:
            return self._settings_gen

    @property
    def is_enabled(self) -> bool:
        with self._gate_lock:
            return self._enabled

    @property
    def is_running(self) -> bool:
        return self._running

    def configure(self, *, enabled: bool, bump_generation: bool = True) -> int:
        """
        线性化更新授权开关与代次：
        关闭或模型设置变更时立即递增 settings_gen 并取消在途请求任务。
        """
        with self._gate_lock:
            if bump_generation:
                self._settings_gen += 1
            self._enabled = bool(enabled)
            gen = self._settings_gen
            loop, task = self._active_loop, self._active_task
            if (not self._enabled or bump_generation) and loop is not None and task is not None:
                try:
                    loop.call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    pass
        if enabled:
            self.start()
            self._wake_event.set()
        return gen

    def start(self) -> None:
        with self._gate_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._wake_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._thread_main, daemon=True, name="TextRefinementWorker")
            self._thread.start()

    def stop(self, deadline: Optional[float] = None) -> bool:
        """立即停用门控、取消在途任务并等待专属事件循环关闭独立 HTTP 客户端。"""
        with self._gate_lock:
            self._enabled = False
            self._settings_gen += 1
            self._stop_event.set()
            self._wake_event.set()
            loop, task = self._active_loop, self._active_task
            if loop is not None and task is not None:
                try:
                    loop.call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    pass

        if self._thread and self._thread.is_alive():
            wait_s = max(0.2, (deadline - time.monotonic()) if deadline is not None else 2.0)
            self._thread.join(timeout=wait_s)
        return not (self._thread and self._thread.is_alive())

    def _build_provider(self) -> DayflowBackendProvider:
        if self._provider_factory is not None:
            return self._provider_factory()
        return DayflowBackendProvider(
            api_base_url=config.API_BASE_URL,
            api_key=config.API_KEY,
            model=config.API_MODEL,
            timeout=60.0,
        )

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_loop())
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("纯文本精炼调度循环异常退出")
        finally:
            with self._gate_lock:
                self._active_loop = None
                self._active_task = None
            self._running = False

    async def _async_loop(self) -> None:
        loop = asyncio.get_running_loop()
        with self._gate_lock:
            self._active_loop = loop
        try:
            while not self._stop_event.is_set():
                if self.is_enabled:
                    try:
                        await self._run_batch_locked(manual=False)
                    except asyncio.CancelledError:
                        if self._stop_event.is_set():
                            break
                    except Exception:
                        logger.warning("定时纯文本精炼本轮未完成")
                # 分段等待，及时响应停用或停止信号
                waited = 0.0
                while waited < self.scan_interval and not self._stop_event.is_set():
                    if self._wake_event.is_set():
                        self._wake_event.clear()
                        break
                    await asyncio.sleep(0.5)
                    waited += 0.5
        finally:
            with self._gate_lock:
                self._active_loop = None
                self._active_task = None

    async def run_once_manual(self) -> dict:
        """供 POST /api/refinement/run 手动触发，与定时调度共用同一串行锁与门控。"""
        with self._gate_lock:
            if not self._enabled:
                return {"ok": False, "claimed": 0, "committed": 0, "reason": "disabled"}
        return await self._run_batch_locked(manual=True)

    async def _run_batch_locked(self, *, manual: bool = False) -> dict:
        if not self._active_run_lock.acquire(blocking=False):
            return {"ok": True, "claimed": 0, "committed": 0, "reason": "busy"}
        provider: Optional[DayflowBackendProvider] = None
        lease_id = uuid.uuid4().hex
        claimed_cards: List[ActivityCard] = []
        try:
            with self._gate_lock:
                if not self._enabled or self._stop_event.is_set():
                    return {"ok": False, "claimed": 0, "committed": 0, "reason": "disabled"}
                claimed_gen = self._settings_gen

            claimed_cards = await asyncio.to_thread(
                self.storage.claim_refinement_batch,
                lease_id,
                lease_ttl=LEASE_TTL_SECONDS,
                max_cards=MAX_CARDS_PER_BATCH,
                daily_limit=self.daily_limit,
                max_attempts=MAX_ATTEMPTS_PER_CARD,
            )
            if not claimed_cards:
                return {"ok": True, "claimed": 0, "committed": 0, "reason": "empty_or_quota"}

            payload = build_minimal_outbound_payload(claimed_cards)
            if not payload:
                await asyncio.to_thread(
                    self.storage.release_refinement_lease,
                    lease_id,
                    retryable=False,
                    max_attempts=MAX_ATTEMPTS_PER_CARD,
                )
                return {"ok": True, "claimed": len(claimed_cards), "committed": 0, "reason": "empty_payload"}

            payload_ids = {item["id"] for item in payload}
            claimed_map = {c.id: c for c in claimed_cards if c.id in payload_ids}
            overflow_ids = [c.id for c in claimed_cards if c.id not in payload_ids and c.id is not None]
            if overflow_ids:
                await asyncio.to_thread(
                    self.storage.commit_refinement_results,
                    lease_id,
                    [],
                    failed_ids=overflow_ids,
                    max_attempts=MAX_ATTEMPTS_PER_CARD,
                )

            provider = self._build_provider()

            # 线性化发射前检查钩子：在 httpx 真正写入网络套接字前持锁校验授权代次
            async def _pre_send_gate(_request) -> None:
                with self._gate_lock:
                    if not self._enabled or self._settings_gen != claimed_gen or self._stop_event.is_set():
                        raise RefinementCancelledError("精炼已在请求发送前停用")

            loop = asyncio.get_running_loop()
            with self._gate_lock:
                if not self._enabled or self._settings_gen != claimed_gen or self._stop_event.is_set():
                    raise RefinementCancelledError("精炼已停用")
                self._active_loop = loop
                task = asyncio.create_task(
                    provider.refine_local_cards(
                        payload,
                        max_tokens=MAX_OUTPUT_TOKENS,
                        pre_send_hook=_pre_send_gate,
                    )
                )
                self._active_task = task

            try:
                raw_items = await task
            finally:
                with self._gate_lock:
                    if self._active_task is task:
                        self._active_task = None

            updates, failed_ids = validate_refinement_response(raw_items, claimed_map)

            # 原子线性化提交：持 _gate_lock 核对代次与开关后再落库
            def _commit_if_authorized() -> int:
                with self._gate_lock:
                    if not self._enabled or self._settings_gen != claimed_gen or self._stop_event.is_set():
                        self.storage.release_refinement_lease(
                            lease_id, retryable=True, max_attempts=MAX_ATTEMPTS_PER_CARD
                        )
                        return -1
                    return self.storage.commit_refinement_results(
                        lease_id,
                        updates,
                        failed_ids=failed_ids,
                        max_attempts=MAX_ATTEMPTS_PER_CARD,
                    )

            committed = await asyncio.to_thread(_commit_if_authorized)
            if committed < 0:
                return {"ok": False, "claimed": len(claimed_map), "committed": 0, "reason": "stale_generation"}
            return {"ok": True, "claimed": len(claimed_map), "committed": committed}

        except (asyncio.CancelledError, RefinementCancelledError):
            if claimed_cards:
                await asyncio.to_thread(
                    self.storage.release_refinement_lease,
                    lease_id,
                    retryable=True,
                    max_attempts=MAX_ATTEMPTS_PER_CARD,
                )
            return {"ok": False, "claimed": len(claimed_cards), "committed": 0, "reason": "cancelled"}
        except Exception as exc:
            logger.warning("纯文本精炼批次失败: %s", type(exc).__name__)
            if claimed_cards:
                await asyncio.to_thread(
                    self.storage.release_refinement_lease,
                    lease_id,
                    retryable=True,
                    max_attempts=MAX_ATTEMPTS_PER_CARD,
                )
            return {"ok": False, "claimed": len(claimed_cards), "committed": 0, "reason": type(exc).__name__}
        finally:
            if provider is not None:
                try:
                    await provider.close()
                except Exception:
                    pass
            self._active_run_lock.release()
