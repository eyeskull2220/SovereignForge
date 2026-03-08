@echo off
echo ========================================
echo SovereignForge Personal Deployment Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

echo [+] Python found, checking version...
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [+] Python version: %PYTHON_VERSION%

REM Create virtual environment
echo [+] Creating virtual environment...
python -m venv personal_env
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

REM Activate virtual environment
echo [+] Activating virtual environment...
call personal_env\Scripts\activate.bat

REM Upgrade pip
echo [+] Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo [+] Installing dependencies...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install flask fastapi uvicorn pandas numpy psutil python-telegram-bot aiofiles

REM Create directory structure
echo [+] Creating directory structure...
mkdir personal_data\models 2>nul
mkdir personal_data\logs 2>nul
mkdir personal_data\backups 2>nul

REM Copy configuration files
echo [+] Setting up configuration...
copy personal_config.json personal_data\ 2>nul

REM Copy model files (if they exist)
echo [+] Checking for model files...
if exist "models\final_BTC_USDT.pth" (
    echo [+] Copying BTC model...
    copy "models\final_BTC_USDT.pth" "personal_data\models\" 2>nul
)
if exist "models\final_ETH_USDT.pth" (
    echo [+] Copying ETH model...
    copy "models\final_ETH_USDT.pth" "personal_data\models\" 2>nul
)

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo To start SovereignForge Personal:
echo   1. Run: call personal_env\Scripts\activate.bat
echo   2. Run: python personal_app.py
echo.
echo Or use the start script: start_personal.bat
echo.
echo Web interface will be available at: http://localhost:5000
echo.
pause