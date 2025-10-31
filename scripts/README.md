# Claude Draws - Power Management Scripts

This directory contains scripts for automated power management using Wake-on-LAN (WoL). The system allows the Windows PC to sleep after periods of inactivity and wake automatically when new submissions are detected.

## Architecture Overview

The power management system has two main components:

1. **Sleep Monitor (Windows PC)** - PowerShell script that monitors artwork activity and triggers sleep after inactivity
2. **WoL Monitor (Remote Server)** - Bash script that checks for pending submissions and sends WoL packets

## Component 1: Sleep Monitor (Windows PC)

### Prerequisites

- Windows PC with PowerShell 5.1 or later
- Cloudflare D1 database credentials (account ID, database ID, API token)
- Backend `.env` file configured with Cloudflare credentials

### Installation

1. **Configure environment variables** in `backend/.env`:
   ```
   CLOUDFLARE_ACCOUNT_ID=your_account_id
   D1_DATABASE_ID=your_database_id
   CLOUDFLARE_API_TOKEN=your_api_token
   ```

2. **Run the installation script as Administrator**:
   ```powershell
   # Open PowerShell as Administrator
   cd backend\scripts
   .\install_sleep_monitor.ps1
   ```

   This will:
   - Create a Windows Scheduled Task named "ClaudeDraws-SleepMonitor"
   - Configure it to run at system startup
   - Start the monitor immediately

3. **Verify installation**:
   ```powershell
   # Check task status
   Get-ScheduledTask -TaskName "ClaudeDraws-SleepMonitor"

   # View logs
   Get-Content backend\scripts\sleep_monitor.log -Tail 20
   ```

### Configuration

The sleep monitor supports these parameters (edit in `install_sleep_monitor.ps1`):

- `InactivityMinutes` (default: 15) - Minutes of inactivity before triggering sleep
- `PollIntervalSeconds` (default: 60) - How often to check for activity

### How It Works

The sleep monitor runs continuously and:

1. Every minute, queries D1 database to check:
   - Are there any submissions with status = 'processing'?
   - When was the last artwork completed?
2. If no processing submissions AND last completion > 15 minutes ago:
   - Triggers Windows sleep via `SetSuspendState` API
3. Logs all activity to `sleep_monitor.log`

### Troubleshooting

**Sleep not triggering:**
- Check logs: `Get-Content backend\scripts\sleep_monitor.log -Tail 50`
- Verify D1 credentials are correct in `backend\.env`
- Check Windows power settings allow sleep

**Task not running:**
- Verify task exists: `Get-ScheduledTask -TaskName "ClaudeDraws-SleepMonitor"`
- Check task history in Task Scheduler GUI
- Manually start: `Start-ScheduledTask -TaskName "ClaudeDraws-SleepMonitor"`

### Uninstalling

```powershell
# Stop and remove the scheduled task
Stop-ScheduledTask -TaskName "ClaudeDraws-SleepMonitor"
Unregister-ScheduledTask -TaskName "ClaudeDraws-SleepMonitor" -Confirm:$false

# Remove log file (optional)
Remove-Item backend\scripts\sleep_monitor.log
```

## Component 2: WoL Monitor (Remote Server)

### Prerequisites

- Linux server on the same network as Windows PC (e.g., Home Assistant, Raspberry Pi)
- `wakeonlan` package installed
- `jq` package installed (for JSON parsing)
- `curl` installed
- Cloudflare D1 database credentials
- PC's MAC address and Wake-on-LAN enabled in BIOS

### Enable Wake-on-LAN on Windows PC

1. **In BIOS/UEFI** (varies by manufacturer):
   - Enable "Wake on LAN" or "PXE Boot"
   - Enable "Power On by PCI-E/PCI"

2. **In Windows**:
   ```powershell
   # Find your network adapter name
   Get-NetAdapter

   # Enable WoL for your adapter (replace "Ethernet" with your adapter name)
   Set-NetAdapterPowerManagement -Name "Ethernet" -WakeOnMagicPacket Enabled
   ```

3. **In Device Manager**:
   - Open Device Manager → Network Adapters
   - Right-click your adapter → Properties → Power Management
   - Check "Allow this device to wake the computer"
   - Check "Only allow a magic packet to wake the computer"

### Installation on Remote Server

1. **Install dependencies**:
   ```bash
   # Debian/Ubuntu
   sudo apt-get install wakeonlan jq curl

   # Arch Linux
   sudo pacman -S wakeonlan jq curl

   # macOS (via Homebrew)
   brew install wakeonlan jq curl
   ```

2. **Copy the script to your server**:
   ```bash
   scp scripts/wol_monitor.sh user@your-server:/home/user/
   scp scripts/wol_monitor.service user@your-server:/home/user/
   ```

3. **Configure environment variables**:

   **Option A: Using command-line arguments** (recommended for testing):
   ```bash
   chmod +x wol_monitor.sh
   ./wol_monitor.sh \
     --mac-address [your address here] \
     --account-id your_cloudflare_account_id \
     --database-id your_d1_database_id \
     --api-token your_cloudflare_api_token \
     --poll-interval 30
   ```

   **Option B: Using environment variables**:
   ```bash
   export WOL_MAC_ADDRESS="[your address here]"
   export CLOUDFLARE_ACCOUNT_ID="your_account_id"
   export D1_DATABASE_ID="your_database_id"
   export CLOUDFLARE_API_TOKEN="your_api_token"
   export WOL_POLL_INTERVAL=30

   ./wol_monitor.sh
   ```

   **Option C: Using environment file** (recommended for systemd):
   ```bash
   # Create environment file
   sudo mkdir -p /etc/claude-draws
   sudo nano /etc/claude-draws/wol-monitor.env

   # Add these lines:
   WOL_MAC_ADDRESS=[your address here]
   CLOUDFLARE_ACCOUNT_ID=your_account_id
   D1_DATABASE_ID=your_database_id
   CLOUDFLARE_API_TOKEN=your_api_token
   WOL_POLL_INTERVAL=30
   WOL_LOG_FILE=/var/log/claude-draws-wol-monitor.log
   ```

