"""
Dayflow Python 后端桥接层

把 core/ 和 database/ 的能力暴露成 HTTP API，供 Tauri 前端调用。
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

# 让 bridge 能 import 到项目根下的 core / database
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
from core.activity_time import activity_segments, day_bounds, ledger_days
from core.daily_summary import daily_summary, evidence_markdown
from core.chunk_files import chunk_files, protected_chunk_files
from core.types import ActivityCard, AppSite, Distraction
from database.storage import StorageManager
from bridge.settings import (
    MASK, RECORDING_KEYS, SECRET_KEYS, apply_settings, chunks_directory, read_settings,
    updated_settings, write_settings,
)
from bridge.desktop import router

logger = logging.getLogger("bridge")

app = FastAPI(title="Dayflow Bridge", version=config.VERSION)
app.include_router(router)

ORIGINS = [
    "http://tauri.localhost", "https://tauri.localhost", "tauri://localhost",
    "http://localhost:1420", "http://127.0.0.1:1420",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_recording_lock = threading.RLock()
_mutation_cond = threading.Condition()
_active_mutations = 0
_shutting_down = False
_settings_gen_lock = threading.Lock()
_settings_gen = 0

_storage: StorageManager | None = None
_recorder = None        # core.recorder.RecordingManager
_analysis = None        # core.analysis.AnalysisManager
_refiner = None         # core.text_refiner.TextRefinementWorker
_provider = None        # core.llm_provider.DayflowBackendProvider
_log_manager = None     # core.log_manager.LogManager
_mail_stop = threading.Event()
_mail_thread: threading.Thread | None = None


def _current_settings_gen() -> int:
    with _settings_gen_lock:
        return _settings_gen


def _bump_settings_gen() -> int:
    global _settings_gen
    with _settings_gen_lock:
        _settings_gen += 1
        return _settings_gen


@app.middleware("http")
async def authorize_bridge(request: Request, call_next):
    global _active_mutations
    if request.method != "OPTIONS" and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin and origin not in ORIGINS:
            return JSONResponse({"detail": "不允许此来源访问 Dayflow"}, status_code=403)
        token = os.getenv("DAYFLOW_BRIDGE_TOKEN")
        if token and not hmac.compare_digest(request.headers.get("x-dayflow-session", "").encode(), token.encode()):
            return JSONResponse({"detail": "Dayflow 后台会话未就绪"}, status_code=401)

    is_mutating = (
        request.method in {"POST", "PATCH", "PUT", "DELETE"}
        and request.url.path.startswith("/api/")
        and request.url.path != "/api/system/shutdown"
    )
    if is_mutating:
        with _mutation_cond:
            if _shutting_down:
                return JSONResponse({"detail": "Dayflow 正在安全退出，暂不接受写入请求"}, status_code=503)
            _active_mutations += 1
    try:
        return await call_next(request)
    finally:
        if is_mutating:
            with _mutation_cond:
                _active_mutations -= 1
                if _active_mutations <= 0:
                    _mutation_cond.notify_all()


def get_storage() -> StorageManager:
    global _storage
    if _storage is None:
        _storage = StorageManager()
    return _storage


def get_recorder():
    """录制管理器（懒加载 —— 视觉模式下初始化会占用屏幕句柄）"""
    global _recorder
    if _recorder is None:
        from core.recorder import RecordingManager
        storage = get_storage()
        values = read_settings(storage)
        _recorder = RecordingManager(
            storage,
            mode=values["recording_mode"],
            context_mode=values["local_context_mode"],
            settings_gen_provider=_current_settings_gen,
        )
    return _recorder


def get_analysis():
    global _analysis
    if _analysis is None:
        from core.analysis import AnalysisManager
        _analysis = AnalysisManager(get_storage())
    return _analysis


def get_refiner():
    global _refiner
    if _refiner is None:
        from core.text_refiner import TextRefinementWorker
        _refiner = TextRefinementWorker(get_storage())
    return _refiner


def get_provider():
    global _provider
    if _provider is None:
        from core.llm_provider import DayflowBackendProvider
        _provider = DayflowBackendProvider()
    return _provider


def _sync_refiner(values: dict, *, bump_generation: bool = False) -> None:
    """将纯文本精炼开关和模型配置同步到唯一 Worker。"""
    enabled = (
        values.get("recording_mode") == "local"
        and values.get("local_ai_refinement") == "1"
        and not _needs_recording_setup()
    )
    if enabled or _refiner is not None:
        get_refiner().configure(enabled=enabled, bump_generation=bump_generation)


# ── 序列化 ────────────────────────────────────────────────────


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def app_site_to_dict(a: AppSite) -> dict:
    return {
        "name": a.name,
        "durationSeconds": int(a.duration_seconds or 0),
        "iconUrl": a.icon_url,
    }


def distraction_to_dict(d: Distraction) -> dict:
    return {
        "description": d.description,
        "timestamp": d.timestamp,
        "durationSeconds": int(d.duration_seconds or 0),
    }


def card_to_dict(c: ActivityCard) -> dict:
    return {
        "id": c.id,
        "category": c.category or "",
        "title": c.title or "",
        "summary": c.summary or "",
        "startTime": _iso(c.start_time),
        "endTime": _iso(c.end_time),
        "durationMinutes": round(c.duration_minutes or 0, 1),
        "productivityScore": round(c.productivity_score or 0, 1),
        "appSites": [app_site_to_dict(a) for a in (c.app_sites or [])],
        "distractions": [distraction_to_dict(d) for d in (c.distractions or [])],
    }


# ── 生命周期与统一优雅停机 ────────────────────────────────────


def _startup() -> None:
    global _log_manager, _shutting_down
    with _mutation_cond:
        _shutting_down = False
    from core.log_manager import LogManager
    if _log_manager is not None:
        _log_manager.close()
    _log_manager = LogManager(
        log_dir=config.APP_DATA_DIR,
        log_filename="dayflow.log",
        max_size_mb=5, backup_count=5, retention_days=30,
    )
    _log_manager.setup()
    _log_manager.cleanup_old_logs()
    config.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    storage = get_storage()
    try:
        storage.recover_interrupted_local_sessions()
        storage.cleanup_expired_context_events(retention_days=90)
    except Exception as exc:
        logger.warning("启动恢复/清理本机上下文失败: %s", exc)
    if not storage.get_setting("recording_mode"):
        with storage._get_connection() as conn:
            used_visual = conn.execute("SELECT 1 FROM chunks LIMIT 1").fetchone() is not None
        write_settings(storage, {"recording_mode": "visual" if used_visual else "local"})
    values = read_settings(storage)
    try:
        path = chunks_directory(values)
    except (OSError, ValueError):
        logger.warning("已保存的切片目录不可用，暂用默认目录")
        path = chunks_directory({**values, "custom_chunks_dir": ""})
    apply_settings(values, path)
    _sync_refiner(values, bump_generation=False)
    if os.getenv("DAYFLOW_HOST_EXE"):
        from core.autostart import check_path_changed, update_autostart_path
        changed, _, _ = check_path_changed()
        if changed:
            ok, _ = update_autostart_path()
            if not ok:
                logger.warning("自启动路径需要在设置中重新绑定")
    logger.info("Dayflow Bridge v%s 启动", config.VERSION)


def _graceful_shutdown(timeout_s: float = 10.0) -> tuple[bool, list[str]]:
    """
    单一单调截止时间贯穿全部子系统与存储关闭：
    1. 拒绝新写入并等待在途写入 API 排空；
    2. 停止定时邮件线程；
    3. 停止录制并确认最终提交；
    4. 停止纯文本精炼 worker（关闭独立 AsyncClient）；
    5. 停止视觉分析调度器；
    6. 所有写入方确认退出后关闭 StorageManager 连接池。
    """
    global _storage, _recorder, _analysis, _refiner, _provider, _log_manager, _shutting_down, _mail_thread

    deadline = time.monotonic() + timeout_s
    failures: list[str] = []

    with _mutation_cond:
        _shutting_down = True
        drain_deadline = min(deadline, time.monotonic() + 1.5)
        while _active_mutations > 0:
            rem = drain_deadline - time.monotonic()
            if rem <= 0:
                failures.append("仍有进行中的写入请求未结束")
                break
            _mutation_cond.wait(timeout=rem)

    # 2. 停止邮件线程
    _mail_stop.set()
    if _mail_thread is not None and _mail_thread.is_alive():
        _mail_thread.join(timeout=max(0.2, min(1.0, deadline - time.monotonic())))
        if _mail_thread.is_alive():
            failures.append("邮件调度线程未能及时退出")
    if _mail_thread is not None and not _mail_thread.is_alive():
        _mail_thread = None

    # 3. 停止录制器并确认最终提交
    if _recording_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
        try:
            rec = _recorder
            if rec is not None:
                rec_deadline = min(deadline, time.monotonic() + 5.0)
                confirmed, err = rec.stop_recording(deadline=rec_deadline)
                if not confirmed:
                    failures.append(err or "录制器最终保存未确认")
        except Exception as exc:
            failures.append(f"停止录制异常: {type(exc).__name__}")
        finally:
            _recording_lock.release()
    else:
        failures.append("正在处理记录设置或设备操作，暂未停止记录")

    # 4. 停止纯文本精炼 worker（关闭独立 HTTP 客户端）
    ref = _refiner
    if ref is not None:
        try:
            ref_deadline = min(deadline, time.monotonic() + 1.5)
            if not ref.stop(deadline=ref_deadline):
                failures.append("纯文本精炼任务未能及时停止")
        except Exception as exc:
            failures.append(f"停止精炼异常: {type(exc).__name__}")

    # 5. 停止视觉分析调度器
    ana = _analysis
    if ana is not None:
        try:
            ana_deadline = min(deadline, time.monotonic() + 1.5)
            if not ana.stop_scheduler(deadline=ana_deadline):
                failures.append("视觉分析调度器未能及时停止")
        except Exception as exc:
            failures.append(f"停止视觉分析异常: {type(exc).__name__}")

    # 6. 仅当全部数据库写入方均已退出时关闭连接池
    all_writers_stopped = not failures and (ana is None or not ana.is_running) and (ref is None or not ref.is_running)
    if _storage is not None and all_writers_stopped:
        try:
            _storage.close()
            _storage = None
        except Exception as exc:
            failures.append(f"关闭数据库失败: {type(exc).__name__}")
    elif _storage is not None and not all_writers_stopped:
        failures.append("存在未退出写入方，暂未关闭存储")

    if not failures:
        _recorder = _analysis = _refiner = _provider = None
        logger.info("Bridge 已安全关闭")
        if _log_manager is not None:
            _log_manager.close()
            _log_manager = None

    return not failures, failures


def _shutdown() -> None:
    _graceful_shutdown(timeout_s=10.0)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _mail_thread
    _startup()
    _resume_analysis_queue()
    jobs = []
    _mail_stop.clear()
    if os.getenv("DAYFLOW_BRIDGE_TOKEN"):
        _mail_thread = threading.Thread(target=mail_loop, args=(get_storage(), _mail_stop), daemon=True, name="MailLoop")
        _mail_thread.start()
        if os.getenv("DAYFLOW_START_MINIMIZED") == "1":
            jobs.append(asyncio.create_task(startup_recording()))
    try:
        yield
    finally:
        _mail_stop.set()
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        _shutdown()


def mail_loop(storage, stop):
    from bridge.mail import check_email_schedule

    while not stop.is_set():
        try:
            check_email_schedule(storage)
        except Exception:
            logger.warning("检查日报邮件发送时间失败")
        stop.wait(30)


async def startup_recording():
    try:
        await asyncio.to_thread(start_recording)
    except HTTPException as exc:
        logger.warning("登录后无法自动录制: %s", exc.detail)
    except Exception:
        logger.warning("登录后无法自动录制，请检查录制设备")


app.router.lifespan_context = lifespan


# ── 系统 ──────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {"ok": True, "version": config.VERSION}


@app.post("/api/system/shutdown")
async def system_shutdown():
    """供 Tauri 托盘退出与更新安装调用的统一优雅停机入口（单一 10s 截止时间）。"""
    ok, failures = await asyncio.to_thread(_graceful_shutdown, 10.0)
    if not ok:
        raise HTTPException(503, "；".join(failures))
    return {"ok": True}


@app.get("/api/settings/all")
def get_all_settings():
    values = read_settings(get_storage())
    values["api_key_configured"] = bool(values["api_key"])
    for key in SECRET_KEYS & values.keys():
        values[key] = MASK if values[key] else ""
    return values


class SettingsUpdate(BaseModel):
    values: dict[str, str]


@app.post("/api/settings")
def update_settings(body: SettingsUpdate):
    global _recorder, _provider
    with _recording_lock:
        storage = get_storage()
        try:
            changes, values = updated_settings(read_settings(storage), body.values)
            recording_changed = bool(changes.keys() & RECORDING_KEYS)
            if recording_changed and _recorder is not None:
                if _recorder.is_recording:
                    raise HTTPException(409, "请先停止记录，再更改记录方式、上下文粒度、显示器、空闲检测或切片目录")
                confirmed, err = _recorder.stop_recording(deadline=time.monotonic() + 6.0)
                if not confirmed:
                    raise HTTPException(503, err or "上一次记录尚未确认保存")
            if changes.get("recording_mode") == "local" and _analysis and not _analysis.stop_scheduler():
                raise HTTPException(409, "请等待当前分析任务停止后再保存")
            directory = chunks_directory(values) if "custom_chunks_dir" in changes else config.CHUNKS_DIR
        except (OSError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        write_settings(storage, changes)
        apply_settings(values, directory)
        if changes:
            _bump_settings_gen()
        if recording_changed:
            _recorder = None
        if changes.keys() & {"api_url", "api_key", "api_model"}:
            _provider = None
            storage.retry_analysis_after_settings_change()
        if changes.keys() & {"api_url", "api_key", "api_model", "recording_mode", "local_ai_refinement"}:
            _sync_refiner(values, bump_generation=True)
        if changes.keys() & {"api_url", "api_key", "api_model", "recording_mode"}:
            _resume_analysis_queue()
    return {"ok": True, "apiKeyConfigured": bool(values["api_key"])}


# ── 时间轴 ────────────────────────────────────────────────────


@app.get("/api/cards/{date_str}")
def get_cards(date_str: str):
    """date_str 形如 2026-09-28"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, f"日期格式应为 YYYY-MM-DD，收到 {date_str!r}")
    cards = get_storage().get_cards_for_date(d)
    return {"cards": [
        {
            **card_to_dict(original),
            "displayStartTime": _iso(segment.start_time),
            "displayEndTime": _iso(segment.end_time),
            "durationMinutes": segment.duration_minutes,
        }
        for original, segment in activity_segments(cards, *day_bounds(d.date()))
    ]}


