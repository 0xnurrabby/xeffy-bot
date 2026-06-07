@echo off
setlocal
cd /d "%~dp0"

if not exist sessions mkdir sessions
if not exist exports mkdir exports
if not exist .web_runs mkdir .web_runs

if not exist .env copy /Y .env.example .env >nul

py -3.11 -m venv .venv
if errorlevel 1 (
  python -m venv .venv
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Setup complete.
echo .env was created from .env.example only if it was missing.
echo Put your .session files inside the sessions folder, or paste query data in data.txt.
pause
