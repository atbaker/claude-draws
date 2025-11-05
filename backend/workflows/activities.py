"""Temporal activities for Claude Draws artwork processing."""

import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Dict, Optional, Tuple

import boto3
import httpx
import resend
from botocore.exceptions import ClientError
from baml_client.sync_client import b
from dotenv import load_dotenv
from jinja2 import Template
from playwright.async_api import async_playwright
from pydantic import BaseModel
from temporalio import activity
from temporalio.client import Client
from temporalio.common import RetryPolicy

# Import OBS WebSocket client
from workflows.obs_client import OBSWebSocketClient, OBSWebSocketError

# Load environment variables
load_dotenv()

# IMPORTANT: Set this environment variable BEFORE importing playwright
# This enables the underlying Node.js server to attach to Chrome targets of type "other"
# (such as extension side panels) as if they were regular pages
os.environ['PW_CHROMIUM_ATTACH_TO_OTHER'] = '1'

# R2 Configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

# Temporal Configuration
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "claude-draws-queue"

# Chrome Extension
CLAUDE_EXTENSION_ID = os.getenv("CLAUDE_EXTENSION_ID")
ONBOARDING_PAGE_URL = "https://claude.ai/chrome/installed"

# Cloudflare D1 Configuration
D1_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
D1_DATABASE_ID = os.getenv("D1_DATABASE_ID")  # From wrangler d1 create output
D1_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

# Resend Email Configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "Claude Draws <noreply@claudedraws.com>")

# OBS WebSocket Configuration
OBS_WEBSOCKET_URL = os.getenv("OBS_WEBSOCKET_URL", "ws://localhost:4444")
OBS_WEBSOCKET_PASSWORD = os.getenv("OBS_WEBSOCKET_PASSWORD", "")
OBS_MAIN_SCENE = os.getenv("OBS_MAIN_SCENE", "Main Scene")
OBS_SCREENSAVER_SCENE = os.getenv("OBS_SCREENSAVER_SCENE", "Screensaver")
OBS_COUNTDOWN_TEXT_SOURCE = os.getenv("OBS_COUNTDOWN_TEXT_SOURCE", "CountdownTimer")
OBS_SCREENSAVER_MEDIA_SOURCE = os.getenv("OBS_SCREENSAVER_MEDIA_SOURCE", "After Dark - Nocturnes")

# Screensaver video files (in obs/ directory)
SCREENSAVER_VIDEOS = [
    "after-dark-bad-dog.mp4",
    "after-dark-fish.mp4",
    "after-dark-flying-toasters.mp4",
    "after-dark-nocturne.mp4",
    "after-dark-rat-race.mp4",
]

# Paths
BACKEND_ROOT = Path(__file__).parent.parent  # /app/backend
GALLERY_DIR = BACKEND_ROOT.parent / "gallery"  # /app/gallery
DOWNLOADS_DIR = BACKEND_ROOT.parent / "downloads"  # /app/downloads
RECORDINGS_DIR = DOWNLOADS_DIR / "recordings"  # /app/downloads/recordings

# Ensure recordings directory exists
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)


def get_host_path_class(path_str: str):
    """
    Detect whether a path string is Windows or Unix-based and return the appropriate
    pathlib class for constructing host OS paths from within a Linux container.

    Args:
        path_str: The path string to analyze (e.g., PROJECT_HOST_DIR)

    Returns:
        PureWindowsPath for Windows paths (C:\ or C:/)
        PurePosixPath for macOS/Linux paths (/Users/... or /home/...)
    """
    # Check if path starts with Windows drive letter (e.g., C:\ or C:/)
    if re.match(r'^[A-Za-z]:[/\\]', path_str):
        return PureWindowsPath
    return PurePosixPath


class BrowserSessionResult(BaseModel):
    """Result from browser_session_activity."""
    image_path: str
    response_html: str
    submission_id: Optional[str]  # D1 submission ID if from form
    submission_email: Optional[str]  # Email for notification if provided
    tab_url: str  # URL of the tab to reconnect to later (e.g., https://kidpix.claudedraws.com)
    prompt: str  # The full prompt text submitted to Claude


