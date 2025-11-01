#!/bin/bash
# Claude Draws - Wake-on-LAN Monitor
# Checks D1 for pending submissions and returns exit code for Home Assistant
# Designed to be run on a schedule (e.g., Home Assistant automation)
#
# Exit codes:
#   0 = Pending submissions found (wake PC)
#   1 = No pending submissions (no action needed)
#   2 = Query error

# Configuration (can be overridden with environment variables or command-line arguments)
CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
D1_DATABASE_ID="${D1_DATABASE_ID:-}"
CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
LOG_FILE="${WOL_LOG_FILE:-/tmp/claude-draws-wol-monitor.log}"

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --account-id)
            CLOUDFLARE_ACCOUNT_ID="$2"
            shift 2
            ;;
        --database-id)
            D1_DATABASE_ID="$2"
            shift 2
            ;;
        --api-token)
            CLOUDFLARE_API_TOKEN="$2"
            shift 2
            ;;
        --log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--account-id ID] [--database-id ID] [--api-token TOKEN] [--log-file PATH]"
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
if [[ -z "$CLOUDFLARE_ACCOUNT_ID" ]] || [[ -z "$D1_DATABASE_ID" ]] || [[ -z "$CLOUDFLARE_API_TOKEN" ]]; then
    log "ERROR: Missing Cloudflare configuration. Set CLOUDFLARE_ACCOUNT_ID, D1_DATABASE_ID, and CLOUDFLARE_API_TOKEN"
    exit 2
fi

# Query D1 for pending submissions
response=$(curl -s -X POST \
    "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/d1/database/$D1_DATABASE_ID/query" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"sql":"SELECT COUNT(*) as count FROM submissions WHERE status = '\''pending'\''"}')

# Check if request was successful
if ! echo "$response" | jq -e '.success' &> /dev/null; then
    log "ERROR: Failed to query D1 database"
    log "Response: $response"
    exit 2  # Exit code 2 for query error
fi

# Extract pending count
pending_count=$(echo "$response" | jq -r '.result[0].results[0].count // 0')

if [[ "$pending_count" -gt 0 ]]; then
    log "Found $pending_count pending submission(s) - wake needed"
    exit 0  # Exit code 0 = submissions found, wake PC
else
    log "No pending submissions found"
    exit 1  # Exit code 1 = no submissions, no action needed
fi
