# Claude Draws - Sleep Monitor
# Monitors artwork activity and triggers Windows sleep after inactivity threshold

param(
    [string]$GalleryUrl = "https://claudedraws.xyz",
    [int]$PollIntervalSeconds = 60
)

# Setup logging
$LogFile = Join-Path $PSScriptRoot "sleep_monitor.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "$timestamp - $Message"
    Write-Host $logMessage
    Add-Content -Path $LogFile -Value $logMessage
}

function Test-ShouldSleep {
    param([string]$GalleryUrl)

    Write-Log "Checking system status from $GalleryUrl/api/system-status..."

    try {
        $response = Invoke-RestMethod -Uri "$GalleryUrl/api/system-status" -Method Get

        # Check for error in response
        if ($response.error) {
            Write-Log "ERROR: API returned error: $($response.error)"
            return $false
        }

        # Extract status information
        $shouldSleep = $response.shouldSleep
        $processingCount = $response.processingCount
        $minutesSinceLastCompleted = $response.minutesSinceLastCompleted

        # Log detailed status
        Write-Log "Processing count: $processingCount"
        if ($null -ne $minutesSinceLastCompleted) {
            Write-Log "Minutes since last completed: $minutesSinceLastCompleted"
        } else {
            Write-Log "No completed artworks found"
        }

        if ($shouldSleep) {
            Write-Log "System status indicates sleep is appropriate"
            return $true
        } else {
            Write-Log "System status indicates PC should remain active"
            return $false
        }
    } catch {
        Write-Log "ERROR: Failed to fetch system status: $_"
        return $false
    }
}

function Invoke-Sleep {
    Write-Log "=========================================="
    Write-Log "TRIGGERING SLEEP"
    Write-Log "=========================================="

    # Sleep command: SetSuspendState(0, 1, 0)
    # 0 = Sleep (not hibernate)
    # 1 = Force (don't wait for apps to close)
    # 0 = Don't disable wake events
    Add-Type -TypeDefinition @"
        using System;
        using System.Runtime.InteropServices;
        public class Power {
            [DllImport("powrprof.dll", SetLastError = true)]
            public static extern bool SetSuspendState(bool hibernate, bool forceCritical, bool disableWakeEvent);
        }
"@

    [Power]::SetSuspendState($false, $true, $false)
}

# Main loop
Write-Log "=========================================="
Write-Log "Claude Draws - Sleep Monitor Started"
Write-Log "=========================================="
Write-Log "Gallery URL: $GalleryUrl"
Write-Log "Poll interval: $PollIntervalSeconds seconds"
Write-Log "Starting monitoring loop..."

while ($true) {
    try {
        if (Test-ShouldSleep -GalleryUrl $GalleryUrl) {
            Invoke-Sleep
            # If we reach here, sleep failed or was cancelled
            Write-Log "Sleep was triggered but PC is still awake - continuing monitoring"
        }
    } catch {
        Write-Log "ERROR in monitoring loop: $_"
    }

    # Wait before next check
    Start-Sleep -Seconds $PollIntervalSeconds
}