def get_r2_client():
    """Create and return an R2 client using boto3."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


async def get_d1_client():
    """Create and return an async HTTP client for D1 API."""
    return httpx.AsyncClient(
        base_url=f"https://api.cloudflare.com/client/v4/accounts/{D1_ACCOUNT_ID}/d1/database/{D1_DATABASE_ID}",
        headers={
            "Authorization": f"Bearer {D1_API_TOKEN}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


async def query_d1(sql: str, params: list = None) -> Dict:
    """
    Execute a SQL query against the D1 database via HTTP API.

    Args:
        sql: SQL query string
        params: Optional list of parameters for the query

    Returns:
        Dict containing query results
    """
    async with await get_d1_client() as client:
        payload = {"sql": sql}
        if params:
            payload["params"] = params

        response = await client.post("/query", json=payload)
        response.raise_for_status()
        return response.json()


async def visit_gallery(page) -> None:
    """
    Navigate to the Claude Draws gallery for livestream viewers.

    Shows the gallery website briefly so viewers can see the completed artworks
    and decide to visit in their own browser.

    Args:
        page: Playwright page object
    """
    activity.logger.info("Navigating to Claude Draws gallery...")
    await page.goto('https://claudedraws.com')
    await page.wait_for_load_state('domcontentloaded')

    # Show gallery for 5 seconds
    activity.logger.info("Displaying gallery for 5 seconds...")
    await page.wait_for_timeout(5000)
    activity.logger.info("✓ Gallery visit complete")


async def get_next_submission(page) -> Optional[Dict]:
    """
    Query D1 database for the next pending submission.

    Finds the oldest pending submission from the D1 database and navigates
    to the gallery for livestream viewers.

    Args:
        page: Playwright page object

    Returns:
        Dict with submission data, or None if no submissions found
    """
    activity.logger.info("Querying D1 for pending submissions...")

    try:
        # Query D1 for pending submissions, ordered by upvote_count DESC (most upvoted first), then created_at ASC (FIFO tiebreaker)
        result = await query_d1(
            "SELECT id, prompt, email FROM submissions WHERE status = ? ORDER BY upvote_count DESC, created_at ASC LIMIT 1",
            ["pending"]
        )

        # Check if we got any results
        if not result.get("success"):
            activity.logger.error(f"D1 query failed: {result}")
            return None

        results = result.get("result", [{}])[0].get("results", [])

        if not results:
            activity.logger.info("No pending submissions found in D1")
            return None

        submission = results[0]
        submission_id = submission["id"]
        prompt = submission["prompt"]
        email = submission.get("email")

        activity.logger.info(f"✓ Found submission: {submission_id}")
        activity.logger.info(f"Prompt preview: {prompt[:100]}...")

        # Navigate to gallery for livestream viewers
        activity.logger.info("Navigating to gallery for livestream viewers...")
        await page.goto('https://claudedraws.com')
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(3000)

        return {
            "submission_id": submission_id,
            "prompt": prompt,
            "email": email,
        }

    except Exception as e:
        activity.logger.error(f"Error querying D1: {e}")
        return None


def format_artwork_prompt(user_prompt: str) -> str:
    """
    Format an artwork prompt for Claude using Jinja2 templates.

    Args:
        user_prompt: User-submitted prompt text

    Returns:
        str: Formatted prompt ready for Claude
    """
    # Load shared Kid Pix instructions
    kidpix_instructions_path = BACKEND_ROOT / "claudedraw" / "kidpix_instructions.md"
    with open(kidpix_instructions_path, 'r') as f:
        kidpix_instructions = f.read()

    # Use user submission template
    template_path = BACKEND_ROOT / "claudedraw" / "user_submission_template.md"
    with open(template_path, 'r') as f:
        template_text = f.read()

    template = Template(template_text)
    return template.render(
        user_prompt=user_prompt,
        kidpix_instructions=kidpix_instructions,
    )


async def open_claude_side_panel(page, context):
    """
    Open Claude for Chrome side panel using the official onboarding page mechanism.

    This uses Anthropic's onboarding button to trigger the side panel without
    needing OS-level keyboard automation (pyautogui).

    Args:
        page: The current Playwright page
        context: The browser context containing all pages

    Returns:
        The Playwright page object for the Claude side panel

    Raises:
        RuntimeError: If the side panel cannot be opened or found
    """
    activity.logger.info(f"Navigating to onboarding page: {ONBOARDING_PAGE_URL}")
    await page.goto(ONBOARDING_PAGE_URL, wait_until="domcontentloaded")

    # Wait for the hidden onboarding button to be present
    activity.logger.info("Waiting for onboarding button...")
    try:
        await page.locator("#claude-onboarding-button").wait_for(state="hidden", timeout=10000)
        activity.logger.info("Found onboarding button")
    except Exception as e:
        raise RuntimeError(f"Could not find onboarding button: {e}")

    # Set prompt to a single space (better UX - we'll fill in real prompt later)
    # and click the button to open side panel
    activity.logger.info("Triggering side panel via onboarding button...")
    await page.evaluate("""
        document.getElementById('claude-onboarding-button')
            .setAttribute('data-task-prompt', ' ');
        document.getElementById('claude-onboarding-button').click();
    """)

    # Wait a moment for side panel to open
    await page.wait_for_timeout(2000)

    # Find the side panel page
    activity.logger.info("Finding side panel page...")
    side_panel_page = None
    for p in context.pages:
        if CLAUDE_EXTENSION_ID in p.url:
            side_panel_page = p
            activity.logger.info(f"Found side panel: {p.url}")
            break

    if not side_panel_page:
        raise RuntimeError("Could not find Claude side panel page after opening")

    # Wait one more moment so livestream viewers can see the side panel
    await page.wait_for_timeout(2000)

    return side_panel_page


@activity.defn
async def browser_session_activity(cdp_url: str, submission_id: Optional[str] = None) -> BrowserSessionResult:
    """
    Long-running activity that handles the full browser automation session.

    This activity:
    1. Retrieves a specific submission (if submission_id provided) or finds a pending one
    2. Opens Claude side panel
    3. Submits the formatted prompt
    4. Waits for Claude to complete (with heartbeats)
    5. Downloads the artwork PNG

    Args:
        cdp_url: Chrome DevTools Protocol URL
        submission_id: Optional specific submission ID to process (from CheckSubmissionsWorkflow)

    Returns:
        BrowserSessionResult with paths and metadata
    """
    activity.logger.info(f"Starting browser session activity (submission_id={submission_id})...")

    async with async_playwright() as p:
        # Connect to the existing browser via CDP
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]

        # Always create a new tab for this workflow run
        # This ensures clean isolation and avoids interfering with other tabs (e.g., background music)
        page = await context.new_page()
        activity.logger.info("Created new tab for this workflow run")

        try:
            # Get submission - either the specific one provided or find the next pending one
            # Note: Gallery visit now happens in CheckSubmissionsWorkflow before this activity
            if submission_id:
                # Specific submission requested - fetch it from D1
                activity.logger.info(f"Fetching specific submission: {submission_id}")
                result = await query_d1(
                    """
                    SELECT id, prompt, email, created_at
                    FROM submissions
                    WHERE id = ? AND status IN ('pending', 'processing')
                    LIMIT 1
                    """,
                    [submission_id]
                )

                # Parse D1 HTTP API response structure: result -> result[0] -> results
                results = result.get("result", [{}])[0].get("results", [])
                if results and len(results) > 0:
                    submission_data = results[0]
                    submission = {
                        'submission_id': submission_data['id'],
                        'prompt': submission_data['prompt'],
                        'email': submission_data.get('email'),
                    }
                    activity.logger.info(f"✓ Found submission: {submission_id}")
                else:
                    activity.logger.warning(f"⚠ Submission {submission_id} not found or not in processable state")
                    submission = None
            else:
                # No specific submission - find next pending one
                submission = await get_next_submission(page)

            # Ensure we have a submission
            if submission is None:
                raise ValueError("No pending submission found. CheckSubmissionsWorkflow should ensure submissions exist before calling this activity.")

            # Use the form submission
            activity.logger.info(f"Using form submission: {submission['submission_id']}")
            prompt_text = format_artwork_prompt(user_prompt=submission['prompt'])

            # Set metadata for form submission
            submission_id = submission['submission_id']
            submission_email = submission.get('email')

            # Open Claude side panel using the official onboarding page mechanism
            activity.logger.info("Opening Claude side panel...")
            side_panel_page = await open_claude_side_panel(page, context)

            # Navigate to Kid Pix
            activity.logger.info("Navigating to Kid Pix...")
            await page.goto('https://kidpix.claudedraws.com')
            await page.wait_for_load_state('domcontentloaded')

            # Wait for message input and submit prompt
            activity.logger.info("Submitting prompt to Claude...")
            message_input = side_panel_page.locator('textarea[data-test-id="message-input"]')
            await message_input.wait_for(state="visible", timeout=10000)
            await message_input.fill(prompt_text)

            send_button = side_panel_page.locator('button[data-test-id="send-button"]')
            await send_button.click()
            activity.logger.info("Prompt submitted!")

            # Wait for Claude to start working
            activity.logger.info("Waiting for Claude to start working...")
            stop_button = side_panel_page.locator('button[data-test-id="stop-button"]')
            await stop_button.wait_for(state="visible", timeout=30000)

            # Wait for Claude to finish with heartbeats
            activity.logger.info("Claude is working... (sending heartbeats)")
            timeout_ms = 12 * 60 * 1000  # 12 minutes max
            start_time = time.time()

            while True:
                # Send heartbeat to Temporal
                activity.heartbeat()

                # Check if stop button is still visible
                is_visible = await stop_button.is_visible()
                if not is_visible:
                    activity.logger.info("Claude has completed the task!")
                    break

                # Check timeout
                elapsed_ms = (time.time() - start_time) * 1000
                if elapsed_ms > timeout_ms:
                    raise TimeoutError("Claude did not finish within 12 minutes")

                # Wait before next check
                await page.wait_for_timeout(1000)  # Check every second

            # Extract HTML from Claude's final response
            activity.logger.info("Extracting response metadata...")
            last_response = side_panel_page.locator('div.claude-response').last
            response_html = await last_response.inner_html()
            activity.logger.info(f"Extracted {len(response_html)} characters from response")

            # Save the artwork
            activity.logger.info("Saving artwork...")
            downloads_dir = BACKEND_ROOT.parent / "downloads"  # /app/downloads
            downloads_dir.mkdir(exist_ok=True)

            async with page.expect_download() as download_info:
                save_button = page.locator('button#save')
                await save_button.click()

            download = await download_info.value

            # Extract image bytes from data URL (Kid Pix downloads as data:image/png;base64,...)
            # This avoids host vs. container filesystem path issues when using CDP
            url = download.url
            activity.logger.info(f"Download URL type: {url[:50]}...")

            if url.startswith('data:image/png;base64,'):
                # Extract base64 data and decode to bytes
                base64_data = url.split(',', 1)[1]
                image_bytes = base64.b64decode(base64_data)
                activity.logger.info(f"Downloaded {len(image_bytes)} bytes from base64 data URL")
            else:
                raise ValueError(f"Unexpected download URL format: {url[:100]}")

            # Write to container's downloads directory
            timestamp = int(time.time())
            download_path = downloads_dir / f"claudedraws-{timestamp}.png"
            with open(download_path, 'wb') as f:
                f.write(image_bytes)
            activity.logger.info(f"Artwork saved to: {download_path}")

            # Close side panel (after a moment for the livestream viewers to read
            # the title and artist statement)
            await page.wait_for_timeout(4000)
            await side_panel_page.close()

            # Store the tab URL for reconnection (should be https://kidpix.claudedraws.com for Kid Pix)
            tab_url = page.url
            activity.logger.info(f"Storing tab URL for reconnection: {tab_url}")

            # Don't close browser or page - we may need to reconnect later

            return BrowserSessionResult(
                image_path=str(download_path),
                response_html=response_html,
                submission_id=submission_id,
                submission_email=submission_email,
                tab_url=tab_url,
                prompt=prompt_text,
            )
        except Exception:
            # Clean up tab on error to prevent accumulation on retry
            activity.logger.info("Error occurred, closing tab before retry...")
            try:
                await page.close()
                activity.logger.info("✓ Tab closed")
            except Exception as e:
                activity.logger.warning(f"Failed to close tab during cleanup: {e}")
            raise


@activity.defn
async def extract_artwork_metadata(response_html: str) -> Tuple[str, str]:
    """
    Extract artwork title and artist statement from Claude's HTML response using BAML.

    Args:
        response_html: HTML content from Claude for Chrome's final response

    Returns:
        Tuple of (title, artist_statement)
    """
    activity.logger.info("Extracting artwork metadata with BAML...")

    try:
        # Call BAML function to extract structured metadata
        metadata = b.ExtractArtworkMetadata(response_html)

        activity.logger.info(f"✓ Extracted title: {metadata.title}")
        activity.logger.info(f"✓ Extracted artist statement ({len(metadata.artist_statement)} chars)")

        return (metadata.title, metadata.artist_statement)

    except Exception as e:
        activity.logger.error(f"✗ Error extracting metadata: {e}")
        # Return fallback values if extraction fails
        return ("(untitled)", "(no statement found)")


@activity.defn
async def upload_image_to_r2(artwork_id: str, image_path: str) -> str:
    """
    Upload artwork image to R2.

    Args:
        artwork_id: Unique identifier for the artwork (e.g., kidpix-1234567890)
        image_path: Path to the PNG image file

    Returns:
        Public URL of the uploaded image
    """
    activity.logger.info(f"Uploading image for {artwork_id}")

    client = get_r2_client()
    image_path_obj = Path(image_path)

    if not image_path_obj.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    try:
        with open(image_path, "rb") as f:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=f"{artwork_id}.png",
                Body=f,
                ContentType="image/png",
            )

        image_url = f"{R2_PUBLIC_URL}/{artwork_id}.png"
        activity.logger.info(f"✓ Uploaded image: {image_url}")
        return image_url

    except ClientError as e:
        activity.logger.error(f"✗ Error uploading image: {e}")
        raise


@activity.defn
async def insert_artwork_to_d1(artwork_id: str, metadata: Dict) -> None:
    """
    Insert artwork metadata into D1 artworks table.

    Args:
        artwork_id: Unique identifier for the artwork
        metadata: Dictionary containing artwork metadata
    """
    activity.logger.info(f"Inserting artwork {artwork_id} into D1")

    try:
        sql = """
            INSERT OR REPLACE INTO artworks
            (id, title, artist_statement, image_url, submission_id, created_at, video_url, prompt, autogenerated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = [
            artwork_id,
            metadata.get("title", ""),
            metadata.get("artistStatement"),
            metadata["imageUrl"],
            metadata.get("submissionId"),
            metadata["createdAt"],
            metadata.get("videoUrl"),
            metadata.get("prompt"),
            1 if metadata.get("autogenerated", False) else 0,
        ]

        await query_d1(sql, params)
        activity.logger.info(f"✓ Inserted artwork into D1: {artwork_id}")

    except Exception as e:
        activity.logger.error(f"✗ Error inserting artwork into D1: {e}")
        raise


@activity.defn
async def update_submission_status(
    submission_id: str,
    status: str,
    artwork_id: Optional[str] = None,
    error_message: Optional[str] = None
) -> None:
    """
    Update the status of a submission in D1.

    Args:
        submission_id: ID of the submission to update
        status: New status (pending/processing/completed/failed)
        artwork_id: ID of the completed artwork (for completed status)
        error_message: Error message (for failed status)
    """
    activity.logger.info(f"Updating submission {submission_id} to status: {status}")

    try:
        if status == "completed":
            await query_d1(
                "UPDATE submissions SET status = ?, completed_at = ?, artwork_id = ? WHERE id = ?",
                [status, datetime.now(timezone.utc).isoformat(), artwork_id, submission_id]
            )
        elif status == "failed":
            await query_d1(
                "UPDATE submissions SET status = ?, error_message = ? WHERE id = ?",
                [status, error_message, submission_id]
            )
        else:
            await query_d1(
                "UPDATE submissions SET status = ? WHERE id = ?",
                [status, submission_id]
            )

        activity.logger.info(f"✓ Updated submission status to: {status}")

    except Exception as e:
        activity.logger.error(f"✗ Error updating submission status: {e}")
        raise


@activity.defn
async def send_email_notification(
    email: str,
    artwork_id: str,
    artwork_title: str,
    gallery_url: str
) -> None:
    """
    Send email notification via Resend when artwork is complete.

    Args:
        email: Recipient email address
        artwork_id: ID of the completed artwork
        artwork_title: Title of the artwork
        gallery_url: URL to view the artwork in the gallery
    """
    activity.logger.info(f"Sending email notification to {email}")

    try:
        # Configure Resend API key
        resend.api_key = RESEND_API_KEY

        # Build email parameters
        params: resend.Emails.SendParams = {
            "from": RESEND_FROM_EMAIL,
            "to": [email],
            "subject": f'Your Claude Draws artwork "{artwork_title}" is ready!',
            "html": f"""
            <html>
                <body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #882FF6;">Your artwork is ready!</h1>
                    <p>Claude Draws has completed your artwork request:</p>
                    <h2 style="color: #333;">"{artwork_title}"</h2>
                    <p>
                        <a href="{gallery_url}" style="display: inline-block; background-color: #882FF6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold;">
                            View Your Artwork
                        </a>
                    </p>
                    <p style="color: #666; font-size: 14px; margin-top: 40px;">
                        This artwork was created by Claude for Chrome using Kid Pix at <a href="https://claudedraws.com">claudedraws.com</a>
                    </p>
                </body>
            </html>
            """,
        }

        # Send email via Resend SDK
        email_result = resend.Emails.send(params)
        activity.logger.info(f"✓ Email sent successfully to {email}: {email_result}")

    except Exception as e:
        activity.logger.error(f"✗ Error sending email: {e}")
        # Don't raise - we don't want to fail the workflow if email fails
        # The artwork is still successfully created


@activity.defn
async def cleanup_tab_activity(cdp_url: str, tab_url: str) -> None:
    """
    Close a tab to prevent accumulation in continuous mode.

    This is used for autogenerated artworks where we don't send user notifications,
    but still need to clean up the tab.

    Args:
        cdp_url: Chrome DevTools Protocol URL
        tab_url: URL of the tab to close (e.g., https://kidpix.claudedraws.com)
    """
    activity.logger.info("Cleaning up tab...")

    async with async_playwright() as p:
        # Reconnect to Chrome
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]

        # Try to find the tab by URL
        activity.logger.info(f"Looking for tab with URL: {tab_url}")
        page = None
        for p_candidate in context.pages:
            if p_candidate.url == tab_url:
                page = p_candidate
                activity.logger.info(f"✓ Found tab at {tab_url}")
                break

        # Close the tab if found
        if page:
            try:
                await page.close()
                activity.logger.info("✓ Tab closed")
            except Exception as e:
                activity.logger.warning(f"Failed to close tab during cleanup: {e}")
        else:
            activity.logger.warning(f"⚠ Could not find tab at {tab_url} to close")