class CardUpdate(BaseModel):
    category: str | None = None
    title: str | None = None
    summary: str | None = None
    productivityScore: float | None = None


@app.patch("/api/cards/{card_id}")
async def update_card(card_id: int, body: CardUpdate):
    s = get_storage()
    ok = s.update_card(
        card_id,
        category=body.category,
        title=body.title,
        summary=body.summary,
        productivity_score=body.productivityScore,
    )
    if not ok:
        raise HTTPException(404, f"卡片 {card_id} 不存在")
    return {"ok": True}


@app.delete("/api/cards/{card_id}")
async def delete_card(card_id: int):
    undo_token = get_storage().delete_card_with_undo(card_id)
    if undo_token is None:
        raise HTTPException(404, f"卡片 {card_id} 不存在")
    return {"ok": True, "undoToken": undo_token}


class CardRestore(BaseModel):
    card: dict
    undoToken: str | None = None


@app.post("/api/cards/restore")
async def restore_card(body: CardRestore):
    """撤销删除：优先从服务端快照无损恢复分段与来源，并清空旧租约、递增版本。"""
    d = body.card
    if not isinstance(d.get("id"), int) or d["id"] <= 0:
        raise HTTPException(400, "无法识别待恢复的活动")

    def parse(v):
        return datetime.fromisoformat(v) if v else None

    card = ActivityCard(
        id=d.get("id"),
        category=d.get("category", ""),
        title=d.get("title", ""),
        summary=d.get("summary", ""),
        start_time=parse(d.get("startTime")),
        end_time=parse(d.get("endTime")),
        app_sites=[
            AppSite(
                name=a["name"],
                duration_seconds=a.get("durationSeconds", 0),
                icon_url=a.get("iconUrl"),
            )
            for a in d.get("appSites", [])
        ],
        distractions=[
            Distraction(
                description=x["description"],
                timestamp=x.get("timestamp", 0),
                duration_seconds=x.get("durationSeconds", 0),
            )
            for x in d.get("distractions", [])
        ],
        productivity_score=d.get("productivityScore", 0),
    )
    get_storage().restore_card_with_snapshot(card, undo_token=body.undoToken)
    return {"ok": True}


