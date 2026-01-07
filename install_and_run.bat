@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo      Video Frame Extractor - Setup & Run
echo ===================================================

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.8 or higher from python.org and try again.
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b
)

:: 2. Setup Virtual Environment
if not exist ".venv" (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
)

:: 3. Activate and Install
echo [INFO] Activating environment and checking dependencies...
call .venv\Scripts\activate.bat

echo [INFO] Installing/Updating required libraries (this may take a minute)...
pip install -r requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    echo Retrying with visible output...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [FATAL] Installation failed.
        pause
        exit /b
    )
)

:: 4. Launch
echo [INFO] Starting Application...
echo.
echo ===================================================
echo    Open your browser to: http://127.0.0.1:8000
echo    Close this window to stop the program.
echo ===================================================

:: Start browser in background after a short delay
start "" "http://127.0.0.1:8000"

:: Run the server
uvicorn app:app --host 127.0.0.1 --port 8000 --reload --log-level error

pause
