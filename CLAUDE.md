# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Draws** is an automated art project where Claude for Chrome creates crowdsourced illustrations using Kid Pix, sourced from user submissions at claudedraws.xyz. The complete workflow:

1. **Web form** (claudedraws.xyz/submit) accepts art requests and stores them in Cloudflare D1
2. **Browser automation** (Playwright + CDP) submits prompts to Claude for Chrome extension
3. **OBS recording** captures the entire artwork creation process via WebSocket control
4. **Claude draws** in a modified Kid Pix JavaScript app (served from local directory, not included in this repo)
5. **Temporal workflows** orchestrate the post-processing pipeline
6. **BAML extraction** parses Claude's title and artist statement from the final response
7. **Cloudflare R2** stores artwork images and creation videos
8. **Cloudflare D1** stores artwork metadata (including video URLs) in SQLite database
9. **SvelteKit gallery** (`gallery/`) displays all artworks with videos at claudedraws.xyz with SSR-on-demand
10. **Cloudflare Workers** hosts the gallery site

### Repository Structure (Monorepo)

This repository uses a monorepo structure to organize different components:

```
claude-draws/
├── backend/              # Python backend (CLI, Temporal workflows, BAML)
│   ├── claudedraw/      # CLI tool for browser automation
│   ├── workflows/       # Temporal workflow definitions
│   ├── worker/          # Temporal worker process
│   ├── baml_src/        # BAML definitions for metadata extraction
│   ├── pyproject.toml   # Python dependencies
│   └── Dockerfile.worker # Container for worker
├── gallery/             # SvelteKit frontend (SSR-on-demand with D1 API)
├── .chrome-data/        # Chrome profile for automation (gitignored)
├── downloads/           # Temporary artwork storage (gitignored)
├── docs/               # Documentation
└── docker-compose.yml  # Orchestrates all services
```

### Key Components

1. **Python CLI tool** (`backend/claudedraw/`) - Browser automation to submit prompts to Claude for Chrome
2. **Temporal workflows** (`backend/workflows/`) - Orchestrates artwork processing, metadata extraction, R2 image upload, and D1 metadata insertion
3. **Temporal worker** (`backend/worker/`) - Runs the Temporal worker process that executes workflow activities
4. **SvelteKit gallery** (`gallery/`) - SSR-on-demand site with D1 API backend, deployed to Cloudflare Workers
5. **BAML integration** (`backend/baml_src/`) - AI-powered extraction of artwork titles and artist statements

## Key Architecture Details

### Temporal Workflow Architecture

**Primary Workflow**: `backend/workflows/create_artwork.py` - `CreateArtworkWorkflow`

The workflow handles the **complete end-to-end process**:

1. **Starts OBS recording** - Begins recording the artwork creation process for the gallery
2. **Browser automation** - Finds pending submission from D1, submits to Claude, waits for completion
3. **Stops OBS recording** - Ends recording and retrieves video file path
4. **Extracts metadata** using BAML - Parses Claude's HTML response to extract artwork title and artist statement
5. **Uploads image to R2** - Stores PNG file in Cloudflare R2 bucket with public access
6. **Uploads video to R2** - Stores MKV/MP4 recording in R2 bucket with public access
7. **Inserts metadata into D1** - Stores artwork metadata (including video URL) in D1 database (artwork appears immediately in gallery)
8. **Sends email notification** - Notifies requester when artwork is ready (if email provided)
9. **Schedules next workflow** (continuous mode only) - Enables livestream operation

**Key activities** in `backend/workflows/activities.py`:
- `start_obs_recording()` - Starts OBS recording to the recordings directory
- `browser_session_activity()` - Long-running activity that automates the browser (find submission → submit → wait → download)
- `stop_obs_recording()` - Stops OBS recording and returns the video file path
- `compress_video()` - Compresses video using PyAV (H.264, ~70-75% size reduction)
- `extract_artwork_metadata()` - Uses BAML to parse Claude's response HTML
- `upload_image_to_r2()` - Uploads PNG to R2 with public access
- `upload_video_to_r2()` - Uploads compressed video to R2 with public access
- `insert_artwork_to_d1()` - Inserts artwork metadata into D1 database
- `send_email_notification()` - Sends completion email to requester (if email provided)

