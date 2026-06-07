@echo off
py -3.11 -m venv .venv
if errorlevel 1 (
  python -m venv .venv
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Setup complete.
pause
