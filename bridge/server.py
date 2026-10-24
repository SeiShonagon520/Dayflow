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
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 让 bridge 能 import 到项目根下的 core / database
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from core.types import ActivityCard, AppSite, Distraction
from database.storage import StorageManager

logger = logging.getLogger("bridge")

app = FastAPI(title="Dayflow Bridge", version=config.VERSION)

# 放行本地回环及 Tauri 客户端请求。服务仅绑定在 127.0.0.1 回环地址上。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_storage: StorageManager | None = None
_recorder = None        # core.recorder.RecordingManager
_analysis = None        # core.analysis.AnalysisManager
_provider = None        # core.llm_provider.DayflowBackendProvider
_email = None           # core.email_service.EmailService


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
    config.ensure_directories()
    get_storage()
    logger.info(f"Dayflow Bridge v{config.VERSION} 启动")


def _shutdown() -> None:
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
    logger.info("Bridge 已关闭")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _startup()
    yield
    _shutdown()


# 用 lifespan 而不是已废弃的 on_event
app.router.lifespan_context = lifespan


# ── 系统 ──────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {"ok": True, "version": config.VERSION}


@app.get("/api/settings/all")
def get_all_settings():
    keys = [
        "api_url", "api_key", "api_model", "theme", "daily_goal",
        "idle_pause_enabled", "idle_pause_timeout_min", "record_output_idx",
        "chunks_max_size_gb", "custom_chunks_dir",
        "email_enabled", "email_sender", "email_auth_code",
        "email_receiver", "email_send_times",
    ]
    s = get_storage()
    out = {k: s.get_setting(k, "") for k in keys}
    # API Key 不回传明文，只告诉前端配没配
    out["api_key"] = "********" if out.get("api_key") else ""
    out["api_key_configured"] = bool(s.get_setting("api_key", ""))
    return out


class SettingsUpdate(BaseModel):
    values: dict[str, str]


@app.post("/api/settings")
def update_settings(body: SettingsUpdate):
    s = get_storage()
    for k, v in body.values.items():
        s.set_setting(k, str(v))
    # 让运行中的模块立刻用上新配置
    if "api_url" in body.values:
        config.API_BASE_URL = body.values["api_url"]
    if "api_key" in body.values:
        config.API_KEY = body.values["api_key"]
    if "api_model" in body.values:
        config.API_MODEL = body.values["api_model"]
    return {"ok": True}


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
        app_sites=[AppSite(name=a["name"], duration_seconds=a.get("durationSeconds", 0))
                   for a in d.get("appSites", [])],
        distractions=[Distraction(description=x["description"],
                                  timestamp=x.get("timestamp", 0),
                                  duration_seconds=x.get("durationSeconds", 0))
                      for x in d.get("distractions", [])],
        productivity_score=d.get("productivityScore", 0),
    )
    get_storage().save_card(card)
    return {"ok": True}


# ── 录制 ──────────────────────────────────────────────────────


@app.get("/api/recording/state")
def recording_state():
    r = get_recorder()
    return {
        "isRecording": r.is_recording,
        "isPaused": r.is_paused,
        "isIdlePaused": r.is_idle_paused,
    }


@app.post("/api/recording/start")
def start_recording():
    r = get_recorder()
    if r.is_recording:
        return {"ok": True, "already": True}
    if not config.API_KEY:
        raise HTTPException(400, "尚未配置 API Key，请先到设置页填写")
    r.start_recording()
    get_analysis().start_scheduler()
    return {"ok": True}


@app.post("/api/recording/stop")
async def stop_recording():
    """停止会保存视频切片、等待分析器收尾，必须放到线程里"""
    r = get_recorder()
    if not r.is_recording:
        return {"ok": True, "already": True}
    await asyncio.to_thread(r.stop_recording)
    return {"ok": True}


@app.post("/api/recording/pause")
def pause_recording():
    r = get_recorder()
    if r.is_recording:
        r.pause_recording()
    return {"ok": True}