# ── 录制与精炼 ────────────────────────────────────────────────


@app.get("/api/recording/state")
def recording_state():
    storage = get_storage()
    values = read_settings(storage)
    r = _recorder
    mode = r.mode if r else values["recording_mode"]
    return {
        "recordingMode": mode,
        "contextMode": values["local_context_mode"],
        "refinementEnabled": values["local_ai_refinement"] == "1",
        "needsSetup": mode == "visual" and _needs_recording_setup(),
        "isRecording": bool(r and r.is_recording),
        "isPaused": bool(r and r.is_paused),
        "isIdlePaused": bool(r and r.is_idle_paused),
        "isPrivacyPaused": bool(r and r.is_privacy_paused),
    }


def _recording_mode(storage):
    return "visual" if storage.get_setting("recording_mode") == "visual" else "local"


def _needs_recording_setup():
    from urllib.parse import urlsplit
    if not config.API_MODEL or not config.API_BASE_URL:
        return True
    try:
        url = urlsplit(config.API_BASE_URL)
    except ValueError:
        return True
    return url.scheme not in {"http", "https"} or not (
        url.hostname and (config.API_KEY or url.hostname in {"localhost", "127.0.0.1", "::1"})
    )


def _resume_analysis_queue():
    storage = get_storage()
    if _recording_mode(storage) == "visual" and not _needs_recording_setup() and storage.analysis_queue_size():
        get_analysis().start_scheduler()


