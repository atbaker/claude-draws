# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Draws** is a livestream art project where Claude for Chrome creates crowdsourced illustrations using a JavaScript port of Kid Pix. The project consists of:

1. **Python CLI tool** (`claudedraw/`) - Automates submitting prompts to Claude for Chrome extension via browser automation
2. **Modified Kid Pix** (`kidpix/`) - Customized version of the open-source Kid Pix JavaScript app for Claude's use

## Key Architecture Details

### Browser Automation with Playwright + CDP

The core automation flow in `claudedraw/browser.py`:

1. **Environment variable must be set BEFORE importing Playwright**: `os.environ['PW_CHROMIUM_ATTACH_TO_OTHER'] = '1'`
   - This is critical - it enables Playwright's Node.js server to attach to Chrome extension side panels (which are targets of type "other")

2. **Hybrid automation approach**:
   - Playwright connects to Chrome via CDP (Chrome DevTools Protocol)
   - OS-level keyboard automation via `pyautogui` is required to trigger browser extension shortcuts (Command+E to open Claude side panel)
   - Playwright's `page.keyboard.press()` does NOT work for extension shortcuts - only affects page content

3. **Finding the side panel**:
   - After opening side panel with Command+E, must use `page.wait_for_timeout()` (not `time.sleep()`) to allow Playwright's context to update
   - Then iterate through `context.pages` to find the page with the Claude for Chrome extension ID in its URL

### Kid Pix Customizations

Located in `kidpix/` directory. This is a fork of the open-source Kid Pix JavaScript implementation.

**Build process**: Run `./build.sh` to concatenate all JS files from `js/` subdirectories into `js/app.js`

**Key modifications made**:
- Removed default splash screen image (`js/util/display.js` line ~146)
- Disabled localStorage loading to ensure blank canvas on every load (for fresh commissions)
- Updated social links in `index.html` to point to this project

**JavaScript structure**:
- `js/init/` - Initialization code
- `js/tools/` - Drawing tools
- `js/brushes/` - Brush implementations
- `js/stamps/` - Stamp tools
- `js/util/` - Utilities including `display.js` (canvas management)

## Development Commands

### Python CLI (root directory)

**Install dependencies**:
```bash
uv sync
```

**Run the CLI tool**:
```bash
# First, start Chrome with CDP enabled
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=.chrome-data

# Then run the tool
uv run claudedraw start --cdp-url ws://127.0.0.1:9222/devtools/browser/<browser-id> --prompt "Your prompt here"
```

**Note**: The CDP URL comes from navigating to `http://localhost:9222/json` in another browser and copying the `webSocketDebuggerUrl` of the browser target.

### Kid Pix Development (kidpix/ directory)

**Install dependencies**:
```bash
npm install
```

**Build the app** (required after any JS changes):
```bash
./build.sh
```

**Run locally**:
```bash
python3 -m http.server 8000
# Then open http://localhost:8000
```

## Important Constraints

- **Chrome data directory**: `.chrome-data/` is used for isolated Chrome profile (gitignored). Claude for Chrome extension must be installed and logged in here before running the CLI tool
- **Kid Pix canvas**: Intentionally starts blank (no localStorage, no splash) for fresh commissions each time Claude opens a new tab.
