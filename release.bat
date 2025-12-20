@echo off
chcp 65001 >nul
echo ========================================
echo   Dayflow 一键发布工具
echo ========================================
echo.

REM 检查 GITHUB_TOKEN
if "%GITHUB_TOKEN%"=="" (
    echo [警告] 未设置 GITHUB_TOKEN 环境变量
    echo.
    echo 请先设置 Token:
    echo   set GITHUB_TOKEN=ghp_xxxxxxxxxxxx
    echo.
    echo 获取 Token: https://github.com/settings/tokens
    echo 需要勾选 "repo" 权限
    echo.
    pause
    exit /b 1
)

REM 检查是否有发布说明文件
if exist release_notes.md (
    echo [提示] 检测到 release_notes.md，将使用该文件作为发布说明
    echo.
    conda run -n dayflow --no-capture-output python release.py --notes-file release_notes.md %*
) else (
    echo [提示] 未检测到 release_notes.md，将使用默认发布说明
    echo.
    conda run -n dayflow --no-capture-output python release.py %*
)

pause