@app.post("/api/recording/start")
def start_recording():
    with _recording_lock:
        if _recorder is not None and _recorder.is_recording:
            return {"ok": True, "already": True}
        storage = get_storage()
        values = read_settings(storage)
        mode = values["recording_mode"]
        if mode == "visual" and _needs_recording_setup():
            raise HTTPException(412, "连接分析模型后即可录制")
        get_recorder().start_recording()
        if mode == "visual":
            get_analysis().start_scheduler()
        else:
            _sync_refiner(values, bump_generation=False)
        return {"ok": True}


@app.post("/api/recording/stop")
def stop_recording():
    with _recording_lock:
        if _recorder is None:
            return {"ok": True, "already": True}
        was_recording = _recorder.is_recording
        confirmed, err = _recorder.stop_recording(deadline=time.monotonic() + 6.0)
        if not confirmed:
            raise HTTPException(503, err or "停止记录最终保存未确认，请稍后重试")
        return {"ok": True} if was_recording else {"ok": True, "already": True}


@app.post("/api/recording/pause")
def pause_recording():
    with _recording_lock:
        if _recorder is not None and _recorder.is_recording:
            _recorder.pause_recording()
    return {"ok": True}


@app.post("/api/recording/resume")
def resume_recording():
    with _recording_lock:
        if _recorder is not None and _recorder.is_recording:
            _recorder.resume_recording()
    return {"ok": True}


