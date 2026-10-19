@echo off
cd /d "%~dp0"
title Teams Audio Recorder

python recorder_gui.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [Program exited with error: %ERRORLEVEL%]
    pause
)