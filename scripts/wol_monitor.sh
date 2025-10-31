#!/bin/bash
# Claude Draws - Wake-on-LAN Monitor
# Checks for pending submissions and sends WoL packet to wake the PC

# Configuration (can be overridden with environment variables or command-line arguments)
MAC_ADDRESS="${WOL_MAC_ADDRESS:-}"
CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
D1_DATABASE_ID="${D1_DATABASE_ID:-}"
CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
POLL_INTERVAL="${WOL_POLL_INTERVAL:-30}"
LOG_FILE="${WOL_LOG_FILE:-/tmp/claude-draws-wol-monitor.log}"

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mac-address)
            MAC_ADDRESS="$2"
            shift 2
            ;;
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
        --poll-interval)
            POLL_INTERVAL="$2"
            shift 2
            ;;
        --log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--mac-address MAC] [--account-id ID] [--database-id ID] [--api-token TOKEN] [--poll-interval SECONDS] [--log-file PATH]"
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
if [[ -z "$MAC_ADDRESS" ]]; then
    log "ERROR: MAC_ADDRESS not set. Use --mac-address or set WOL_MAC_ADDRESS environment variable"
    exit 1
fi

if [[ -z "$CLOUDFLARE_ACCOUNT_ID" ]] || [[ -z "$D1_DATABASE_ID" ]] || [[ -z "$CLOUDFLARE_API_TOKEN" ]]; then
    log "ERROR: Missing Cloudflare configuration. Set CLOUDFLARE_ACCOUNT_ID, D1_DATABASE_ID, and CLOUDFLARE_API_TOKEN"
    exit 1
fi

# Check for wakeonlan command
if ! command -v wakeonlan &> /dev/null; then
    log "ERROR: 'wakeonlan' command not found. Install it first:"
    log "  Debian/Ubuntu: sudo apt-get install wakeonlan"
    log "  Arch Linux: sudo pacman -S wakeonlan"
    log "  macOS: brew install wakeonlan"
    exit 1
fi

log "=========================================="
log "Claude Draws - WoL Monitor Started"
log "=========================================="
log "Poll Interval: $POLL_INTERVAL seconds"

# Main monitoring loop
last_wake_time=0
cooldown_period=300  # 5 minutes cooldown between wake attempts

while true; do
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
        sleep "$POLL_INTERVAL"
        continue
    fi

    # Extract pending count
    pending_count=$(echo "$response" | jq -r '.result[0].results[0].count // 0')

    if [[ "$pending_count" -gt 0 ]]; then
        current_time=$(date +%s)
        time_since_wake=$((current_time - last_wake_time))

        if [[ $time_since_wake -ge $cooldown_period ]]; then
            log "Found $pending_count pending submission(s) - sending WoL packet"

            # Send Wake-on-LAN packet
            if wakeonlan "$MAC_ADDRESS" >> "$LOG_FILE" 2>&1; then
                log "WoL packet sent successfully"
                last_wake_time=$current_time
            else
                log "ERROR: Failed to send WoL packet"
            fi
        else
            remaining=$((cooldown_period - time_since_wake))
            log "Found $pending_count pending submission(s) but in cooldown period ($remaining seconds remaining)"
        fi
    else
        log "No pending submissions found"
    fi

    # Wait before next check
    sleep "$POLL_INTERVAL"
done
