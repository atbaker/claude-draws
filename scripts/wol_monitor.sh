#!/bin/bash
# Claude Draws - Wake-on-LAN Monitor
# Checks gallery endpoint for system status and returns exit code for Home Assistant
# Designed to be run on a schedule (e.g., Home Assistant automation)
#
# Exit codes:
#   0 = Wake needed (pending submissions found)
#   1 = No action needed (no pending submissions)
#   2 = Query error

# Configuration (can be overridden with environment variables or command-line arguments)
GALLERY_URL="${GALLERY_URL:-https://claudedraws.xyz}"
LOG_FILE="${WOL_LOG_FILE:-/tmp/claude-draws-wol-monitor.log}"

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --gallery-url)
            GALLERY_URL="$2"
            shift 2
            ;;
        --log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--gallery-url URL] [--log-file PATH]"
            exit 1
            ;;
    esac
done

# Logging function
log() {
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    echo "$timestamp - $1" | tee -a "$LOG_FILE"
}

# Validate configuration
if [[ -z "$GALLERY_URL" ]]; then
    log "ERROR: Missing GALLERY_URL configuration"
    exit 2
fi

# Query system status endpoint
response=$(curl -s "${GALLERY_URL}/api/system-status")

# Check if we got valid JSON
if ! echo "$response" | jq -e '.' &> /dev/null; then
    log "ERROR: Failed to fetch system status from ${GALLERY_URL}/api/system-status"
    log "Response: $response"
    exit 2  # Exit code 2 for query error
fi

# Check for error in response
if echo "$response" | jq -e '.error' &> /dev/null; then
    error_msg=$(echo "$response" | jq -r '.error')
    log "ERROR: API returned error: $error_msg"
    exit 2
fi

# Extract shouldWake and pending count
should_wake=$(echo "$response" | jq -r '.shouldWake // false')
pending_count=$(echo "$response" | jq -r '.pendingCount // 0')

if [[ "$should_wake" == "true" ]]; then
    log "Wake needed - $pending_count pending submission(s)"
    exit 0  # Exit code 0 = wake PC
else
    log "No action needed - no pending submissions"
    exit 1  # Exit code 1 = no action needed
fi
