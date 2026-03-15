# SovereignForge - Task Scheduler Setup for Paper Trading Auto-Start
# Run this script as Administrator:
#   Right-click PowerShell -> Run as Administrator
#   cd E:\Users\Gino\Downloads\SovereignForge
#   .\setup_autostart.ps1

$TaskName = "SovereignForge-PaperTrading"
$BatchFile = "E:\Users\Gino\Downloads\SovereignForge\sovereignforge_autostart.bat"
$WorkingDir = "E:\Users\Gino\Downloads\SovereignForge"

# Remove existing task if it exists
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task '$TaskName'..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the action
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatchFile`"" `
    -WorkingDirectory $WorkingDir

# Create the trigger: at startup with 30-second delay
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Trigger.Delay = "PT30S"

# Settings: allow running on battery, don't stop on battery, no time limit
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Register the task to run as the current user
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType S4U `
    -RunLevel Highest

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Auto-start SovereignForge paper trading on system boot" `
        -Force

    Write-Host ""
    Write-Host "Task '$TaskName' registered successfully." -ForegroundColor Green
    Write-Host ""
    Write-Host "Details:" -ForegroundColor Cyan
    Write-Host "  Trigger:    At system startup (30s delay)"
    Write-Host "  Action:     $BatchFile"
    Write-Host "  Log:        $WorkingDir\logs\autostart.log"
    Write-Host "  Run as:     $env:USERNAME (no login required)"
    Write-Host ""
    Write-Host "To test now:  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    Write-Host "To remove:    Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
}
catch {
    Write-Host "Failed to register task. Make sure you are running as Administrator." -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Try: Right-click PowerShell -> Run as Administrator, then re-run this script." -ForegroundColor Yellow
    exit 1
}
