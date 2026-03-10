@echo off
REM SovereignForge Personal CLI Wrapper (Windows)
REM Simple commands for personal use

set "SCRIPT_DIR=%~dp0"
set "DOCKER_COMPOSE_FILE=%SCRIPT_DIR%docker-compose.yml"
set "DASHBOARD_URL=http://localhost:5173"
set "API_URL=http://localhost:8000"

if "%1"=="start" goto :start
if "%1"=="stop" goto :stop
if "%1"=="restart" goto :restart
if "%1"=="status" goto :status
if "%1"=="health" goto :health
if "%1"=="logs" goto :logs
if "%1"=="backup" goto :backup
if "%1"=="dashboard" goto :dashboard
if "%1"=="update" goto :update
if "%1"=="help" goto :help
if "%1"=="" goto :help

echo [ERROR] Unknown command: %1
echo Run 'sovereignforge help' for usage information
goto :eof

:start
echo [INFO] Starting SovereignForge...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Please start Docker first.
    exit /b 1
)
if not exist "%DOCKER_COMPOSE_FILE%" (
    echo [ERROR] docker-compose.yml not found in %SCRIPT_DIR%
    exit /b 1
)
cd /d "%SCRIPT_DIR%"
docker-compose up -d
timeout /t 3 /nobreak >nul
echo [SUCCESS] SovereignForge started!
echo Dashboard: %DASHBOARD_URL%
echo API: %API_URL%
echo Run 'sovereignforge status' to check services
goto :eof

:stop
echo [INFO] Stopping SovereignForge...
if not exist "%DOCKER_COMPOSE_FILE%" (
    echo [ERROR] docker-compose.yml not found in %SCRIPT_DIR%
    exit /b 1
)
cd /d "%SCRIPT_DIR%"
docker-compose down
echo [SUCCESS] SovereignForge stopped!
goto :eof

:restart
echo [INFO] Restarting SovereignForge...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Please start Docker first.
    exit /b 1
)
if not exist "%DOCKER_COMPOSE_FILE%" (
    echo [ERROR] docker-compose.yml not found in %SCRIPT_DIR%
    exit /b 1
)
cd /d "%SCRIPT_DIR%"
docker-compose restart
echo [SUCCESS] SovereignForge restarted!
goto :eof

:status
echo === SovereignForge Status ===
echo.
echo Docker Services:
docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>nul
if errorlevel 1 echo No services running
echo.
echo System Resources:
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>nul
if errorlevel 1 echo Unable to get container stats
echo.
echo API Health:
curl -s --max-time 5 "%API_URL%/health" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] API responding
) else (
    echo [FAIL] API not responding
)
echo.
echo Dashboard:
curl -s --max-time 5 "%DASHBOARD_URL%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Dashboard available at %DASHBOARD_URL%
) else (
    echo [FAIL] Dashboard not available
)
goto :eof

:health
echo === SovereignForge Health Check ===
echo.
set "issues=0"
docker info >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Docker is not running
    set /a issues+=1
) else (
    echo [OK] Docker is running
)
if not exist "%DOCKER_COMPOSE_FILE%" (
    echo [FAIL] docker-compose.yml not found
    set /a issues+=1
) else (
    echo [OK] docker-compose.yml found
)
curl -s --max-time 5 "%API_URL%/health" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] API health check passed
) else (
    echo [FAIL] API health check failed
    set /a issues+=1
)
echo.
if %issues% equ 0 (
    echo [SUCCESS] All health checks passed!
) else (
    echo [WARNING] %issues% issue(s) found. Run 'sovereignforge logs' for details.
)
goto :eof

:logs
echo [INFO] Showing SovereignForge logs...
if not exist "%DOCKER_COMPOSE_FILE%" (
    echo [ERROR] docker-compose.yml not found in %SCRIPT_DIR%
    exit /b 1
)
cd /d "%SCRIPT_DIR%"
docker-compose logs -f --tail=50
goto :eof

:backup
echo [INFO] Creating backup...
set "BACKUP_DIR=%SCRIPT_DIR%backups"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
set "TIMESTAMP=%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%"
set "BACKUP_FILE=%BACKUP_DIR%\sovereignforge_backup_%TIMESTAMP%.zip"
powershell "Get-ChildItem -Path '%SCRIPT_DIR%data','%SCRIPT_DIR%models','%SCRIPT_DIR%logs','%SCRIPT_DIR%reports' -Recurse -ErrorAction SilentlyContinue | Compress-Archive -DestinationPath '%BACKUP_FILE%' -Force" 2>nul
if exist "%BACKUP_FILE%" (
    echo [SUCCESS] Backup created: %BACKUP_FILE%
) else (
    echo [ERROR] Backup failed
)
goto :eof

:dashboard
echo [INFO] Opening dashboard...
start %DASHBOARD_URL%
goto :eof

:update
echo [INFO] Checking for updates...
cd /d "%SCRIPT_DIR%"
git pull origin main 2>nul
if %errorlevel% equ 0 (
    echo [SUCCESS] Code updated successfully
    echo [WARNING] Run 'sovereignforge restart' to apply changes
) else (
    echo [WARNING] Unable to update automatically. Check git status.
)
goto :eof

:help
echo SovereignForge Personal CLI
echo.
echo Usage: sovereignforge ^<command^>
echo.
echo Commands:
echo   start     Start all services
echo   stop      Stop all services
echo   restart   Restart all services
echo   status    Show system status
echo   health    Run health diagnostics
echo   logs      Show service logs
echo   backup    Create data backup
echo   dashboard Open dashboard in browser
echo   update    Update from git repository
echo   help      Show this help
echo.
echo Examples:
echo   sovereignforge start
echo   sovereignforge status
echo   sovereignforge health
goto :eof