@app.post("/api/refinement/run")
async def run_refinement_now():
    """手动立即触发一次本机纯文本精炼批次（与定时任务共用唯一 worker、租约和日额度）。"""
    storage = get_storage()
    values = read_settings(storage)
    if values["recording_mode"] != "local":
        raise HTTPException(400, "纯文本精炼仅适用于本机计时模式")
    if values["local_ai_refinement"] != "1":
        raise HTTPException(412, "请先在设置中开启纯文本 AI 精炼")
    if _needs_recording_setup():
        raise HTTPException(412, "请先配置有效的模型地址、名称与密钥")
    _sync_refiner(values, bump_generation=False)
    return await get_refiner().run_once_manual()


# ── 连接测试 ──────────────────────────────────────────────────


@app.post("/api/test/connection")
async def test_connection(body: SettingsUpdate | None = None):
    """按草稿或当前 recording_mode 校验模型输入能力（visual 识图 / local 纯文本 JSON）。"""
    current = read_settings(get_storage())
    temporary = bool(body and body.values)
    draft_mode = current["recording_mode"]
    if body and body.values:
        from core.llm_provider import DayflowBackendProvider
        from urllib.parse import urlsplit

        if "recording_mode" in body.values:
            candidate_mode = body.values["recording_mode"].strip()
            if candidate_mode not in {"local", "visual"}:
                raise HTTPException(400, "请选择有效的记录方式")
            draft_mode = candidate_mode

        draft = current | {
            key: value.strip()
            for key, value in body.values.items()
            if key in {"api_url", "api_model", "api_key"} and value != MASK
        }
        try:
            target = urlsplit(draft["api_url"])
            saved = urlsplit(current["api_url"])
            if target.scheme not in {"http", "https"} or not target.hostname or not draft["api_model"]:
                raise ValueError()
        except ValueError as exc:
            raise HTTPException(400, "请填写有效的模型地址和模型名称") from exc
        if (target.scheme, target.netloc) != (saved.scheme, saved.netloc) and body.values.get("api_key") in {None, MASK}:
            draft["api_key"] = ""
        provider = DayflowBackendProvider(draft["api_url"], draft["api_key"], draft["api_model"])
    else:
        provider = get_provider()
    require_vision = draft_mode == "visual"
    try:
        import inspect
        sig = inspect.signature(provider.test_connection)
        if "require_vision" in sig.parameters:
            ok, msg = await provider.test_connection(require_vision=require_vision)
        else:
            ok, msg = await provider.test_connection()
    finally:
        if temporary:
            await provider.close()
    return {"ok": ok, "message": msg, "mode": draft_mode}