4. **Set up systemd service** (optional but recommended):
   ```bash
   # Edit the service file with your paths and credentials
   sudo nano wol_monitor.service

   # Update these fields:
   # - User=YOUR_USERNAME
   # - Group=YOUR_GROUP
   # - WorkingDirectory=/path/to/claude-draws/scripts
   # - ExecStart=/path/to/claude-draws/scripts/wol_monitor.sh
   # - Environment variables or EnvironmentFile path

   # Install the service
   sudo cp wol_monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable claude-draws-wol-monitor
   sudo systemctl start claude-draws-wol-monitor
   ```

5. **Verify it's running**:
   ```bash
   # Check service status
   sudo systemctl status claude-draws-wol-monitor

   # View logs
   sudo journalctl -u claude-draws-wol-monitor -f

   # Or check the log file directly
   tail -f /var/log/claude-draws-wol-monitor.log
   ```

### How It Works

The WoL monitor runs continuously and:

1. Every 30 seconds, queries D1 database for pending submissions
2. If pending submissions found:
   - Sends Wake-on-LAN magic packet to PC's MAC address
   - Enforces 5-minute cooldown between wake attempts
3. Logs all activity for debugging

### Configuration

Environment variables / command-line arguments:

- `WOL_MAC_ADDRESS` / `--mac-address` (required) - MAC address of Windows PC
- `CLOUDFLARE_ACCOUNT_ID` / `--account-id` (required) - Cloudflare account ID
- `D1_DATABASE_ID` / `--database-id` (required) - D1 database ID
- `CLOUDFLARE_API_TOKEN` / `--api-token` (required) - Cloudflare API token
- `WOL_POLL_INTERVAL` / `--poll-interval` (default: 30) - Seconds between checks
- `WOL_LOG_FILE` / `--log-file` (default: /tmp/claude-draws-wol-monitor.log) - Log file path

### Troubleshooting

**PC not waking:**
- Verify Wake-on-LAN is enabled in BIOS and Windows (see prerequisites)
- Check if WoL packet is being sent: `sudo journalctl -u claude-draws-wol-monitor -n 50`
- Test WoL manually: `wakeonlan [your address here]`
- Ensure PC and server are on same subnet/VLAN
- Check router doesn't block WoL packets
- Try disabling "Fast Startup" in Windows power settings

**Script not finding pending submissions:**
- Verify D1 credentials are correct
- Test D1 query manually:
  ```bash
  curl -X POST "https://api.cloudflare.com/client/v4/accounts/YOUR_ACCOUNT/d1/database/YOUR_DB/query" \
    -H "Authorization: Bearer YOUR_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"sql":"SELECT COUNT(*) as count FROM submissions WHERE status = '\''pending'\''"}'
  ```

**Service not starting:**
- Check service logs: `sudo journalctl -u claude-draws-wol-monitor -n 50`
- Verify script path in service file
- Check file permissions: `ls -la /path/to/wol_monitor.sh`
- Ensure dependencies installed: `which wakeonlan jq curl`

### Uninstalling

```bash
# Stop and disable service
sudo systemctl stop claude-draws-wol-monitor
sudo systemctl disable claude-draws-wol-monitor

# Remove service file
sudo rm /etc/systemd/system/wol_monitor.service
sudo systemctl daemon-reload

# Remove environment file and logs (optional)
sudo rm /etc/claude-draws/wol-monitor.env
sudo rm /var/log/claude-draws-wol-monitor.log
```

## Testing the Complete System

1. **Verify sleep monitor is running** on Windows PC:
   ```powershell
   Get-ScheduledTask -TaskName "ClaudeDraws-SleepMonitor"
   Get-Content backend\scripts\sleep_monitor.log -Tail 10
   ```

2. **Verify WoL monitor is running** on remote server:
   ```bash
   sudo systemctl status claude-draws-wol-monitor
   tail -20 /var/log/claude-draws-wol-monitor.log
   ```

3. **Test sleep trigger**:
   - Ensure no artworks are in progress
   - Wait 15+ minutes with no activity
   - PC should automatically sleep
   - Check sleep monitor logs to confirm

4. **Test wake trigger**:
   - With PC asleep, submit a new request at claudedraws.com/submit
   - WoL monitor should detect it within 30 seconds
   - WoL packet should be sent
   - PC should wake up
   - Check WoL monitor logs to confirm packet was sent

5. **Test OBS stream resume**:
   - After PC wakes, check OBS streaming status
   - Workflow should automatically restart streaming if needed
   - Check Temporal workflow logs

## Notes

- **Cooldown periods**: WoL monitor has a 5-minute cooldown between wake attempts to avoid spamming
- **Docker containers**: Docker Desktop for Windows should automatically pause/resume containers during sleep/wake
- **Temporal reconnection**: Worker automatically reconnects to Temporal server after wake
- **OBS streaming**: Workflow now includes `ensure_obs_streaming()` activity to restart streaming if needed
- **Chrome CDP**: May require manual restart if connection is lost - not automatically recovered

## Security Considerations

- Store API tokens securely (use environment files with restricted permissions)
- Consider using Cloudflare API tokens with minimal scopes (only D1 read access needed)
- WoL packets are not encrypted - ensure trusted network environment
- Sleep monitor logs may contain sensitive information - restrict access appropriately
