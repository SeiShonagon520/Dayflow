"""把「跑一遍 + 打印每个检查项」的前端自检包成 pytest 测试。

这些检查脚本原本叫 test_*.py，顶层 raise SystemExit(1) 会在
pytest 收集阶段整个崩掉（INTERNALERROR，0 个测试跑），
连带把其它测试文件也废掉。所以改名为 check_*.py，
pytest 不再收集，由这个文件以子进程方式调用。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = [
    "check_test_interaction_web",
    "check_test_responsive_web",
    "check_test_motion_web",
    "check_test_hook_order_web",
]


def _run(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
        cwd=str(ROOT),
    )
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_web_suites():
    """四个前端自检套件：动效、响应式、交互、hook 顺序。"""
    failed = []
    for name in SUITES:
        ok, out = _run(name)
        if not ok:
            lines = [l for l in out.splitlines()
                     if "FAIL" in l or "✗" in l or l.strip().startswith("-")]
            failed.append(f"{name}:\n" + "\n".join(lines[-15:]))
    assert not failed, "\n\n".join(failed)