# ── 日报 ──────────────────────────────────────────────────────


_report_lock = threading.Lock()


@app.get("/api/reports/dates")
def report_dates():
    with get_storage()._get_connection() as conn:
        rows = conn.execute(
            "SELECT report_date AS day FROM daily_reports "
            "UNION SELECT substr(start_time,1,10) FROM timeline_cards WHERE end_time > start_time "
            "UNION SELECT substr(end_time,1,10) FROM timeline_cards "
            "WHERE substr(end_time,1,10) > substr(start_time,1,10) "
            "AND replace(end_time,' ','T') <> substr(end_time,1,10) || 'T00:00:00' "
            "ORDER BY day DESC"
        )
        return {"dates": [row["day"] for row in rows]}


def _report_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD") from error


def _report_response(storage, day, local):
    revision = storage.get_report_revision(day.isoformat())
    supplement = revision.get("content") or ""
    content = local.markdown + evidence_markdown(local.evidence) if local else ""
    if supplement:
        label = "AI 补充" if revision.get("source_key") else "历史日报"
        content = f"{content}\n\n## {label}\n\n{supplement}".strip()
    return {
        "date": day.isoformat(),
        "content": content,
        "localSummary": local.markdown if local else "",
        "supplement": supplement,
        "evidence": local.evidence if local else [],
        "hasActivity": local is not None,
        "canSupplement": bool(local and local.evidence) and not _needs_recording_setup(),
        "isStale": bool(local and supplement and revision.get("source_key") != local.source_key),
        "isLegacy": bool(supplement and not revision.get("source_key")),
        "hasPrevious": bool(revision.get("has_previous")),
    }


@app.get("/api/reports/{date_str}")
def get_report(date_str: str):
    day = _report_date(date_str)
    storage = get_storage()
    return _report_response(storage, day, daily_summary(storage, day))


@app.post("/api/reports/{date_str}")
async def generate_report(date_str: str):
    day = _report_date(date_str)
    if not _report_lock.acquire(blocking=False):
        raise HTTPException(409, "已有日报正在补充，请稍候")
    try:
        storage = get_storage()
        local = await asyncio.to_thread(daily_summary, storage, day)
        if not local or not local.evidence:
            raise HTTPException(400, "这一天还没有可供补充的活动")
        revision = storage.get_report_revision(day.isoformat())
        if revision.get("source_key") != local.source_key:
            if _needs_recording_setup():
                raise HTTPException(412, "连接模型后即可补充日报")
            try:
                content = await get_provider().generate_report_insights(local.markdown, local.evidence)
            except Exception as error:
                logger.warning("日报补充失败: %s", type(error).__name__)
                raise HTTPException(502, "AI 补充暂时失败，本机总结可继续使用") from error
            storage.save_report_revision(day.isoformat(), content, local.source_key)
        latest = await asyncio.to_thread(daily_summary, storage, day)
        return _report_response(storage, day, latest)
    finally:
        _report_lock.release()


