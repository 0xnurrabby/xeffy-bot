@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Running setup first...
  call setup.bat
)
if not exist .venv\Scripts\python.exe (
  echo.
  echo Setup failed. Install Python, then run setup.bat again.
  pause
  exit /b 1
)
.venv\Scripts\python.exe xeffy_bot.py
pause
