@echo off
REM SovereignForge Paper Trading Auto-Start Script
REM Runs on system boot via Task Scheduler

cd /d "E:\Users\Gino\Downloads\SovereignForge"

REM Create logs directory if it doesn't exist
if not exist "logs" mkdir logs

REM Timestamp the log
echo ============================================== >> logs\autostart.log
echo [%date% %time%] SovereignForge autostart begin >> logs\autostart.log
echo ============================================== >> logs\autostart.log

REM Activate GPU venv if it exists
if exist "gpu_venv\Scripts\activate.bat" (
    echo [%date% %time%] Activating gpu_venv... >> logs\autostart.log
    call gpu_venv\Scripts\activate.bat
) else (
    echo [%date% %time%] gpu_venv not found, using system Python >> logs\autostart.log
)

REM Start paper trading
echo [%date% %time%] Starting paper trading... >> logs\autostart.log
python launcher.py start --paper >> logs\autostart.log 2>&1

echo [%date% %time%] Process exited with code %ERRORLEVEL% >> logs\autostart.log