# ============================================================================
# OBS Control Activities
# ============================================================================


@activity.defn
async def switch_obs_scene(scene_name: str) -> None:
    """
    Switch OBS to the specified scene.

    Args:
        scene_name: Name of the scene to switch to

    Raises:
        OBSWebSocketError: If scene switch fails (workflow will fail)
    """
    activity.logger.info(f"Switching OBS scene to: {scene_name}")

    try:
        async with OBSWebSocketClient(
            url=OBS_WEBSOCKET_URL,
            password=OBS_WEBSOCKET_PASSWORD,
        ) as obs:
            await obs.switch_scene(scene_name)
            activity.logger.info(f"✓ Successfully switched to scene: {scene_name}")

    except OBSWebSocketError as e:
        activity.logger.error(f"✗ Failed to switch OBS scene: {e}")
        raise
    except Exception as e:
        activity.logger.error(f"✗ Unexpected error switching OBS scene: {e}")
        raise OBSWebSocketError(f"Unexpected error: {e}")


@activity.defn
async def update_countdown_text(seconds: int) -> None:
    """
    Update the OBS countdown text source with remaining seconds.

    Formats the countdown as "Next check: M:SS"

    Args:
        seconds: Number of seconds remaining

    Raises:
        OBSWebSocketError: If text update fails (workflow will fail)
    """
    minutes = seconds // 60
    secs = seconds % 60
    countdown_text = f"Next check: {minutes}:{secs:02d}"

    try:
        async with OBSWebSocketClient(
            url=OBS_WEBSOCKET_URL,
            password=OBS_WEBSOCKET_PASSWORD,
        ) as obs:
            await obs.update_text_source(OBS_COUNTDOWN_TEXT_SOURCE, countdown_text)
            activity.logger.debug(f"Updated countdown: {countdown_text}")

    except OBSWebSocketError as e:
        activity.logger.error(f"✗ Failed to update countdown text: {e}")
        raise
    except Exception as e:
        activity.logger.error(f"✗ Unexpected error updating countdown text: {e}")
        raise OBSWebSocketError(f"Unexpected error: {e}")