**Browser Automation Details** (implemented in `browser_session_activity()`):

1. **Environment variable must be set BEFORE importing Playwright**: `os.environ['PW_CHROMIUM_ATTACH_TO_OTHER'] = '1'`
   - This is critical - it enables Playwright's Node.js server to attach to Chrome extension side panels (which are targets of type "other")

2. **Hybrid automation approach**:
   - Playwright connects to Chrome via CDP (Chrome DevTools Protocol)
   - OS-level keyboard automation via `pyautogui` is required to trigger browser extension shortcuts (Command+E to open Claude side panel)
   - Playwright's `page.keyboard.press()` does NOT work for extension shortcuts - only affects page content

3. **Finding the side panel**:
   - After opening side panel with Command+E, must use `page.wait_for_timeout()` (not `time.sleep()`) to allow Playwright's context to update
   - Then iterate through `context.pages` to find the page with the Claude for Chrome extension ID in its URL

4. **Heartbeats during long operations**:
   - The browser session activity sends heartbeats to Temporal every 30 seconds while waiting for Claude
   - Allows Temporal to detect worker crashes during the 5-10 minute drawing process

**Why Temporal?**
- Automatic retries on failure (network issues, API rate limits, etc.)
- Visibility into each step via Temporal UI
- Resumable if worker crashes mid-process
- Heartbeat mechanism for long-running operations
- Easy to add new steps (e.g., video processing, social media posting)
- Continuous mode support for livestreaming

**CRITICAL: Activity Registration**
When adding new Temporal activities, you MUST register them in TWO places:
1. Import in `backend/worker/main.py` (line 15-33)
2. Add to `activities=[...]` list in Worker constructor (line 61-78)

Without both steps, the worker will fail with: `Activity function <name> is not registered on this worker`

### BAML Integration

**BAML** (Bounded Automation Markup Language) is used to reliably extract structured data from Claude's unstructured HTML responses.

**Key file**: `backend/baml_src/artwork_metadata.baml`

The BAML function `ExtractArtworkMetadata` takes Claude's final HTML response and extracts:
- **Title**: Artwork title (e.g., "Sunset Over Mountains")
- **Artist Statement**: Claude's description/explanation of the artwork

This avoids fragile regex parsing and handles variations in Claude's response format automatically.

### OBS Recording Integration

The system automatically records each artwork creation process via OBS (Open Broadcaster Software) and uploads the videos to R2 for viewing in the gallery.

**Architecture**:

1. **OBS WebSocket Client** (`backend/workflows/obs_client.py`)
   - Custom WebSocket client implementing OBS WebSocket Protocol v5
   - Handles authentication, request/response, and event subscriptions
   - Subscribes to Output events (512 bitmask) to capture recording state changes

2. **Recording Workflow**:
   - **Start**: Before browser automation begins, `start_obs_recording()` activity:
     - Sets OBS recording directory to `downloads/recordings/` (via host OS path)
     - Starts recording (with safety check to stop any existing recording)
   - **During**: OBS records the entire artwork creation process (5-10 minutes)
   - **Stop**: After browser automation completes, `stop_obs_recording()` activity:
     - Stops recording and waits for `RecordStateChanged` event
     - Event provides the host OS file path (e.g., Windows: `C:\...\downloads\recordings\2025-11-04 14-30-45.mkv` or macOS: `/Users/.../downloads/recordings/2025-11-04 14-30-45.mkv`)
     - Converts host OS path to container path (`/app/downloads/recordings/...`)
     - Verifies file exists in mounted volume
   - **Compress**: `compress_video()` activity compresses the video using PyAV:
     - Converts to H.264 MP4 with CRF 23 (excellent quality)
     - AAC audio at 128 kbps
     - Preserves original resolution (1280x720)
     - Achieves ~70-75% file size reduction (e.g., 112 MB → 25-30 MB)
     - Deletes original uncompressed file
     - Processing time: 30-90 seconds
   - **Upload**: `upload_video_to_r2()` activity uploads compressed video to R2 and cleans up local file

