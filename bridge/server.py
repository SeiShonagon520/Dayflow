"""
Dayflow Python 后端桥接层

把 core/ 和 database/ 的能力暴露成 HTTP API，供 Tauri 前端调用。

设计要点：
  · 只做「翻译」，不含业务逻辑。录制、分析、存储的实现在 core/ 里，
    这里只是把 dataclass 转成 JSON、把 HTTP 请求转成方法调用。
  · core/ 和 database/ 不依赖本文件，也不依赖任何 Web 框架 ——
    它们仍然可以独立运行（比如命令行工具、测试）。
  · 所有耗时操作（AI 分析、SMTP 邮件、版本检查）都在线程里跑，
    绝不能阻塞事件循环，否则整个界面会卡死。
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import sys
import threading
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

ORIGINS = ["http://tauri.localhost", "https://tauri.localhost", "tauri://localhost",
           "http://localhost:1420", "http://127.0.0.1:1420"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def authorize_bridge(request: Request, call_next):
    if request.method != "OPTIONS" and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin and origin not in ORIGINS:
            return JSONResponse({"detail": "不允许此来源访问 Dayflow"}, status_code=403)
        token = os.getenv("DAYFLOW_BRIDGE_TOKEN")
        if token and not hmac.compare_digest(request.headers.get("x-dayflow-session", "").encode(), token.encode()):
            return JSONResponse({"detail": "Dayflow 后台会话未就绪"}, status_code=401)
    return await call_next(request)


_recording_lock = threading.RLock()
_storage: StorageManager | None = None
_recorder = None        # core.recorder.RecordingManager
_analysis = None        # core.analysis.AnalysisManager
_provider = None        # core.llm_provider.DayflowBackendProvider


def get_storage() -> StorageManager:
    global _storage
    if _storage is None:
        _storage = StorageManager()
    return _storage


def get_recorder():
    """录制管理器（懒加载 —— 它一初始化就会开始占用摄像头/屏幕句柄）"""
    global _recorder
    if _recorder is None:
        from core.recorder import RecordingManager
        _recorder = RecordingManager(get_storage())
    return _recorder


def get_analysis():
    global _analysis
    if _analysis is None:
        from core.analysis import AnalysisManager
        _analysis = AnalysisManager(get_storage())
    return _analysis


def get_provider():
    global _provider
    if _provider is None:
        from core.llm_provider import DayflowBackendProvider
        _provider = DayflowBackendProvider()
    return _provider


# ── 序列化 ────────────────────────────────────────────────────
# core.types 的 dataclass 不含 Qt，纯 dataclasses，asdict 就能用。
# 但 datetime 需要转 ISO 字符串，Enum 需要转 value，所以手写映射，
# 不用 asdict —— 那样会漏掉类型转换。


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


# ── 生命周期 ──────────────────────────────────────────────────


def _startup() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from core.log_manager import LogManager
    LogManager(
        log_dir=config.APP_DATA_DIR,
        log_filename="dayflow.log",
        max_size_mb=5, backup_count=5, retention_days=30,
    ).setup()
    config.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    values = read_settings(get_storage())
    try:
        path = chunks_directory(values)
    except (OSError, ValueError):
        logger.warning("已保存的切片目录不可用，暂用默认目录")
        path = chunks_directory({**values, "custom_chunks_dir": ""})
    apply_settings(values, path)
    if os.getenv("DAYFLOW_HOST_EXE"):
        from core.autostart import check_path_changed, update_autostart_path
        changed, _, _ = check_path_changed()
        if changed:
            ok, _ = update_autostart_path()
            if not ok:
                logger.warning("自启动路径需要在设置中重新绑定")
    logger.info(f"Dayflow Bridge v{config.VERSION} 启动")


def _shutdown() -> None:
    global _storage, _recorder, _analysis, _provider
    for name, mgr in (("recorder", _recorder), ("analysis", _analysis)):
        if mgr is None:
            continue
        try:
            if name == "recorder" and mgr.is_recording:
                mgr.stop_recording()
            if name == "analysis":
                mgr.stop_scheduler()
        except Exception as e:
            logger.warning(f"关闭 {name} 失败: {e}")
    if _storage is not None:
        _storage.close()
    _storage = _recorder = _analysis = _provider = None
    logger.info("Bridge 已关闭")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _startup()
    jobs = []
    stop = threading.Event()
    if os.getenv("DAYFLOW_BRIDGE_TOKEN"):
        threading.Thread(target=mail_loop, args=(get_storage(), stop), daemon=True).start()
        jobs.append(asyncio.create_task(cache_yesterday()))
        if os.getenv("DAYFLOW_START_MINIMIZED") == "1":
            jobs.append(asyncio.create_task(startup_recording()))
    try:
        yield
    finally:
        stop.set()
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


async def cache_yesterday():
    await asyncio.sleep(3)
    if not config.API_KEY:
        return
    day = (date.today() - timedelta(days=1)).isoformat()
    try:
        await _generate_report(day, cached_only=True)
    except HTTPException:
        pass


# 用 lifespan 而不是已废弃的 on_event
app.router.lifespan_context = lifespan


# ── 系统 ──────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {"ok": True, "version": config.VERSION}


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
            if recording_changed and _recorder is not None and _recorder.is_recording:
                raise HTTPException(409, "请先停止录制，再修改录制显示器、空闲检测或切片目录")
            directory = chunks_directory(values) if "custom_chunks_dir" in changes else config.CHUNKS_DIR
        except (OSError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        write_settings(storage, changes)
        apply_settings(values, directory)
        if recording_changed:
            _recorder = None
        if changes.keys() & {"api_url", "api_key", "api_model"}:
            _provider = None
    return {"ok": True, "apiKeyConfigured": bool(values["api_key"])}


# ── 时间轴 ────────────────────────────────────────────────────


@app.get("/api/cards/{date_str}")
def get_cards(date_str: str):
    """date_str 形如 2026-09-28"""
    from datetime import datetime
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, f"日期格式应为 YYYY-MM-DD，收到 {date_str!r}")
    cards = get_storage().get_cards_for_date(d)
    return {"cards": [card_to_dict(c) for c in cards]}


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
    ok = get_storage().delete_card(card_id)
    if not ok:
        raise HTTPException(404, f"卡片 {card_id} 不存在")
    return {"ok": True}


class CardRestore(BaseModel):
    card: dict


@app.post("/api/cards/restore")
async def restore_card(body: CardRestore):
    """撤销删除：把整张卡片写回去"""
    d = body.card
    if not isinstance(d.get("id"), int) or d["id"] <= 0:
        raise HTTPException(400, "无法识别待恢复的活动")
    from datetime import datetime

    def parse(v):
        return datetime.fromisoformat(v) if v else None

    card = ActivityCard(
        id=d.get("id"),
        category=d.get("category", ""),
        title=d.get("title", ""),
        summary=d.get("summary", ""),
        start_time=parse(d.get("startTime")),
        end_time=parse(d.get("endTime")),
        app_sites=[AppSite(name=a["name"], duration_seconds=a.get("durationSeconds", 0),
                           icon_url=a.get("iconUrl"))
                   for a in d.get("appSites", [])],
        distractions=[Distraction(description=x["description"],
                                  timestamp=x.get("timestamp", 0),
                                  duration_seconds=x.get("durationSeconds", 0))
                      for x in d.get("distractions", [])],
        productivity_score=d.get("productivityScore", 0),
    )
    get_storage().save_card(card, restore_id=card.id)
    return {"ok": True}


# ── 录制 ──────────────────────────────────────────────────────


@app.get("/api/recording/state")
def recording_state():
    r = _recorder
    return {
        "needsSetup": _needs_recording_setup(),
        "isRecording": bool(r and r.is_recording),
        "isPaused": bool(r and r.is_paused),
        "isIdlePaused": bool(r and r.is_idle_paused),
    }


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


@app.post("/api/recording/start")
def start_recording():
    with _recording_lock:
        if _recorder is not None and _recorder.is_recording:
            return {"ok": True, "already": True}
        if _needs_recording_setup():
            raise HTTPException(412, "连接分析模型后即可录制")
        get_recorder().start_recording()
        get_analysis().start_scheduler()
        return {"ok": True}


@app.post("/api/recording/stop")
def stop_recording():
    with _recording_lock:
        if _recorder is None or not _recorder.is_recording:
            return {"ok": True, "already": True}
        _recorder.stop_recording()
        return {"ok": True}


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


# ── 分析进度 ──────────────────────────────────────────────────


@app.get("/api/analysis/progress")
def analysis_progress():
    """待分析批次数量，供前端显示真实进度而不是假进度条"""
    try:
        pending = get_storage().get_pending_chunks(limit=1000)
        return {"pending": len(pending), "analyzing": _analysis is not None}
    except Exception as e:
        logger.warning(f"读取分析进度失败: {e}")
        return {"pending": 0, "analyzing": False}


# ── 连接测试 ──────────────────────────────────────────────────


@app.post("/api/test/connection")
async def test_connection(body: SettingsUpdate | None = None):
    """调 AI 接口要网络往返，交给 provider 的现成实现"""
    provider = get_provider()
    if body and body.values:
        from core.llm_provider import DayflowBackendProvider
        from urllib.parse import urlsplit

        current = read_settings(get_storage())
        draft = current | {key: value.strip() for key, value in body.values.items()
                           if key in {"api_url", "api_model", "api_key"} and value != MASK}
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
    ok, msg = await provider.test_connection()
    return {"ok": ok, "message": msg}


# ── 日报 ──────────────────────────────────────────────────────


@app.get("/api/reports/dates")
def report_dates():
    """已生成日报的日期列表"""
    try:
        s = get_storage()
        with s._get_connection() as conn:
            rows = conn.execute(
                "SELECT report_date FROM daily_reports ORDER BY report_date DESC"
            ).fetchall()
        return {"dates": [r["report_date"] for r in rows]}
    except Exception as e:
        logger.warning(f"读取日报列表失败: {e}")
        return {"dates": []}


@app.get("/api/reports/{date_str}")
def get_report(date_str: str):
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD") from exc
    storage = get_storage()
    content = storage.get_daily_report(date_str) or ""
    return {"date": date_str, "content": content, "hasActivity": bool(content or storage.get_cards_for_date(day))}


@app.post("/api/reports/{date_str}")
async def generate_report(date_str: str):
    return await _generate_report(date_str)


async def _generate_report(date_str: str, *, cached_only=False):
    from datetime import datetime
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")

    s = get_storage()
    if cached_only and s.get_daily_report(date_str):
        return
    cards = s.get_cards_for_date(d)
    if not cards:
        raise HTTPException(400, f"{date_str} 没有活动记录，无法生成日报")

    try:
        content = await get_provider().generate_daily_report(cards, date_str)
    except Exception as e:
        logger.error(f"生成日报失败: {e}")
        raise HTTPException(502, f"生成失败：{type(e).__name__}: {e}")

    s.save_daily_report(date_str, content)
    return {"date": date_str, "content": content}


# ── 统计 ──────────────────────────────────────────────────────


@app.get("/api/stats")
async def get_stats(days: int = 7):
    """
    统计聚合。遍历 days 天的卡片，在线程里跑 ——
    一个月的数据量已经够阻塞事件循环一会儿了。
    """
    if days not in (7, 30):
        days = 7
    from bridge.stats_service import collect_stats
    storage = get_storage()
    stats = await asyncio.to_thread(collect_stats, storage, days)
    stats["dailyGoal"] = int(read_settings(storage)["daily_goal"])
    return stats


# ── 导出 ──────────────────────────────────────────────────────

@app.get("/api/export/csv/{date_str}")
async def export_csv(date_str: str):
    try:
        day = date.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD") from exc
    return await asyncio.to_thread(_csv, day, day)


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
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        for card in storage.get_cards_for_date(datetime.combine(day, datetime.min.time())):
            writer.writerow([
                day.isoformat(), card.start_time.strftime("%H:%M") if card.start_time else "",
                card.end_time.strftime("%H:%M") if card.end_time else "",
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
        # 路径变了就说明用户移动过程序，注册表里还指着老位置
        "stale": bool(registered and current and os.path.normcase(registered) != os.path.normcase(current)),
        "available": bool(current),
    }


@app.post("/api/autostart/{action}")
async def set_autostart(action: Literal["enable", "disable"]):
    """action: enable | disable"""
    from core.autostart import enable_autostart, disable_autostart
    fn = enable_autostart if action == "enable" else disable_autostart
    ok, msg = await asyncio.to_thread(fn)
    if not ok:
        raise HTTPException(500, msg)
    return {"ok": True, "message": msg}


# ── 软件更新 ──────────────────────────────────────────────────


# ── 存储 ──────────────────────────────────────────────────────


@app.get("/api/storage/info")
def storage_info():
    """磁盘占用与切片目录大小"""
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


class CacheLimit(BaseModel):
    gb: int


@app.post("/api/storage/cache-limit")
async def set_cache_limit(body: CacheLimit):
    gb = max(1, min(int(body.gb), 500))
    get_storage().set_setting("chunks_max_size_gb", str(gb))
    config.CHUNKS_MAX_SIZE_GB = gb
    return {"ok": True, "limitGb": gb}


@app.post("/api/storage/clear-chunks")
async def clear_chunks():
    """清理已经脱离分析队列的临时文件。"""
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
