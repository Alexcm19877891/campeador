@echo off
cd /d "%~dp0"

echo [Campeador] Creating virtual environment...
py -3.11 -m venv .venv

if errorlevel 1 (
    echo.
    echo [Campeador] Failed to create virtual environment.
    echo Make sure Python 3.11 is installed.
    pause
    exit /b 1
)

echo.
echo [Campeador] Activating virtual environment...
call ".venv\Scripts\activate.bat"

echo.
echo [Campeador] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [Campeador] Installing requirements...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [Campeador] Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo [Campeador] Installation complete.
echo You can now run run_campeador.bat
echo.
pause
exit /b 0