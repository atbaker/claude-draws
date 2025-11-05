# Claude Draws - Power Management Scripts

This directory contains scripts for automated power management using Wake-on-LAN (WoL). The system allows the Windows PC to sleep after periods of inactivity and wake automatically when new submissions are detected.

## Architecture Overview

The power management system has three main components:

1. **System Status Endpoint** (Cloudflare Workers) - API endpoint at `/api/system-status` that queries D1 and returns wake/sleep status
2. **Sleep Monitor** (Windows PC) - PowerShell script that checks the endpoint and triggers sleep after inactivity
3. **WoL Monitor** (Remote Server) - Bash script that checks the endpoint and signals for Wake-on-LAN

Both monitors now query a centralized endpoint instead of D1 directly, simplifying credential management and centralizing the power management logic.

## Component 1: Sleep Monitor (Windows PC)

### Prerequisites

- Windows PC with PowerShell 5.1 or later
- Access to the Claude Draws gallery endpoint (default: https://claudedraws.com)

### Installation

1. **Run the installation script as Administrator**:
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

The sleep monitor supports these parameters (can be passed when running the script):

- `GalleryUrl` (default: "https://claudedraws.com") - URL of the Claude Draws gallery site
- `PollIntervalSeconds` (default: 60) - How often to check for activity

The inactivity threshold (15 minutes) is hardcoded in the API endpoint.

### How It Works

The sleep monitor runs continuously and:

1. Every minute, calls the `/api/system-status` endpoint
2. Endpoint returns a JSON response including `shouldSleep` boolean
3. If `shouldSleep` is true:
   - Triggers Windows sleep via `SetSuspendState` API
4. Logs all activity to `sleep_monitor.log`

The endpoint determines `shouldSleep` based on:
- No submissions with status = 'processing'
- Last artwork completion > 15 minutes ago

### Troubleshooting

**Sleep not triggering:**
- Check logs: `Get-Content backend\scripts\sleep_monitor.log -Tail 50`
- Verify the gallery endpoint is accessible: `Invoke-RestMethod -Uri "https://claudedraws.com/api/system-status"`
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
- `jq` package (for JSON parsing, usually pre-installed)
- `curl` (usually pre-installed)
- Access to the Claude Draws gallery endpoint (default: https://claudedraws.com)
- PC's MAC address and Wake-on-LAN enabled in BIOS
- **For Home Assistant**: The `wake_on_lan` integration (install via Configuration → Integrations)

**Note**: The script checks the gallery endpoint for pending submissions and returns an exit code. Home Assistant's `wake_on_lan` integration sends the actual WoL packet (avoiding network interface complexity in containerized environments).

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

### Installation on Home Assistant

1. **Install the Wake-on-LAN integration**:
   - Go to Configuration → Devices & Services → Add Integration
   - Search for "Wake on LAN" and install it
   - Or add to `configuration.yaml`:
     ```yaml
     wake_on_lan:
     ```

2. **Copy the script to Home Assistant**:
   - Use the File Editor add-on or SSH to create `/config/scripts/wol_monitor.sh`
   - Copy the contents from `scripts/wol_monitor.sh`
   - Make it executable: `chmod +x /config/scripts/wol_monitor.sh`

3. **Add to `configuration.yaml`**:
   ```yaml
   shell_command:
     check_claude_draws: >
       /config/scripts/wol_monitor.sh
       --gallery-url https://claudedraws.com
       --log-file /config/logs/wol_monitor.log
   ```

4. **Create the automation**:
   ```yaml
   automation:
     - alias: "Check for Claude Draws submissions and wake PC"
       trigger:
         - platform: time_pattern
           seconds: "/30"  # Run every 30 seconds
       action:
         - service: shell_command.check_claude_draws
           response_variable: check_result
         - if:
             - condition: template
               value_template: "{{ check_result.returncode == 0 }}"
           then:
             - service: wake_on_lan.send_magic_packet
               data:
                 mac: "2C:F0:5D:70:48:AA"  # Replace with your PC's MAC address
   ```

5. **Restart Home Assistant** to apply the changes

### Installation on Standard Linux Server

For non-Home Assistant environments, combine the check script with `wakeonlan` or `etherwake`:

1. **Install wakeonlan**:
   ```bash
   # Debian/Ubuntu
   sudo apt-get install wakeonlan

   # Arch Linux
   sudo pacman -S wakeonlan
   ```

2. **Create a wrapper script** that runs the check and sends WoL:
   ```bash
   #!/bin/bash
   /path/to/wol_monitor.sh --account-id ... --database-id ... --api-token ...
   if [ $? -eq 0 ]; then
     wakeonlan 2C:F0:5D:70:48:AA
   fi
   ```

3. **Schedule with cron**:
   ```bash
   # Run every 30 seconds
   * * * * * /path/to/wrapper.sh
   * * * * * sleep 30; /path/to/wrapper.sh
   ```

### How It Works

The WoL monitor is a two-part system:

**Part 1: Check Script** (`wol_monitor.sh`)
1. Calls the `/api/system-status` endpoint
2. Parses the JSON response for the `shouldWake` boolean
3. Returns exit code based on result:
   - **Exit 0**: `shouldWake` is true → trigger WoL
   - **Exit 1**: `shouldWake` is false → no action
   - **Exit 2**: API error → check logs

**Part 2: Wake-on-LAN** (Home Assistant integration)
1. Home Assistant automation runs the check script every 30 seconds
2. If exit code is 0, Home Assistant's `wake_on_lan` integration sends the magic packet
3. PC wakes up and resumes Temporal workflow

The endpoint determines `shouldWake` based on pending submission count (> 0 means wake needed).

This two-part design avoids network interface issues in containerized environments.

### Configuration

Environment variables / command-line arguments:

- `GALLERY_URL` / `--gallery-url` (default: https://claudedraws.com) - URL of the Claude Draws gallery site
- `WOL_LOG_FILE` / `--log-file` (default: /tmp/claude-draws-wol-monitor.log) - Log file path

### Troubleshooting

**PC not waking:**
- Verify Wake-on-LAN is enabled in BIOS and Windows (see prerequisites)
- Check Home Assistant automation history to see if WoL packet was sent
- Test WoL manually in Home Assistant: Developer Tools → Services → `wake_on_lan.send_magic_packet`
- Verify the MAC address is correct in your automation
- Ensure PC and Home Assistant are on same subnet/VLAN
- Check router doesn't block WoL packets
- Try disabling "Fast Startup" in Windows power settings

**Script not finding pending submissions:**
- Check the script logs: `tail -50 /config/logs/wol_monitor.log`
- Test the endpoint manually from Home Assistant Terminal add-on:
  ```bash
  curl -s https://claudedraws.com/api/system-status | jq
  ```
- Verify the endpoint is accessible and returns valid JSON
- Check automation is running: Configuration → Automations & Scenes

**Automation not triggering:**
- Check automation history in Home Assistant UI
- Verify shell_command is defined in `configuration.yaml`
- Check Home Assistant logs: Settings → System → Logs
- Test shell command manually: Developer Tools → Services → `shell_command.check_claude_draws`
- Verify script has execute permissions: `ls -la /config/scripts/wol_monitor.sh`

### Uninstalling

**For Home Assistant:**
- Delete the shell_command and automation from `configuration.yaml`
- Remove the script file from `/config/scripts/`

**For systemd:**
```bash
# Stop and disable service/timer
sudo systemctl stop claude-draws-wol-monitor.timer
sudo systemctl disable claude-draws-wol-monitor.timer

# Remove service files
sudo rm /etc/systemd/system/wol_monitor.service
sudo rm /etc/systemd/system/wol_monitor.timer
sudo systemctl daemon-reload

# Remove logs (optional)
sudo rm /var/log/claude-draws-wol-monitor.log
```

**For cron:**
- Remove the cron entries: `crontab -e` and delete the relevant lines

## Testing the Complete System

1. **Verify sleep monitor is running** on Windows PC:
   ```powershell
   Get-ScheduledTask -TaskName "ClaudeDraws-SleepMonitor"
   Get-Content scripts\sleep_monitor.log -Tail 10
   ```

2. **Verify WoL monitor is configured** on remote server:
   ```bash
   # For Home Assistant: Check automation in UI
   # For systemd: sudo systemctl status claude-draws-wol-monitor.timer
   # For cron: crontab -l | grep wol_monitor

   # Check recent logs
   tail -20 /config/logs/wol_monitor.log  # Home Assistant
   # or
   tail -20 /tmp/claude-draws-wol-monitor.log  # Other systems
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

- The system status endpoint is public and does not require authentication
- WoL packets are not encrypted - ensure trusted network environment
- Monitor logs may contain submission details - restrict access appropriately
- Consider rate limiting the `/api/system-status` endpoint if needed
