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
import threading
import time
import urllib.request
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
        config.ensure_directories()
        log_file = config.APP_DATA_DIR / "dayflow.log"
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            encoding="utf-8",
        )
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

    # 端口被上一个没退干净的实例占着时，先把它顶掉。
    # 后台录屏工具重启频繁，留着旧进程会占着 8899 让新实例起不来。
    if _port_in_use():
        logging.info(f"bridge: 端口 {PORT} 已被占用，尝试结束旧进程")
        _kill_stale()
        for _ in range(5):
            if not _port_in_use():
                break
            time.sleep(0.4)

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


def _kill_stale() -> None:
    """结束占着端口的旧 bridge。找不到就算了 —— 可能是别的程序。"""
    if sys.platform != "win32":
        return
    try:
        import subprocess

        kwargs = {}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        out = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True, text=True, timeout=5,
            **kwargs,
        ).stdout
        pids = set()
        for line in out.splitlines():
            if f":{PORT}" in line and "LISTENING" in line.upper():
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(int(parts[-1]))
        for pid in pids:
            if pid == os.getpid():
                continue
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=10,
                           **kwargs)
            print(f"bridge: 已结束旧进程 {pid}", flush=True)
        if pids:
            time.sleep(0.6)
    except Exception as e:
        print(f"bridge: 清理旧进程失败（忽略）: {e}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
