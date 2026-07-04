@echo off
cd /d "%~dp0"

echo ========================================
echo Campeador Installer
echo ========================================
echo.

if not exist "requirements.txt" (
    echo [Campeador] requirements.txt not found.
    echo Make sure Install_first.bat is in the same folder as requirements.txt
    echo.
    pause
    exit /b 1
)

echo [Campeador] Checking Python 3.11...
py -3.11 --version >nul 2>&1

if errorlevel 1 (
    echo.
    echo [Campeador] Python 3.11 was not found.
    echo [Campeador] Trying to install Python 3.11 automatically using winget...
    echo.

    winget --version >nul 2>&1

    if errorlevel 1 (
        echo [Campeador] winget was not found on this system.
        echo.
        echo Please install Python 3.11 manually from:
        echo https://www.python.org/downloads/windows/
        echo.
        echo During installation, tick:
        echo - Add python.exe to PATH
        echo - Install py launcher
        echo.
        pause
        exit /b 1
    )

    winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements

    if errorlevel 1 (
        echo.
        echo [Campeador] Python installation failed.
        echo Please install Python 3.11 manually from:
        echo https://www.python.org/downloads/windows/
        echo.
        pause
        exit /b 1
    )

    echo.
    echo [Campeador] Python installation finished.
    echo [Campeador] Checking Python again...
    echo.

    py -3.11 --version >nul 2>&1

    if errorlevel 1 (
        echo [Campeador] Python was installed, but this terminal cannot detect it yet.
        echo.
        echo Close this window and run Install_first.bat again.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo [Campeador] Python 3.11 found.
py -3.11 --version

echo.
echo [Campeador] Creating virtual environment...
py -3.11 -m venv .venv

if errorlevel 1 (
    echo.
    echo [Campeador] Failed to create virtual environment.
    pause
    exit /b 1
)

echo.
echo [Campeador] Activating virtual environment...
call ".venv\Scripts\activate.bat"

echo.
echo [Campeador] Upgrading pip...
python -m pip install --upgrade pip

if errorlevel 1 (
    echo.
    echo [Campeador] Failed to upgrade pip.
    pause
    exit /b 1
)

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
echo ========================================
echo Campeador installation complete.
echo ========================================
echo.
echo You can now run:
echo run_campeador.bat
echo.
pause
exit /b 0