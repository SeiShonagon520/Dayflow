@echo off
REM ============================================================
REM  Dayflow 开发环境启动
REM
REM  会依次拉起两个进程：
REM    1. Python bridge  —— 录屏 / AI 分析 / 数据（8899）
REM    2. Tauri 窗口     —— React 界面
REM
REM  改了 Python 代码要重启本脚本才会生效（没有热重载）。
REM ============================================================

setlocal
cd /d "%~dp0"

where conda >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 conda，请先安装 Anaconda 并加入 PATH
    pause
    exit /b 1
)

REM 先确认 bridge 依赖装好了
echo [1/3] 检查依赖...
call conda run -n dayflow python -c "import fastapi, uvicorn" 2>nul
if errorlevel 1 (
    echo       安装缺失的依赖...
    call conda run -n dayflow python -m pip install -r bridge\requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
)
call conda run -n dayflow python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo [错误] dayflow 环境里没有 PySide6
    echo        录制需要它，请先装好再运行
    pause
    exit /b 1
)

echo [2/3] 启动后台服务...
start "Dayflow Bridge" cmd /c "conda run -n dayflow python bridge\entry.py"

REM 等 bridge 起来，否则界面会先报「无法连接后台服务」
echo       等待后台就绪...
set /a tries=0
:wait_loop
set /a tries+=1
timeout /t 1 /nobreak >nul
call conda run -n dayflow python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8899/api/health',timeout=1)" 2>nul
if errorlevel 1 (
    if !tries!lss 20 (
        goto wait_loop
    )
    echo [错误] 后台服务 20 秒内没起来，请检查 %LOCALAPPDATA%\Dayflow\dayflow.log
    pause
    exit /b 1
)

echo [3/3] 启动界面...
call npm run tauri:dev

REM Tauri 退出后收掉 bridge
taskkill /F /IM python-bridge.exe >nul 2>&1
echo.
echo 已退出。
pause
