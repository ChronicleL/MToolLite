@echo off
chcp 65001 >nul
cd /d "%~dp0"

where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw -m rpgm_tool gui
) else (
    python -m rpgm_tool gui
    if errorlevel 1 pause
)
