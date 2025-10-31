# Claude Draws - Sleep Monitor
# Monitors artwork activity and triggers Windows sleep after inactivity threshold

param(
    [string]$EnvFile = "..\\backend\\.env",
    [int]$InactivityMinutes = 15,
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

function Load-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        Write-Log "ERROR: Environment file not found: $Path"
        exit 1
    }

    Write-Log "Loading environment from: $Path"
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Invoke-D1Query {
    param([string]$Query)

    $accountId = [Environment]::GetEnvironmentVariable("CLOUDFLARE_ACCOUNT_ID")
    $databaseId = [Environment]::GetEnvironmentVariable("D1_DATABASE_ID")
    $apiToken = [Environment]::GetEnvironmentVariable("CLOUDFLARE_API_TOKEN")

    if (-not $accountId -or -not $databaseId -or -not $apiToken) {
        Write-Log "ERROR: Missing required environment variables (CLOUDFLARE_ACCOUNT_ID, D1_DATABASE_ID, CLOUDFLARE_API_TOKEN)"
        return $null
    }

    $uri = "https://api.cloudflare.com/client/v4/accounts/$accountId/d1/database/$databaseId/query"
    $headers = @{
        "Authorization" = "Bearer $apiToken"
        "Content-Type" = "application/json"
    }
    $body = @{
        "sql" = $Query
    } | ConvertTo-Json

    try {
        $response = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body
        if ($response.success) {
            return $response.result[0]
        } else {
            Write-Log "ERROR: D1 query failed: $($response.errors | ConvertTo-Json -Compress)"
            return $null
        }
    } catch {
        Write-Log "ERROR: Failed to query D1: $_"
        return $null
    }
}

function Test-ShouldSleep {
    param([int]$InactivityMinutes)

    # Check 1: Are there any submissions currently being processed?
    Write-Log "Checking for in-progress submissions..."
    $processingQuery = "SELECT COUNT(*) as count FROM submissions WHERE status = 'processing'"
    $processingResult = Invoke-D1Query -Query $processingQuery

    if ($null -eq $processingResult) {
        Write-Log "ERROR: Could not check processing status"
        return $false
    }

    $processingCount = $processingResult.results[0].count
    if ($processingCount -gt 0) {
        Write-Log "Found $processingCount submission(s) in progress - not sleeping"
        return $false
    }

    Write-Log "No submissions in progress"

    # Check 2: When was the last artwork completed?
    Write-Log "Checking time since last completed artwork..."
    $completedQuery = "SELECT MAX(completed_at) as last_completed FROM submissions WHERE status = 'completed'"
    $completedResult = Invoke-D1Query -Query $completedQuery

    if ($null -eq $completedResult) {
        Write-Log "ERROR: Could not check completion status"
        return $false
    }

    $lastCompleted = $completedResult.results[0].last_completed
    if ($null -eq $lastCompleted) {
        Write-Log "No completed artworks found - not sleeping"
        return $false
    }

    # Parse ISO 8601 timestamp and calculate minutes since completion
    try {
        $lastCompletedTime = [DateTime]::Parse($lastCompleted)
        $minutesSinceCompletion = [Math]::Round(((Get-Date) - $lastCompletedTime).TotalMinutes, 1)

        Write-Log "Last artwork completed $minutesSinceCompletion minutes ago (threshold: $InactivityMinutes minutes)"

        if ($minutesSinceCompletion -ge $InactivityMinutes) {
            Write-Log "Inactivity threshold exceeded - ready to sleep"
            return $true
        } else {
            Write-Log "Below inactivity threshold - not sleeping yet"
            return $false
        }
    } catch {
        Write-Log "ERROR: Could not parse completion timestamp: $_"
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
Write-Log "Inactivity threshold: $InactivityMinutes minutes"
Write-Log "Poll interval: $PollIntervalSeconds seconds"

# Load environment variables
Load-EnvFile -Path $EnvFile

Write-Log "Starting monitoring loop..."

while ($true) {
    try {
        if (Test-ShouldSleep -InactivityMinutes $InactivityMinutes) {
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
