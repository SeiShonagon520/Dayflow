"""
把 bridge 打包成单文件 exe，供 Tauri 当 sidecar 拉起。

    pip install pyinstaller
    python bridge/build_bridge.py

产物：src-tauri/resources/python-bridge-<target-triple>.exe。
"""
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src-tauri" / "resources"

# uvicorn.run 通过字符串加载，PyInstaller 无法静态发现入口应用；
# comtypes.gen.UIAutomationClient 在打包前预生成并显式打入，避免只读冻结环境无法动态生成绑定。
HIDDEN = [
    "bridge.server",
    "comtypes.gen.UIAutomationClient",
]

EXCLUDES = [
    "pytest",
    "tkinter",
    "PySide6",
    "PyQt6",
    "PyQt5",
    "matplotlib",
    "scipy",
]


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 pyinstaller，请先运行: pip install pyinstaller")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 预生成 UIAutomationCore COM 类型库绑定，确保随 onefile 包一起冻入
    try:
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
    except Exception as exc:
        print(f"提示: 预生成 UIA 类型库绑定跳过 ({exc})")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",             # bridge 作为后台静默服务运行，不弹出控制台窗口
        "--name", "python-bridge",
        "--distpath", str(OUT_DIR),
        "--workpath", str(ROOT / "build" / "bridge"),
        "--specpath", str(ROOT / "build" / "bridge"),
        # frozen StorageManager 和邮件报告会从 bundle 数据目录读取这些文件。
        "--add-data", f"{ROOT / 'database' / 'schema.sql'};database",
        "--add-data", f"{ROOT / 'templates'};templates",
        # 项目根下的模块：core / database / bridge / config
        "--paths", str(ROOT),
        # 这些包被动态导入，PyInstaller 静态分析发现不了
        "--collect-all", "uvicorn",
        "--collect-all", "fastapi",
        "--collect-all", "starlette",
        "--collect-all", "pydantic",
        "--collect-all", "anyio",
        "--collect-all", "comtypes",
        "--collect-submodules", "core",
        "--collect-submodules", "database",
    ]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    # 入口是一个真正的 CLI，而不是让 Tauri 去跑 `python -m uvicorn`。
    # PyInstaller 的 onefile 会把入口脚本冻进 exe，之后再传
    # `-m uvicorn ...` 是不生效的 —— 参数会被忽略掉。
    cmd.append(str(ROOT / "bridge" / "entry.py"))

    print("打包 bridge ...")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print("打包失败")
        return r.returncode

    exe = OUT_DIR / "python-bridge.exe"
    # Tauri 的 externalBin 要求文件名带目标三元组后缀
    # （x86_64-pc-windows-msvc），缺了会在 build 阶段直接报错。
    machine = platform.machine().lower()
    arch = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine, machine)
    suffixed = OUT_DIR / f"python-bridge-{arch}-pc-windows-msvc.exe"

    if exe.exists():
        size_mb = exe.stat().st_size / 1024 / 1024
        if suffixed.exists():
            suffixed.unlink()
        exe.replace(suffixed)
        print(f"完成: {suffixed}  ({size_mb:.1f} MB)")
    else:
        print("没有找到产物，检查 PyInstaller 输出")
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