@app.post("/api/recording/resume")
def resume_recording():
    r = get_recorder()
    if r.is_recording:
        r.resume_recording()
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
async def test_connection():
    """调 AI 接口要网络往返，交给 provider 的现成实现"""
    ok, msg = await get_provider().test_connection()
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
    content = get_storage().get_daily_report(date_str)
    return {"date": date_str, "content": content or ""}


@app.post("/api/reports/{date_str}")
async def generate_report(date_str: str):
    """生成日报要调 AI，耗时可达数十秒 —— 用 provider 的现成实现"""
    from datetime import datetime
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")

    s = get_storage()
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
    return await asyncio.to_thread(collect_stats, get_storage(), days)


# ── 导出 ──────────────────────────────────────────────────────

@app.get("/api/export/csv/{date_str}")
async def export_csv(date_str: str):
    from datetime import datetime
    import csv
    import io
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")

    def _build():
        cards = get_storage().get_cards_for_date(d)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["开始", "结束", "时长(分钟)", "类别", "标题", "摘要", "生产力评分"])
        for c in cards:
            w.writerow([
                c.start_time.strftime("%H:%M") if c.start_time else "",
                c.end_time.strftime("%H:%M") if c.end_time else "",
                round(c.duration_minutes, 1),
                c.category, c.title, c.summary,
                round(c.productivity_score, 0),
            ])
        return buf.getvalue()

    return await asyncio.to_thread(_build)


# ── 开机自启 ──────────────────────────────────────────────────


@app.get("/api/autostart")
def get_autostart():
    from core.autostart import is_autostart_enabled, get_registered_path, get_exe_path
    registered = get_registered_path()
    current = get_exe_path()
    return {
        "enabled": is_autostart_enabled(),
        # 路径变了就说明用户移动过程序，注册表里还指着老位置
        "stale": bool(registered and current and registered != current),
    }


@app.post("/api/autostart/{action}")
async def set_autostart(action: str):
    """action: enable | disable"""
    from core.autostart import enable_autostart, disable_autostart
    fn = enable_autostart if action == "enable" else disable_autostart
    ok, msg = await asyncio.to_thread(fn)
    if not ok:
        raise HTTPException(500, msg)
    return {"ok": True, "message": msg}


# ── 软件更新 ──────────────────────────────────────────────────


@app.get("/api/update/check")
async def check_update():
    """要访问 GitHub，放线程里"""
    from core.updater import UpdateManager

    def _run():
        info = UpdateManager().check_update()
        return {
            "hasUpdate": bool(info.has_update),
            "currentVersion": info.current_version or config.VERSION,
            "latestVersion": info.latest_version or config.VERSION,
            "downloadUrl": info.download_url or "",
            "notes": info.release_notes or "",
            "fileSize": info.file_size or 0,
        }

    return await asyncio.to_thread(_run)


# ── 存储 ──────────────────────────────────────────────────────


@app.get("/api/storage/info")
def storage_info():
    """磁盘占用与切片目录大小"""
    chunks = config.CHUNKS_DIR

    def _size_of(p: Path) -> int:
        if not p.exists():
            return 0
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

    total = _size_of(chunks)
    limit = config.CHUNKS_MAX_SIZE_GB * 1024 ** 3
    return {
        "chunksDir": str(chunks),
        "usedBytes": total,
        "usedMb": round(total / 1024 / 1024, 1),
        "limitGb": config.CHUNKS_MAX_SIZE_GB,
        "percent": round(total / limit * 100, 1) if limit else 0,
        "dataDir": str(config.APP_DATA_DIR),
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
    """删掉所有临时视频切片。分析完成的切片本来就会被自动清理，
    这里是给「攒太多了」的情况兜底。"""
    import shutil

    def _run():
        chunks = config.CHUNKS_DIR
        n = 0
        if chunks.exists():
            for f in chunks.iterdir():
                try:
                    if f.is_file():
                        f.unlink()
                        n += 1
                    elif f.is_dir():
                        shutil.rmtree(f)
                except Exception as e:
                    logger.warning(f"删除 {f} 失败: {e}")
        return n

    return {"ok": True, "removed": await asyncio.to_thread(_run)}