@app.post("/api/reports/{date_str}/restore")
def restore_report(date_str: str):
    day = _report_date(date_str)
    if not _report_lock.acquire(blocking=False):
        raise HTTPException(409, "请等待日报补充完成")
    try:
        storage = get_storage()
        if not storage.restore_report_revision(day.isoformat()):
            raise HTTPException(404, "这一日期暂无可恢复的上一版")
        return _report_response(storage, day, daily_summary(storage, day))
    finally:
        _report_lock.release()


# ── 统计 ──────────────────────────────────────────────────────


@app.get("/api/stats")
async def get_stats(days: int = 7):
    if days not in (7, 30):
        days = 7
    from bridge.stats_service import collect_stats
    storage = get_storage()
    stats = await asyncio.to_thread(collect_stats, storage, days)
    stats["dailyGoal"] = int(read_settings(storage)["daily_goal"])
    return stats


# ── 导出 ──────────────────────────────────────────────────────


@app.get("/api/export/csv")
async def export_csv_range(start: date, end: date):
    if not timedelta(0) <= end - start <= timedelta(days=366):
        raise HTTPException(400, "请选择一年以内的有效日期范围")
    return await asyncio.to_thread(_csv, start, end)


def _csv(start, end):
    import csv
    import io

    storage = get_storage()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["日期", "开始", "结束", "时长(分钟)", "类别", "标题", "摘要", "生产力评分"])
    for day, cards in ledger_days(storage, start, end).items():
        for card in cards:
            writer.writerow([
                day.isoformat(), card.start_time.strftime("%H:%M") if card.start_time else "",
                "24:00" if card.end_time.date() != day else card.end_time.strftime("%H:%M"),
                round(card.duration_minutes, 1), card.category, card.title, card.summary,
                round(card.productivity_score, 0),
            ])
    return buffer.getvalue()


# ── 开机自启 ──────────────────────────────────────────────────


@app.get("/api/autostart")
def get_autostart():
    from core.autostart import is_autostart_enabled, get_registered_path, get_exe_path
    registered = get_registered_path()
    current = get_exe_path()
    return {
        "enabled": is_autostart_enabled(),
        "stale": bool(registered and current and os.path.normcase(registered) != os.path.normcase(current)),
        "available": bool(current),
    }


@app.post("/api/autostart/{action}")
async def set_autostart(action: Literal["enable", "disable"]):
    from core.autostart import enable_autostart, disable_autostart
    fn = enable_autostart if action == "enable" else disable_autostart
    ok, msg = await asyncio.to_thread(fn)
    if not ok:
        raise HTTPException(500, msg)
    return {"ok": True, "message": msg}


# ── 存储 ──────────────────────────────────────────────────────


@app.get("/api/storage/info")
def storage_info():
    chunks = config.CHUNKS_DIR
    protected = protected_chunk_files(get_storage())
    total = 0
    removable = 0
    for path in chunk_files(chunks):
        try:
            total += path.stat().st_size
            removable += path.resolve() not in protected
        except OSError:
            continue
    limit = config.CHUNKS_MAX_SIZE_GB * 1024 ** 3
    return {
        "chunksDir": str(chunks),
        "usedBytes": total,
        "usedMb": round(total / 1024 / 1024, 1),
        "limitGb": config.CHUNKS_MAX_SIZE_GB,
        "percent": round(total / limit * 100, 1) if limit else 0,
        "dataDir": str(config.APP_DATA_DIR),
        "removableCount": removable,
    }


@app.post("/api/storage/clear-chunks")
async def clear_chunks():
    def clear():
        with _recording_lock:
            if _recorder is not None and _recorder.is_recording:
                raise HTTPException(409, "请先停止录制再清理切片")
            protected = protected_chunk_files(get_storage())
            chunks = config.CHUNKS_DIR
            removed = 0
            for path in chunk_files(chunks):
                try:
                    if path.resolve() in protected:
                        continue
                    path.unlink()
                    removed += 1
                except OSError:
                    logger.warning("无法删除切片 %s", path.name)
            return removed
    return {"ok": True, "removed": await asyncio.to_thread(clear)}