3. **Key Technical Details**:
   - **Event handling**: Client subscribes to recording events to capture the output file path when recording stops
   - **Path translation**: Host OS paths from OBS are converted to Docker container paths using the mounted `downloads/` volume
   - **PyAV compression**: Uses PyAV library (FFmpeg bindings) for frame-by-frame video transcoding - no system FFmpeg installation required
   - **Error resilience**: Recording and compression failures do not block artwork creation - workflow continues without video
   - **File cleanup**: Original uncompressed files deleted after successful compression; compressed files deleted after R2 upload
   - **Video formats**: Input supports MKV (OBS default), MOV, and AVI; output is always H.264 MP4 with AAC audio

4. **Configuration** (in `backend/.env`):
   - `OBS_WEBSOCKET_URL` - WebSocket server URL (default: `ws://host.docker.internal:4444`)
   - `OBS_WEBSOCKET_PASSWORD` - WebSocket authentication password
   - `OBS_RECORDING_DIR` - Host OS path for recordings (e.g., Windows: `C:\Users\...\claude-draws\downloads\recordings`, macOS: `/Users/.../claude-draws/downloads/recordings`)

5. **Gallery Integration**:
   - Video URLs stored in D1 `artworks.video_url` column
   - Gallery artwork detail pages (`/artwork/[id]`) display "Watch Video" link when available
   - Videos are publicly accessible via R2 CDN

### Gallery Architecture

**Tech stack**:
- **Framework**: SvelteKit with Cloudflare adapter (SSR-on-demand)
- **Styling**: Tailwind CSS
- **Hosting**: Cloudflare Workers
- **Database**: Cloudflare D1 for artwork metadata
- **Storage**: Cloudflare R2 for images

**Key design principle**: D1 is the source of truth for metadata. Gallery pages use SSR-on-demand to fetch fresh data from D1 API endpoints, so new artworks appear immediately without requiring a rebuild or deployment.

**Data flow**:
1. Temporal workflow inserts artwork metadata into D1 database
2. Gallery API endpoints (`/api/artworks`, `/api/artworks/[id]`) query D1
3. SvelteKit pages fetch from these API endpoints at request time
4. New artworks appear in gallery instantly (no build/deploy required)

**Routes**:
- `/` - Home page with livestream and gallery preview
- `/gallery` - Full gallery grid showing all artworks
- `/artwork/[id]` - Individual artwork detail page
- `/submit` - Submission form for art requests
- `/queue` - View all pending submissions in queue
- `/about` - About page explaining the project

