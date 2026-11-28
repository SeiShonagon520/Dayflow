"""
Dayflow bridge 可执行入口

PyInstaller 的 onefile 模式会把「入口脚本」冻进 exe，所以这个 exe
不能再用 `python -m uvicorn ...` 的方式传参 —— 参数会被忽略。
它自己就是命令行程序：启动 uvicorn，绑定到 127.0.0.1 的固定端口。

绑定回环而不是 0.0.0.0 是有意的：这个服务没有鉴权，能读写用户的
屏幕活动记录，暴露到局域网等于把数据公开。
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8899


def _root() -> Path:
    """项目根目录。打包后 core/ database/ 已经被冻进 exe 了，
    但配置文件和数据库仍在 %LOCALAPPDATA%。"""
    env = os.environ.get("DAYFLOW_ROOT")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _ensure_importable() -> None:
    r = str(_root())
    if r not in sys.path:
        sys.path.insert(0, r)


def _init_early_logging() -> None:
    try:
        import config
        from core.log_manager import LogManager
        config.ensure_directories()
        LogManager(
            log_dir=config.APP_DATA_DIR,
            log_filename="dayflow.log",
            max_size_mb=5,
            backup_count=5,
            retention_days=30,
        ).setup()
    except Exception:
        pass


def main() -> int:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    _ensure_importable()
    _init_early_logging()

    import uvicorn

    if _port_in_use():
        logging.error("Dayflow 后台端口 %s 已被占用，请先退出另一实例", PORT)
        return 1

    logging.info(f"bridge: 启动 http://{HOST}:{PORT}")
    try:
        uvicorn.run(
            "bridge.server:app",
            host=HOST,
            port=PORT,
            log_level="warning",
            access_log=False,
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"bridge: 启动失败 {type(e).__name__}: {e}", exc_info=True)
        return 1
    return 0


def _port_in_use() -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((HOST, PORT)) == 0


if __name__ == "__main__":
    import multiprocessing

    # PyInstaller onefile 启动独立 UIA spawn 子进程前必须先调用 freeze_support()，
    # 防止子进程重入 Uvicorn。
    multiprocessing.freeze_support()
    raise SystemExit(main())
