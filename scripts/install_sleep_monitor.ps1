# Claude Draws - Sleep Monitor Installation Script
# Creates a Windows Scheduled Task to run the sleep monitor at system boot

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator', then run this script again" -ForegroundColor Yellow
    exit 1
}

# Configuration
$TaskName = "ClaudeDraws-SleepMonitor"
$ScriptPath = Join-Path $PSScriptRoot "sleep_monitor.ps1"
$InactivityMinutes = 15
$PollIntervalSeconds = 60

Write-Host "=========================================="
Write-Host "Claude Draws - Sleep Monitor Installation"
Write-Host "=========================================="
Write-Host ""

# Verify script exists
if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: sleep_monitor.ps1 not found at: $ScriptPath" -ForegroundColor Red
    exit 1
}

Write-Host "Script path: $ScriptPath" -ForegroundColor Cyan
Write-Host "Task name: $TaskName" -ForegroundColor Cyan
Write-Host "Inactivity threshold: $InactivityMinutes minutes" -ForegroundColor Cyan
Write-Host "Poll interval: $PollIntervalSeconds seconds" -ForegroundColor Cyan
Write-Host ""

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Scheduled task already exists. Removing old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Old task removed" -ForegroundColor Green
}

# Create the scheduled task
Write-Host "Creating scheduled task..." -ForegroundColor Cyan

# Action: Run PowerShell with the sleep monitor script
$action = New-ScheduledTaskAction `
    -Execute "PowerShell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`" -InactivityMinutes $InactivityMinutes -PollIntervalSeconds $PollIntervalSeconds" `
    -WorkingDirectory $PSScriptRoot

# Trigger: At system startup
$trigger = New-ScheduledTaskTrigger -AtStartup

# Settings: Run whether user is logged on or not, restart on failure
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

# Principal: Run as current user with highest privileges
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType S4U `
    -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Monitors Claude Draws artwork activity and triggers Windows sleep after inactivity threshold" `
        -ErrorAction Stop | Out-Null

    Write-Host "Scheduled task created successfully!" -ForegroundColor Green
    Write-Host ""

    # Start the task immediately
    Write-Host "Starting the sleep monitor now..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $TaskName

    Write-Host "Sleep monitor started!" -ForegroundColor Green
    Write-Host ""
    Write-Host "=========================================="
    Write-Host "Installation Complete"
    Write-Host "=========================================="
    Write-Host ""
    Write-Host "The sleep monitor will now run automatically at system startup." -ForegroundColor Green
    Write-Host ""
    Write-Host "To check status:" -ForegroundColor Yellow
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To view logs:" -ForegroundColor Yellow
    Write-Host "  Get-Content `"$(Join-Path $PSScriptRoot 'sleep_monitor.log')`" -Tail 20" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To stop the monitor:" -ForegroundColor Yellow
    Write-Host "  Stop-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To uninstall:" -ForegroundColor Yellow
    Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Gray
    Write-Host ""

} catch {
    Write-Host "ERROR: Failed to create scheduled task: $_" -ForegroundColor Red
    exit 1
}