**Queue Ordering System**:
- **Upvote-based**: Submissions with more upvotes are processed first
- **FIFO tiebreaker**: When submissions have equal upvotes, the oldest is processed first
- **Initial upvote**: Every submission starts with 1 upvote (the submitter's)
- **Client-side tracking**: localStorage tracks which submissions a user has upvoted and created
  - `upvotedSubmissions`: Array of submission IDs the user has upvoted
  - `mySubmissions`: Array of submission IDs the user has created
- **User restrictions**: Users cannot upvote or un-upvote their own submissions, but can toggle upvotes on others' submissions
- **Database ordering**: Queries use `ORDER BY upvote_count DESC, created_at ASC` for efficient queue processing

### Power Management (Wake-on-LAN)

The system includes automated power management to reduce energy consumption while maintaining responsiveness to new submissions. The Windows PC automatically sleeps after inactivity and wakes when new requests arrive.

**Architecture**:

1. **Sleep Monitor** (`scripts/sleep_monitor.ps1`) - PowerShell script running on Windows PC
   - Queries D1 database every 60 seconds to check for:
     - Active submissions (status = 'processing')
     - Time since last completed artwork
   - Triggers Windows sleep if no activity for 15+ minutes (configurable)
   - Runs as Windows Scheduled Task (starts automatically at boot)
   - Uses Cloudflare D1 REST API to query submission status

2. **Wake-on-LAN Monitor** (`scripts/wol_monitor.sh`) - Bash script running on remote server (e.g., Home Assistant)
   - Runs once per invocation (scheduled by Home Assistant automation every 30 seconds)
   - Queries D1 database for pending submissions via REST API
   - Returns exit code: 0 = wake needed, 1 = no action, 2 = error
   - Home Assistant's `wake_on_lan` integration sends magic packet when exit code is 0
   - Designed for Home Assistant OS (no dependency installation required)

3. **OBS Streaming Resume** (`workflows/activities.py` - `ensure_obs_streaming()`)
   - Temporal activity that checks OBS streaming status after scene switch
   - Automatically restarts OBS stream if not active (useful after wake from sleep)
   - Called in `CheckSubmissionsWorkflow` before displaying gallery

**Setup Instructions**: See `scripts/README.md` for detailed installation and configuration instructions.

**Key benefits**:
- Significantly reduces power consumption during idle periods
- PC automatically wakes when work is available
- No manual intervention required
- All Docker containers (Temporal, worker) resume automatically after wake
- OBS streaming automatically resumes via workflow activity

**Requirements**:
- Wake-on-LAN enabled in PC BIOS and network adapter settings
- PC and remote server on same network/subnet
- Cloudflare D1 API credentials configured in `backend/.env`

## Development Commands

### Full Stack Development Setup

**Terminal 1: Start Temporal server**
```bash
docker-compose up temporal
```

**Terminal 2: Start Temporal worker**
```bash
docker-compose up worker
```

**Terminal 3: Gallery dev server (optional)**
```bash
# Option 1: Using Docker Compose
docker-compose up gallery

# Option 2: Running locally
cd gallery
npm install
npm run dev
# Open http://localhost:5173
```

**Terminal 4: Run the CLI**
```bash
# Install Python dependencies (from backend directory)
cd backend
uv sync

# Start Chrome with CDP enabled (from repo root)
cd ..
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=.chrome-data

# Set CDP URL in backend/.env:
# 1. Navigate to http://localhost:9222/json in another browser
# 2. Copy the webSocketDebuggerUrl of the browser target
# 3. Add to backend/.env:
#    CHROME_CDP_URL=ws://127.0.0.1:9222/devtools/browser/<browser-id>

# Run the CLI (from backend directory)
cd backend
uv run claudedraw start

# For continuous mode (livestream):
uv run claudedraw start --continuous
```

**Note**: The CDP URL is set once in `backend/.env` and reused across sessions. Get it from `http://localhost:9222/json` (the `webSocketDebuggerUrl` of the browser target).

**Continuous Mode**:
- Automatically schedules the next workflow after each artwork completes
- Perfect for livestreaming - the workflow runs indefinitely
- Each artwork gets its own workflow in Temporal UI for easy debugging
- Stop by canceling the active workflow in Temporal UI

### Gallery Development

**Install dependencies**:
```bash
cd gallery
npm install
```

**Configure local environment variables**:
```bash
# Copy the example file
cp .dev.vars.example .dev.vars

# Edit .dev.vars and add your API keys
# RESEND_API_KEY=your_resend_api_key_here
# ADMIN_NOTIFICATION_EMAIL=admin@example.com
```

**Run dev server**:
```bash
npm run dev
```

**Build for production**:
```bash
npm run build
```

**Deploy to Cloudflare Workers**:
```bash
wrangler deploy
```

**Configure environment variables for Cloudflare Workers**:
```bash
cd gallery
# Set Resend API key (required for admin notifications)
wrangler secret put RESEND_API_KEY
# Enter your Resend API key when prompted

# Set admin notification email
wrangler secret put ADMIN_NOTIFICATION_EMAIL
# Enter your admin email address when prompted
```

Alternatively, configure via [Cloudflare Dashboard](https://dash.cloudflare.com) → Workers & Pages → Your Worker → Settings → Variables and Secrets.

### BAML Development

**Regenerate BAML client** (after editing `.baml` files):
```bash
cd backend
# BAML will auto-generate Python client in backend/baml_client/
uv run baml-cli generate
```

## Important Constraints

- **Chrome data directory**: `.chrome-data/` is used for isolated Chrome profile (gitignored). Claude for Chrome extension must be installed and logged in here before running the CLI tool
- **Environment variables**: Required in `backend/.env` (copy from `backend/.env.example`):
  - `ANTHROPIC_API_KEY` - Anthropic API key for BAML
  - `R2_ACCOUNT_ID` - Cloudflare R2 account ID
  - `R2_ACCESS_KEY_ID` - R2 API access key
  - `R2_SECRET_ACCESS_KEY` - R2 API secret key
  - `R2_BUCKET_NAME` - R2 bucket name (e.g., `claudedraws-dev`)
  - `R2_PUBLIC_URL` - Public R2 URL (e.g., `https://r2.claudedraws.xyz`)
  - `D1_API_TOKEN` - Cloudflare API token for D1 database access
  - `D1_ACCOUNT_ID` - Cloudflare account ID for D1
  - `D1_DATABASE_ID` - D1 database ID
  - `RESEND_API_KEY` - Resend API key for email notifications
  - `RESEND_FROM_EMAIL` - From email address for notifications
  - `ADMIN_NOTIFICATION_EMAIL` - Admin email address for submission notifications
  - `TEMPORAL_HOST` - Temporal server address (default: `localhost:7233`)
  - `CHROME_CDP_URL` - Chrome DevTools Protocol WebSocket URL (get from `http://localhost:9222/json`)
  - `OBS_WEBSOCKET_URL` - OBS WebSocket server URL (default: `ws://host.docker.internal:4444`)
  - `OBS_WEBSOCKET_PASSWORD` - OBS WebSocket password
  - `OBS_RECORDING_DIR` - Host OS path for OBS recordings (Windows: `C:\Users\...\claude-draws\downloads\recordings`, macOS: `/Users/.../claude-draws/downloads/recordings`)
- **Cloudflare Workers environment variables**: The gallery submission API requires these environment variables in Cloudflare Workers (configure via `wrangler secret put` or Cloudflare dashboard):
  - `RESEND_API_KEY` - Resend API key (same as backend)
  - `ADMIN_NOTIFICATION_EMAIL` - Admin email address (same as backend)
- **Docker Compose**: Temporal server and worker must be running for the full workflow to complete

## Troubleshooting

### Temporal workflow not starting
- Check that Temporal server is running: `docker-compose ps`
- Check that worker is running and connected: Check logs with `docker-compose logs worker`
- Verify environment variables in `backend/.env`

### Gallery not updating
- Check Temporal workflow status in Temporal UI (http://localhost:8233)
- Verify artwork was inserted into D1: Check D1 database with `wrangler d1 execute claudedraws-dev --local --command "SELECT * FROM artworks ORDER BY created_at DESC LIMIT 5"`
- Check that R2 image upload succeeded
- Verify API endpoints are working: Visit `/api/artworks` to see if data is returned
- Check browser console for API errors

### BAML extraction errors
- Check that the HTML response from Claude contains title and description
- Review BAML function definition in `backend/baml_src/artwork_metadata.baml`
- Check BAML extraction logs in Temporal activity output
