@echo off
setlocal
cd /d "%~dp0"

if not exist sessions mkdir sessions
if not exist exports mkdir exports

if not exist .env copy /Y examples\.env.example .env >nul
if not exist sessions.txt copy /Y examples\sessions.example.txt sessions.txt >nul
if not exist data.txt copy /Y examples\data.example.txt data.txt >nul
if not exist channel.txt copy /Y examples\channel.example.txt channel.txt >nul
if not exist answers.txt copy /Y examples\answers.example.txt answers.txt >nul
if not exist proxy.txt copy /Y examples\proxy.example.txt proxy.txt >nul
if not exist useragents.txt copy /Y examples\useragents.example.txt useragents.txt >nul

py -3.11 -m venv .venv
if errorlevel 1 (
  python -m venv .venv
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Setup complete.
echo Runtime files were created only if missing:
echo   .env, sessions.txt, data.txt, channel.txt, answers.txt, proxy.txt, useragents.txt
echo Put your .session files inside the sessions folder.
pause