@activity.defn
async def ensure_obs_streaming() -> None:
    """
    Ensure OBS is streaming, starting the stream if necessary.

    This is useful after PC wake from sleep, where OBS may not automatically
    resume streaming even though the application is still running.

    Raises:
        OBSWebSocketError: If stream status check or start fails (workflow will fail)
    """
    activity.logger.info("Checking OBS streaming status...")

    try:
        async with OBSWebSocketClient(
            url=OBS_WEBSOCKET_URL,
            password=OBS_WEBSOCKET_PASSWORD,
        ) as obs:
            is_streaming = await obs.get_stream_status()

            if is_streaming:
                activity.logger.info("✓ OBS is already streaming")
            else:
                activity.logger.info("OBS is not streaming - starting stream...")
                await obs.start_stream()
                activity.logger.info("✓ OBS stream started successfully")

    except OBSWebSocketError as e:
        activity.logger.error(f"✗ Failed to ensure OBS streaming: {e}")
        raise
    except Exception as e:
        activity.logger.error(f"✗ Unexpected error ensuring OBS streaming: {e}")
        raise OBSWebSocketError(f"Unexpected error: {e}")


@activity.defn
async def check_inactivity_and_stop_streaming(inactivity_threshold_minutes: int = 15) -> bool:
    """
    Check for inactivity and stop OBS streaming if system has been idle.

    This prepares the system for sleep by stopping OBS streaming, which
    prevents Windows sleep from being blocked.

    Inactivity is determined by:
    1. No submissions with status = 'processing'
    2. Time since last completed artwork > threshold (default 15 minutes)

    Args:
        inactivity_threshold_minutes: Minutes of inactivity before stopping stream

    Returns:
        bool: True if streaming was stopped, False otherwise

    Raises:
        OBSWebSocketError: If OBS operations fail (workflow will fail)
    """
    activity.logger.info(f"Checking for inactivity (threshold: {inactivity_threshold_minutes} minutes)...")

    try:
        # Check 1: Are there any submissions currently being processed?
        activity.logger.info("Checking for in-progress submissions...")
        processing_result = await query_d1(
            "SELECT COUNT(*) as count FROM submissions WHERE status = 'processing'"
        )
        processing_count = processing_result.get("result", [{}])[0].get("results", [{}])[0].get("count", 0)

        if processing_count > 0:
            activity.logger.info(f"Found {processing_count} submission(s) in progress - not stopping stream")
            return False

        activity.logger.info("No submissions in progress")

        # Check 2: When was the last artwork completed?
        activity.logger.info("Checking time since last completed artwork...")
        completed_result = await query_d1(
            "SELECT MAX(completed_at) as last_completed FROM submissions WHERE status = 'completed'"
        )
        last_completed = completed_result.get("result", [{}])[0].get("results", [{}])[0].get("last_completed")

        if not last_completed:
            activity.logger.info("No completed artworks found - not stopping stream")
            return False

        # Parse ISO 8601 timestamp and calculate minutes since completion
        from datetime import datetime, timezone
        last_completed_time = datetime.fromisoformat(last_completed.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        minutes_since_completion = (now - last_completed_time).total_seconds() / 60

        activity.logger.info(f"Last artwork completed {minutes_since_completion:.1f} minutes ago")

        if minutes_since_completion < inactivity_threshold_minutes:
            activity.logger.info(f"Below inactivity threshold - not stopping stream")
            return False

        # Conditions met - stop OBS streaming
        activity.logger.info("Inactivity threshold exceeded - stopping OBS stream...")

        async with OBSWebSocketClient(
            url=OBS_WEBSOCKET_URL,
            password=OBS_WEBSOCKET_PASSWORD,
        ) as obs:
            # Check if currently streaming
            is_streaming = await obs.get_stream_status()

            if is_streaming:
                await obs.stop_stream()
                activity.logger.info("✓ OBS stream stopped successfully")
                return True
            else:
                activity.logger.info("OBS is not currently streaming - no action needed")
                return False

    except OBSWebSocketError as e:
        activity.logger.error(f"✗ Failed to check inactivity and stop streaming: {e}")
        raise
    except Exception as e:
        activity.logger.error(f"✗ Unexpected error checking inactivity: {e}")
        raise


@activity.defn
async def start_obs_recording() -> None:
    """
    Start OBS recording for the current artwork creation process.

    Sets the recording directory to RECORDINGS_DIR and starts recording.
    Includes safety checks to ensure OBS is not already recording.

    Raises:
        OBSWebSocketError: If recording start fails (workflow will fail)
    """
    activity.logger.info("Starting OBS recording for artwork creation...")

    try:
        async with OBSWebSocketClient(
            url=OBS_WEBSOCKET_URL,
            password=OBS_WEBSOCKET_PASSWORD,
        ) as obs:
            # Set recording directory (OBS expects host OS path)
            # The RECORDINGS_DIR path is the container path (/app/downloads/recordings)
            # We need to convert it to the host OS path
            # Since downloads is mounted as a volume, the host path corresponds to the container path

            # OBS runs on the host OS and needs the host OS path to the recordings directory
            # The container path /app/downloads/recordings maps to the host path
            # We use PROJECT_HOST_DIR and append the relative path
            project_host_dir = os.getenv(
                "PROJECT_HOST_DIR",
                str(RECORDINGS_DIR.parent.parent)  # Fallback to container path for dev
            )
            # Use appropriate path class for host OS (Windows vs Unix)
            PathClass = get_host_path_class(project_host_dir)
            host_recording_dir = str(PathClass(project_host_dir) / "downloads" / "recordings")

            activity.logger.info(f"Setting OBS recording directory to: {host_recording_dir}")
            await obs.set_record_directory(host_recording_dir)

            # Start recording (includes safety check for existing recordings)
            await obs.start_record()
            activity.logger.info("✓ OBS recording started successfully")

    except OBSWebSocketError as e:
        activity.logger.error(f"✗ Failed to start OBS recording: {e}")
        raise
    except Exception as e:
        activity.logger.error(f"✗ Unexpected error starting OBS recording: {e}")
        raise OBSWebSocketError(f"Unexpected error: {e}")


@activity.defn
async def stop_obs_recording() -> Optional[str]:
    """
    Stop OBS recording and return the path to the recorded video file.

    Waits for the RecordStateChanged event to capture the output file path.
    The returned path will be a host OS path that needs to be converted
    to the container path for further processing.

    Returns:
        str: Absolute path to the recorded video file (container path),
             or None if path could not be determined

    Raises:
        OBSWebSocketError: If recording stop fails (workflow will fail)
    """
    activity.logger.info("Stopping OBS recording...")

    try:
        async with OBSWebSocketClient(
            url=OBS_WEBSOCKET_URL,
            password=OBS_WEBSOCKET_PASSWORD,
            timeout=30.0,  # Longer timeout for recording to finalize
        ) as obs:
            # Stop recording and wait for the file path
            host_path = await obs.stop_record(timeout=30.0)

            if not host_path:
                activity.logger.error("✗ Failed to get recording file path from OBS")
                return None

            activity.logger.info(f"✓ Recording stopped. Host OS path: {host_path}")

            # Convert host OS path to container path
            # OBS returns a host OS path like:
            #   Windows: C:\Users\...\claude-draws\downloads\recordings\2025-11-04 14-30-45.mkv
            #   macOS: /Users/.../claude-draws/downloads/recordings/2025-11-04 14-30-45.mkv
            # We need to convert it to: /app/downloads/recordings/2025-11-04 14-30-45.mkv

            # Extract just the filename
            filename = Path(host_path).name
            container_path = RECORDINGS_DIR / filename

            activity.logger.info(f"Container path: {container_path}")

            # Verify the file exists (it should be accessible via the mounted volume)
            if not container_path.exists():
                activity.logger.warning(f"⚠ Recording file not found at {container_path}. Waiting 5 seconds...")
                await asyncio.sleep(5)  # Give file system time to sync

                if not container_path.exists():
                    activity.logger.error(f"✗ Recording file still not found at {container_path}")
                    return None

            activity.logger.info(f"✓ Recording file confirmed at: {container_path}")
            return str(container_path)

    except OBSWebSocketError as e:
        activity.logger.error(f"✗ Failed to stop OBS recording: {e}")
        raise
    except Exception as e:
        activity.logger.error(f"✗ Unexpected error stopping OBS recording: {e}")
        raise OBSWebSocketError(f"Unexpected error: {e}")


@activity.defn
async def rotate_screensaver_video(last_video_index: int = -1) -> int:
    """
    Rotate to the next screensaver video in the After Dark collection.

    Uses round-robin selection to cycle through all available screensaver videos.
    Updates the OBS media source to display the selected video.

    Args:
        last_video_index: Index of the last video shown (-1 for first time)

    Returns:
        int: Index of the video that was just set (to be passed on next call)

    Raises:
        OBSWebSocketError: If media source update fails (workflow will fail)
    """
    activity.logger.info("Rotating screensaver video...")

    try:
        # Calculate next video index (round-robin)
        next_index = (last_video_index + 1) % len(SCREENSAVER_VIDEOS)
        selected_video = SCREENSAVER_VIDEOS[next_index]

        activity.logger.info(f"Selected screensaver video [{next_index + 1}/{len(SCREENSAVER_VIDEOS)}]: {selected_video}")

        # Build host OS path: PROJECT_HOST_DIR/obs/{filename}
        project_host_dir = os.getenv(
            "PROJECT_HOST_DIR",
            str(BACKEND_ROOT.parent)  # Fallback to container path for dev
        )
        # Use appropriate path class for host OS (Windows vs Unix)
        PathClass = get_host_path_class(project_host_dir)
        video_host_path = str(PathClass(project_host_dir) / "obs" / selected_video)

        activity.logger.info(f"Video host path: {video_host_path}")

        # Update OBS media source
        async with OBSWebSocketClient(
            url=OBS_WEBSOCKET_URL,
            password=OBS_WEBSOCKET_PASSWORD,
        ) as obs:
            await obs.update_media_source(
                input_name=OBS_SCREENSAVER_MEDIA_SOURCE,
                file_path=video_host_path,
                overlay=True  # Only update file path, preserve other settings
            )

        activity.logger.info(f"✓ Screensaver video updated to: {selected_video}")
        return next_index

    except OBSWebSocketError as e:
        activity.logger.error(f"✗ Failed to rotate screensaver video: {e}")
        raise
    except Exception as e:
        activity.logger.error(f"✗ Unexpected error rotating screensaver video: {e}")
        raise OBSWebSocketError(f"Unexpected error: {e}")


@activity.defn
async def compress_video(video_path: str) -> str:
    """
    Compress video file using PyAV (H.264 + AAC).

    Converts OBS recordings (.mov, .mkv) to compressed H.264 MP4:
    - Video: H.264 codec, CRF 23, medium preset, preserves original resolution
    - Audio: AAC codec, 128 kbps, stereo
    - Target: ~70-75% file size reduction

    Args:
        video_path: Path to input video file (e.g., "/app/downloads/recordings/video.mov")

    Returns:
        str: Path to compressed output file (e.g., "/app/downloads/recordings/video.mp4")

    Raises:
        FileNotFoundError: If input file doesn't exist
        Exception: If compression fails (workflow will fail)
    """
    import av

    activity.logger.info(f"Compressing video: {video_path}")

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Output path: replace extension with .mp4
    output_path = video_path_obj.with_suffix('.mp4')

    activity.logger.info(f"Output path: {output_path}")

    # Get input file size for logging
    input_size_mb = video_path_obj.stat().st_size / (1024 * 1024)
    activity.logger.info(f"Input file size: {input_size_mb:.2f} MB")

    try:
        # Open input container
        with av.open(str(video_path)) as input_container:
            # Get input streams
            input_video = input_container.streams.video[0]
            input_audio = input_container.streams.audio[0] if input_container.streams.audio else None

            activity.logger.info(f"Input video: {input_video.codec_context.name}, "
                               f"{input_video.width}x{input_video.height}, "
                               f"{input_video.average_rate} fps")
            if input_audio:
                activity.logger.info(f"Input audio: {input_audio.codec_context.name}, "
                                   f"{input_audio.rate} Hz, {input_audio.channels} channels")

            # Open output container
            with av.open(str(output_path), 'w') as output_container:
                # Configure output video stream (H.264)
                output_video = output_container.add_stream('libx264', rate=input_video.average_rate)
                output_video.width = input_video.width
                output_video.height = input_video.height
                output_video.pix_fmt = 'yuv420p'

                # H.264 encoding options for screen recording compression
                # Optimized for text legibility in Kid Pix browser UI
                output_video.codec_context.options = {
                    'crf': '20',           # High quality for text clarity (lower=better, default=23)
                    'preset': 'medium',    # Balanced encoding speed
                    'tune': 'animation',   # Optimized for screen content with flat color areas
                }

                activity.logger.info(f"Output video configured: H.264, {output_video.width}x{output_video.height}, CRF 20, medium preset, tune=animation")

                # Configure output audio stream (AAC)
                output_audio = None
                if input_audio:
                    output_audio = output_container.add_stream('aac', rate=44100, layout='stereo')
                    output_audio.codec_context.bit_rate = 128000  # 128 kbps
                    activity.logger.info("Output audio configured: AAC, 44.1 kHz, stereo, 128 kbps")

                # Transcode video frames
                activity.logger.info("Transcoding video...")
                frame_count = 0
                for packet in input_container.demux(input_video):
                    for frame in packet.decode():
                        # Reformat frame to output pixel format
                        frame = frame.reformat(format=output_video.pix_fmt)

                        # Encode and mux
                        for encoded_packet in output_video.encode(frame):
                            output_container.mux(encoded_packet)

                        frame_count += 1
                        if frame_count % 100 == 0:
                            activity.logger.debug(f"Processed {frame_count} video frames...")

                activity.logger.info(f"✓ Transcoded {frame_count} video frames")

                # Transcode audio frames
                if input_audio and output_audio:
                    activity.logger.info("Transcoding audio...")

                    # Create audio resampler to convert to output format
                    resampler = av.AudioResampler(
                        format=output_audio.format.name,
                        layout='stereo',
                        rate=44100
                    )

                    audio_frame_count = 0
                    for packet in input_container.demux(input_audio):
                        for frame in packet.decode():
                            # Resample to match output stream configuration
                            resampled_frames = resampler.resample(frame)

                            for resampled_frame in resampled_frames:
                                resampled_frame.pts = None  # Let encoder assign timestamps

                                for encoded_packet in output_audio.encode(resampled_frame):
                                    output_container.mux(encoded_packet)

                                audio_frame_count += 1

                    activity.logger.info(f"✓ Transcoded {audio_frame_count} audio frames")

                    # Flush audio encoder
                    for encoded_packet in output_audio.encode():
                        output_container.mux(encoded_packet)

                # Flush video encoder
                for encoded_packet in output_video.encode():
                    output_container.mux(encoded_packet)

        # Verify output file exists
        if not output_path.exists():
            raise FileNotFoundError(f"Compressed file not created: {output_path}")

        # Get output file size and calculate reduction
        output_size_mb = output_path.stat().st_size / (1024 * 1024)
        reduction_pct = ((input_size_mb - output_size_mb) / input_size_mb) * 100

        activity.logger.info(f"✓ Compression complete!")
        activity.logger.info(f"  Output size: {output_size_mb:.2f} MB")
        activity.logger.info(f"  Reduction: {reduction_pct:.1f}%")

        # Delete original uncompressed file
        try:
            video_path_obj.unlink()
            activity.logger.info(f"✓ Deleted original file: {video_path}")
        except Exception as e:
            activity.logger.warning(f"⚠ Failed to delete original file: {e}")

        return str(output_path)

    except Exception as e:
        activity.logger.error(f"✗ Error compressing video: {e}")
        raise


@activity.defn
async def upload_video_to_r2(artwork_id: str, video_path: str) -> str:
    """
    Upload artwork creation video to Cloudflare R2.

    Args:
        artwork_id: Unique identifier for the artwork (e.g., "claudedraws-1730736645")
        video_path: Absolute path to the video file (e.g., "/app/downloads/recordings/2025-11-04 14-30-45.mkv")

    Returns:
        str: Public URL of the uploaded video

    Raises:
        Exception: If upload fails (workflow will fail)
    """
    activity.logger.info(f"Uploading video to R2: {video_path}")

    try:
        client = get_r2_client()
        video_path_obj = Path(video_path)

        if not video_path_obj.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Get file extension (.mkv, .mp4, etc.)
        ext = video_path_obj.suffix.lower()

        # Determine content type
        content_type_map = {
            ".mkv": "video/x-matroska",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
        }
        content_type = content_type_map.get(ext, "video/x-matroska")

        # Upload to R2 with artwork ID as key
        r2_key = f"{artwork_id}{ext}"

        activity.logger.info(f"Uploading to R2 bucket '{R2_BUCKET_NAME}' with key '{r2_key}'...")

        with open(video_path, "rb") as f:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=r2_key,
                Body=f,
                ContentType=content_type,
            )

        video_url = f"{R2_PUBLIC_URL}/{r2_key}"
        activity.logger.info(f"✓ Video uploaded successfully: {video_url}")

        # Clean up local video file after successful upload
        try:
            video_path_obj.unlink()
            activity.logger.info(f"✓ Local video file deleted: {video_path}")
        except Exception as e:
            activity.logger.warning(f"⚠ Failed to delete local video file: {e}")

        return video_url

    except ClientError as e:
        activity.logger.error(f"✗ R2 upload failed: {e}")
        raise
    except Exception as e:
        activity.logger.error(f"✗ Unexpected error uploading video: {e}")
        raise


