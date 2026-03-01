@echo off
setlocal enabledelayedexpansion

if not exist .venv (
    echo [.VENV] Creating virtual environment...
    uv venv -p 3.12
)

echo [.VENV] Syncing dependencies...
uv pip install -r requirements.txt

echo [BUILD] Building MC-JAR-Reader with Nuitka...
uv run python -m nuitka ^
    --standalone ^
    --enable-plugin=pyqt6 ^
    --include-qt-plugins=multimedia ^
    --include-data-dir=assets=assets ^
    --windows-icon-from-ico=assets/ui_icon.ico ^
    --assume-yes-for-downloads ^
    --show-progress ^
    --windows-console-mode=disable ^
    --output-dir=dist ^
    main.py
echo Build complete. Check the 'dist' folder.
pause
