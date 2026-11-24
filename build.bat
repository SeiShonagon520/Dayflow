@echo off
setlocal
cd /d "%~dp0"
python bridge\build_bridge.py
if errorlevel 1 exit /b 1
call npm run tauri:build
exit /b %errorlevel%
