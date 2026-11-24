@echo off
setlocal
cd /d "%~dp0"
if not exist src-tauri\resources\python-bridge-x86_64-pc-windows-msvc.exe (
    python bridge\build_bridge.py
    if errorlevel 1 exit /b 1
)
call npm run tauri:dev
exit /b %errorlevel%
