"""Desktop preferences shared by the bridge and the existing database."""

import re
from pathlib import Path
from urllib.parse import urlsplit

import config

MASK = "********"
SECRET_KEYS = {"api_key", "email_auth", "email_auth_code"}
DEFAULTS = {
    "api_url": config.API_BASE_URL,
    "api_key": config.API_KEY,
    "api_model": config.API_MODEL,
    "theme": "light",
    "daily_goal": "8",
    "record_output_idx": "0",
    "idle_pause_enabled": "1" if config.IDLE_PAUSE_ENABLED else "0",
    "idle_pause_timeout_min": str(config.IDLE_PAUSE_TIMEOUT_SECONDS // 60),
    "chunks_max_size_gb": str(config.CHUNKS_MAX_SIZE_GB),
    "custom_chunks_dir": config.CUSTOM_CHUNKS_DIR,
    "email_enabled": "0",
    "email_sender": "",
    "email_auth_code": "",
    "email_receiver": "",
    "email_send_times": "12:00,22:00",
    "reduce_motion": "system",
}
RECORDING_KEYS = {"record_output_idx", "idle_pause_enabled", "idle_pause_timeout_min", "custom_chunks_dir"}
LIMITS = {"record_output_idx": (-1, 63), "idle_pause_timeout_min": (1, 120),
          "chunks_max_size_gb": (1, 500), "daily_goal": (1, 24)}


def email_times(value):
    times = set()
    for piece in value.strip().split(","):
        match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", piece.strip())
        if not match:
            raise ValueError("发送时间应为 HH:MM，多个时间用逗号分隔")
        hour, minute = int(match[1]), int(match[2] or 0)
        if hour > 23 or minute > 59:
            raise ValueError("发送时间超出有效范围")
        times.add((hour, minute))
    return sorted(times)


def read_settings(storage):
    with storage._get_connection() as conn:
        stored = dict(conn.execute("SELECT key, value FROM settings"))
    values = {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
    if "email_auth_code" not in stored:
        values["email_auth_code"] = stored.get("email_auth", "")
    for key in ("email_enabled", "idle_pause_enabled"):
        values[key] = "1" if values[key].strip().lower() in {"1", "true", "on"} else "0"
    for key, (lo, hi) in LIMITS.items():
        try:
            if not lo <= int(values[key]) <= hi:
                raise ValueError()
        except ValueError:
            values[key] = DEFAULTS[key]
    try:
        email_times(values["email_send_times"])
    except ValueError:
        values["email_send_times"] = DEFAULTS["email_send_times"]
    return values


def updated_settings(current, patch):
    if patch.keys() - DEFAULTS.keys():
        raise ValueError("包含未知设置项")
    changes = {k: v.strip() for k, v in patch.items() if k not in SECRET_KEYS or v != MASK}
    if "api_url" in changes:
        target = urlsplit(changes["api_url"])
        if target.scheme not in {"http", "https"} or not target.hostname:
            raise ValueError("请输入有效的模型地址")
        if current["api_key"] and "api_key" not in changes:
            try:
                existing = urlsplit(current["api_url"])
                same_service = (existing.scheme, existing.netloc) == (target.scheme, target.netloc)
            except ValueError:
                same_service = False
            if not same_service:
                changes["api_key"] = ""
    if "api_model" in changes and not changes["api_model"]:
        raise ValueError("请输入模型名称")
    for key, (lo, hi) in LIMITS.items():
        if key in changes:
            try:
                number = int(changes[key])
                if not lo <= number <= hi:
                    raise ValueError()
            except ValueError:
                raise ValueError(f"{key} 必须是 {lo} 到 {hi} 的整数") from None
            changes[key] = str(number)
    if "email_send_times" in changes:
        times = email_times(changes["email_send_times"] or DEFAULTS["email_send_times"])
        changes["email_send_times"] = ",".join(f"{h:02}:{m:02}" for h, m in times)
    values = current | changes
    if any(key.startswith("email_") for key in changes) and values["email_enabled"] == "1" and not all(
        values[k] for k in ("email_sender", "email_auth_code", "email_receiver")
    ):
        raise ValueError("启用邮件日报前请填写发件邮箱、收件邮箱和授权码")
    return {k: v for k, v in changes.items() if current[k] != v}, values


def chunks_directory(values):
    custom = values["custom_chunks_dir"]
    path = Path(custom) if custom else config.APP_DATA_DIR / "chunks"
    if custom and not path.is_absolute():
        raise ValueError("切片目录必须是绝对路径")
    path.mkdir(parents=True, exist_ok=True)
    return path


def apply_settings(values, chunks_dir):
    config.API_BASE_URL = values["api_url"]
    config.API_KEY = values["api_key"]
    config.API_MODEL = values["api_model"]
    config.CHUNKS_DIR = chunks_dir
    config.CUSTOM_CHUNKS_DIR = values["custom_chunks_dir"]
    config.CHUNKS_MAX_SIZE_GB = int(values["chunks_max_size_gb"])
    config.IDLE_PAUSE_ENABLED = values["idle_pause_enabled"] == "1"
    config.IDLE_PAUSE_TIMEOUT_SECONDS = int(values["idle_pause_timeout_min"]) * 60


def write_settings(storage, changes):
    with storage._get_connection() as conn, conn:
        write_settings_to_connection(conn, changes)


def write_settings_to_connection(conn, changes):
    conn.executemany(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
        changes.items(),
    )
