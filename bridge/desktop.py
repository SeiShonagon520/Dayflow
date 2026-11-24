"""Desktop operations that run on the local bridge."""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
from bridge.backup import Backup, RESTORABLE_SETTINGS, export_backup, import_backup
from bridge.settings import MASK, SECRET_KEYS, apply_settings, read_settings, updated_settings

router = APIRouter(prefix="/api")


def storage():
    from bridge.server import get_storage
    return get_storage()


@router.get("/monitors")
def monitors():
    try:
        import win32api
        screens = win32api.EnumDisplayMonitors()
    except (ImportError, OSError):
        screens = []
    return {"monitors": [{"index": i, "width": rect[2] - rect[0], "height": rect[3] - rect[1]}
                         for i, (_, _, rect) in enumerate(screens)]}


class EmailDraft(BaseModel):
    values: dict[str, str]


@router.post("/email/test")
def test_email(draft: EmailDraft | None = None):
    from bridge.mail import send_test_email
    ok, message = send_test_email(storage(), draft.values if draft else None)
    if not ok:
        raise HTTPException(400, message)
    return {"ok": True}


@router.get("/email/status")
def email_status():
    with storage()._get_connection() as conn:
        row = conn.execute(
            "SELECT send_time,success,error_message FROM email_send_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {"last": dict(row) if row else None}


@router.get("/export/dashboard")
def export_dashboard(start: date, end: date):
    if not timedelta(0) <= end - start <= timedelta(days=366):
        raise HTTPException(400, "请选择一年以内的有效日期范围")
    from core.dashboard_exporter import DashboardExporter
    return {"content": DashboardExporter(storage()).render(start, end)}


@router.get("/backup")
def backup_export():
    return export_backup(storage())


@router.post("/backup")
def backup_import(backup: Backup, restore_settings: bool = False):
    from bridge import server

    try:
        db = storage()
        if not restore_settings:
            return import_backup(db, backup)
        allowed = {k: v for k, v in backup.settings.items() if k in RESTORABLE_SETTINGS}
        with server._recording_lock:
            if server._recorder is not None and server._recorder.is_recording:
                raise HTTPException(409, "请停止录制后再恢复录制设置")
            changes, values = updated_settings(read_settings(db), allowed)
            result = import_backup(db, backup, changes)
            apply_settings(values, config.CHUNKS_DIR)
            server._recorder = None
            return result
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/logs")
def get_logs():
    path = config.APP_DATA_DIR / "dayflow.log"
    if not path.is_file():
        return {"content": ""}
    with path.open("rb") as file:
        file.seek(max(0, path.stat().st_size - 48 * 1024))
        content = file.read().decode("utf-8", "ignore")
    db = storage()
    for key in SECRET_KEYS:
        secret = db.get_setting(key)
        if secret:
            content = content.replace(secret, MASK)
    if config.API_KEY:
        content = content.replace(config.API_KEY, MASK)
    return {"content": "\n".join(content.splitlines()[-150:])}


@router.get("/update/check")
def check_update():
    from core.desktop_update import check_update as fetch
    try:
        info = fetch()
    except Exception as exc:
        raise HTTPException(502, "无法查询 GitHub 发行版，请稍后重试") from exc
    return {
        "hasUpdate": info.has_update, "currentVersion": config.VERSION,
        "latestVersion": info.latest_version, "downloadUrl": info.download_url,
        "notes": info.release_notes, "fileSize": info.file_size,
        "verifiedInstaller": bool(info.digest),
    }


@router.post("/update/download")
def download_update():
    from core.desktop_update import stage_update
    try:
        return {"digest": stage_update()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "下载安装包失败，请检查网络后重试") from exc
