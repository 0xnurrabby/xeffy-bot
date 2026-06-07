@echo off
setlocal
cd /d "%~dp0"

if not exist sessions mkdir sessions
if not exist exports mkdir exports
if not exist .web_runs mkdir .web_runs

if not exist .env copy /Y .env.example .env >nul

if exist .venv\Scripts\python.exe (
  echo Virtual environment already exists.
  goto install_deps
)

echo Creating virtual environment...

py -3.11 --version >nul 2>&1
if not errorlevel 1 (
  py -3.11 -m venv .venv
)

if not exist .venv\Scripts\python.exe (
  py -3 --version >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv .venv
  )
)

if not exist .venv\Scripts\python.exe (
  python --version >nul 2>&1
  if not errorlevel 1 (
    python -m venv .venv
  )
)

if not exist .venv\Scripts\python.exe (
  python3 --version >nul 2>&1
  if not errorlevel 1 (
    python3 -m venv .venv
  )
)

if not exist .venv\Scripts\python.exe (
  echo.
  echo [ERROR] Could not create .venv.
  echo Install Python 3.11 or newer from https://www.python.org/downloads/
  echo During install, tick "Add python.exe to PATH", then run setup.bat again.
  echo.
  pause
  exit /b 1
)

:install_deps
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
  echo.
  echo [ERROR] pip upgrade failed.
  pause
  exit /b 1
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [ERROR] dependency install failed.
  pause
  exit /b 1
)

echo.
echo Setup complete.
echo .env was created from .env.example only if it was missing.
echo Put your .session files inside the sessions folder, or paste query data in data.txt.
pause
