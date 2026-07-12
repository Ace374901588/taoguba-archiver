@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv\Scripts\python.exe
    echo Create the development environment before starting the browser workspace.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m taoguba_archiver.web
