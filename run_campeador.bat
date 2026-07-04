@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Virtual environment not found.
    echo Run install first:
    echo py -3.11 -m venv .venv
    echo .venv\Scripts\activate
    echo python -m pip install -r requirements.txt
    pause
    exit /b
)

start "" ".venv\Scripts\pythonw.exe" "campeador.py"