@activity.defn
async def check_for_pending_submissions() -> Optional[Dict]:
    """
    Check D1 database for pending submissions.

    Returns:
        Dict containing submission data if found, None otherwise
        Keys: id, prompt, email (optional), created_at
    """
    activity.logger.info("Checking for pending submissions in D1...")

    try:
        result = await query_d1(
            """
            SELECT id, prompt, email, created_at
            FROM submissions
            WHERE status = 'pending'
            ORDER BY upvote_count DESC, created_at ASC
            LIMIT 1
            """
        )

        # Parse D1 HTTP API response structure: result -> result[0] -> results
        results = result.get("result", [{}])[0].get("results", [])
        if results and len(results) > 0:
            submission = results[0]
            activity.logger.info(f"✓ Found pending submission: {submission['id']}")
            return submission
        else:
            activity.logger.info("No pending submissions found")
            return None

    except Exception as e:
        activity.logger.error(f"✗ Error checking for submissions: {e}")
        raise


@activity.defn
async def visit_gallery_activity(cdp_url: str) -> None:
    """
    Visit the Claude Draws gallery homepage for livestream viewers.

    Shows the gallery website briefly so viewers can see completed artworks
    and decide to visit in their own browser.

    Args:
        cdp_url: Chrome DevTools Protocol URL
    """
    activity.logger.info("Navigating to Claude Draws gallery...")

    async with async_playwright() as p:
        # Connect to the existing browser via CDP
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]

        # Create a new page for the gallery
        page = await context.new_page()

        try:
            # Navigate to gallery
            await page.goto('https://claudedraws.com')
            await page.wait_for_load_state('domcontentloaded')

            # Show gallery for 5 seconds
            activity.logger.info("Displaying gallery for 5 seconds...")
            await page.wait_for_timeout(5000)
            activity.logger.info("✓ Gallery visit complete")

        finally:
            # Close the gallery page
            await page.close()
