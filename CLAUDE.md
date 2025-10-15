# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Draws** is an automated art project where Claude for Chrome creates crowdsourced illustrations using Kid Pix, sourced from Reddit requests. The complete workflow:

1. **Python CLI** (`claudedraw/`) monitors r/ClaudeDraws for art requests
2. **Browser automation** (Playwright + CDP) submits prompts to Claude for Chrome extension
3. **Claude draws** in a modified Kid Pix JavaScript app (served from local directory, not included in this repo)
4. **Temporal workflows** orchestrate the post-processing pipeline
5. **BAML extraction** parses Claude's title and artist statement from the final response
6. **Cloudflare R2** stores artwork images and metadata
7. **SvelteKit gallery** (`gallery/`) displays all artworks at claudedraws.com
8. **Cloudflare Workers** hosts the static gallery site

### Key Components

1. **Python CLI tool** (`claudedraw/`) - Browser automation to submit prompts to Claude for Chrome
2. **Temporal workflows** (`workflows/`) - Orchestrates artwork processing, metadata extraction, R2 upload, gallery rebuild, and deployment
3. **Temporal worker** (`worker/`) - Runs the Temporal worker process that executes workflow activities
4. **SvelteKit gallery** (`gallery/`) - Static site deployed to Cloudflare Workers
5. **BAML integration** (`baml_src/`) - AI-powered extraction of artwork titles and artist statements

## Key Architecture Details

### Temporal Workflow Architecture

**Primary Workflow**: `workflows/create_artwork.py` - `CreateArtworkWorkflow`

The workflow handles the **complete end-to-end process**:

1. **Browser automation** - Finds Reddit request, submits to Claude, waits for completion
2. **Extracts metadata** using BAML - Parses Claude's HTML response to extract artwork title and artist statement
3. **Uploads image to R2** - Stores PNG file in Cloudflare R2 bucket
4. **Uploads metadata to R2** - Stores JSON metadata file alongside image
5. **Appends to gallery metadata** - Updates local `gallery/src/lib/gallery-metadata.json` (gitignored)
6. **Rebuilds static site** - Runs `npm run build` in gallery directory
7. **Deploys to Cloudflare Workers** - Runs `wrangler deploy` to push updates live
8. **Posts Reddit comment** - Shares completed artwork with requester
9. **Schedules next workflow** (continuous mode only) - Enables livestream operation

**Key activities** in `workflows/activities.py`:
- `browser_session_activity()` - Long-running activity that automates the browser (find request → submit → wait → download)
- `extract_artwork_metadata()` - Uses BAML to parse Claude's response HTML
- `upload_image_to_r2()` - Uploads PNG to R2 with public access
- `upload_metadata_to_r2()` - Uploads JSON metadata to R2
- `append_to_gallery_metadata()` - Updates local gallery metadata file
- `rebuild_static_site()` - Runs npm build
- `deploy_to_cloudflare()` - Deploys via wrangler
- `post_reddit_comment_activity()` - Posts comment, approves/stickies it, updates flair
- `schedule_next_workflow()` - Schedules next workflow run (continuous mode)

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

### BAML Integration

**BAML** (Bounded Automation Markup Language) is used to reliably extract structured data from Claude's unstructured HTML responses.

**Key file**: `baml_src/artwork_metadata.baml`

The BAML function `ExtractArtworkMetadata` takes Claude's final HTML response and extracts:
- **Title**: Artwork title (e.g., "Sunset Over Mountains")
- **Artist Statement**: Claude's description/explanation of the artwork

This avoids fragile regex parsing and handles variations in Claude's response format automatically.

### Gallery Architecture

**Tech stack**:
- **Framework**: SvelteKit with static adapter
- **Styling**: Tailwind CSS
- **Hosting**: Cloudflare Workers (with static assets)
- **Storage**: Cloudflare R2 for images and metadata

**Key design principle**: R2 is the source of truth. The local `gallery/src/lib/gallery-metadata.json` file is gitignored and regenerated from R2 as needed.

**Build process**:
1. Temporal workflow appends new artwork to local JSON
2. SvelteKit reads JSON at build time and pre-renders all pages
3. Static HTML/CSS/JS output deployed to Cloudflare Workers
4. No runtime database queries - everything is pre-rendered

**Routes**:
- `/` - Gallery grid showing all artworks
- `/artwork/[id]` - Individual artwork detail page

### Reddit Integration

The workflow automatically:
1. Navigates to r/ClaudeDraws
2. Finds the first "Open" request
3. Extracts the request details (author, title, body, reference images)
4. Creates the artwork based on the request
5. Posts a comment with the completed artwork
6. Approves and stickies the comment
7. Updates the post flair to "Completed"

All Reddit interaction is handled within the Temporal workflow activities, providing automatic retries and visibility.

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
cd gallery
npm install
npm run dev
# Open http://localhost:5173
```

**Terminal 4: Run the CLI**
```bash
# Install Python dependencies
uv sync

# Start Chrome with CDP enabled
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=.chrome-data

# Get CDP URL from http://localhost:9222/json and run:
uv run claudedraw start --cdp-url ws://127.0.0.1:9222/devtools/browser/<browser-id>

# For continuous mode (livestream):
uv run claudedraw start --continuous --cdp-url ws://127.0.0.1:9222/devtools/browser/<browser-id>
```

**Note**: The CDP URL comes from navigating to `http://localhost:9222/json` in another browser and copying the `webSocketDebuggerUrl` of the browser target.

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

### BAML Development

**Regenerate BAML client** (after editing `.baml` files):
```bash
# BAML will auto-generate Python client in baml_client/
baml generate
```

## Important Constraints

- **Chrome data directory**: `.chrome-data/` is used for isolated Chrome profile (gitignored). Claude for Chrome extension must be installed and logged in here before running the CLI tool
- **Gallery metadata**: `gallery/src/lib/gallery-metadata.json` is gitignored - it's auto-generated by Temporal workflows and should not be checked into Git
- **Environment variables**: Required in `.env`:
  - `R2_ACCOUNT_ID` - Cloudflare R2 account ID
  - `R2_ACCESS_KEY_ID` - R2 API access key
  - `R2_SECRET_ACCESS_KEY` - R2 API secret key
  - `R2_BUCKET_NAME` - R2 bucket name (e.g., `claudedraws-dev`)
  - `R2_PUBLIC_URL` - Public R2 URL (e.g., `https://r2.claudedraws.com`)
  - `TEMPORAL_HOST` - Temporal server address (default: `localhost:7233`)
- **Docker Compose**: Temporal server and worker must be running for the full workflow to complete

## Troubleshooting

### Temporal workflow not starting
- Check that Temporal server is running: `docker-compose ps`
- Check that worker is running and connected: Check logs with `docker-compose logs worker`
- Verify environment variables in `.env`

### Gallery not updating
- Check Temporal workflow status in Temporal UI (http://localhost:8233)
- Verify `gallery/src/lib/gallery-metadata.json` exists and contains new artwork
- Check SvelteKit build logs for errors
- Verify wrangler deployment succeeded

### BAML extraction errors
- Check that the HTML response from Claude contains title and description
- Review BAML function definition in `baml_src/artwork_metadata.baml`
- Check BAML extraction logs in Temporal activity output
