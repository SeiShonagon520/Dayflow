"""
Dayflow 打包脚本
使用 PyInstaller 将应用打包为独立 EXE
"""

import subprocess
import sys


def _safe_print(text: str = ""):
    """在 Windows 控制台编码不一致时尽量避免输出报错。"""
    try:
        print(text)
    except UnicodeEncodeError:
        fallback = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        print(fallback.encode("ascii", errors="replace").decode("ascii"))


def build():
    """打包应用"""
    
    # PyInstaller 参数
    args = [
        sys.executable, "-m", "PyInstaller",
        "--name=Dayflow",
        "--onedir",                    # 生成目录
        "--windowed",                  # 无控制台窗口
        "--clean",                     # 清理缓存
        "--icon=assets/icon.ico",      # 应用图标
        "--add-data=database/schema.sql;database",  # 包含数据库架构
        "--add-data=templates;templates",           # 包含 HTML 模板
        
        # PySide6 6.8.1 通常只需要这些
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=PySide6.QtSvgWidgets", 
        
        "--collect-all=dxcam",         # 收集 dxcam 所有文件
        "--noconfirm",                 # 覆盖已有输出
        "main.py"
    ]
    
    _safe_print("=" * 50)
    _safe_print("  Dayflow 打包工具")
    _safe_print("=" * 50)
    _safe_print()
    _safe_print("正在打包，请稍候...")
    _safe_print()
    
    try:
        subprocess.run(args, check=True)
        _safe_print()
        _safe_print("=" * 50)
        _safe_print("  打包成功！")
        _safe_print("  输出目录: dist/Dayflow/")
        _safe_print("  运行: dist/Dayflow/Dayflow.exe")
        _safe_print("=" * 50)
    except subprocess.CalledProcessError as e:
        _safe_print(f"打包失败: {e}")
        sys.exit(1)
    except FileNotFoundError:
        _safe_print("请先安装 PyInstaller:")
        _safe_print("   pip install pyinstaller")
        sys.exit(1)

if __name__ == "__main__":
    build()
