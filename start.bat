@echo OFF
setlocal enabledelayedexpansion

if not exist .venv (
    echo [.VENV] Creating virtual environment...
    uv -p 3.12 venv
)

echo [.VENV] Syncing dependencies...
uv pip install -r requirements.txt

echo [RUN] Starting MC-JAR-Reader...
uv run main.py
pause
