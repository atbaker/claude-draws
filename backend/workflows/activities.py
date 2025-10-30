"""Temporal activities for Claude Draws artwork processing."""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
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

# Paths
BACKEND_ROOT = Path(__file__).parent.parent  # /app/backend
GALLERY_DIR = BACKEND_ROOT.parent / "gallery"  # /app/gallery
GALLERY_METADATA_PATH = GALLERY_DIR / "src" / "lib" / "gallery-metadata.json"


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
        # Query D1 for pending submissions, ordered by created_at
        result = await query_d1(
            "SELECT id, prompt, email FROM submissions WHERE status = ? ORDER BY created_at ASC LIMIT 1",
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


def generate_autogenerated_prompt() -> str:
    """
    Generate a creative Kid Pix prompt using BAML.

    Returns:
        str: Generated prompt text
    """
    activity.logger.info("Generating autogenerated prompt with BAML...")

    # Call BAML function to generate prompt
    result = b.GenerateKidPixPrompt()

    activity.logger.info(f"✓ Generated prompt: {result.prompt}")
    return result.prompt


def format_artwork_prompt(
    user_prompt: Optional[str] = None,
    autogenerated_prompt: Optional[str] = None,
) -> str:
    """
    Format an artwork prompt for Claude using Jinja2 templates.

    Handles both user-submitted and autogenerated prompts.

    Args:
        user_prompt: User-submitted prompt text (for form submissions)
        autogenerated_prompt: Generated prompt text (for autogenerated mode)

    Returns:
        str: Formatted prompt ready for Claude
    """
    # Load shared Kid Pix instructions
    kidpix_instructions_path = BACKEND_ROOT / "claudedraw" / "kidpix_instructions.md"
    with open(kidpix_instructions_path, 'r') as f:
        kidpix_instructions = f.read()

    if autogenerated_prompt:
        # Use autogenerated template
        template_path = BACKEND_ROOT / "claudedraw" / "autogenerated_template.md"
        with open(template_path, 'r') as f:
            template_text = f.read()

        template = Template(template_text)
        return template.render(
            autogenerated_prompt=autogenerated_prompt,
            kidpix_instructions=kidpix_instructions,
        )
    else:
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
async def browser_session_activity(cdp_url: str) -> BrowserSessionResult:
    """
    Long-running activity that handles the full browser automation session.

    This activity:
    1. Retrieves a pending submission from Cloudflare D1 database
    2. Opens Claude side panel
    3. Submits the formatted prompt
    4. Waits for Claude to complete (with heartbeats)
    5. Downloads the artwork PNG

    Args:
        cdp_url: Chrome DevTools Protocol URL

    Returns:
        BrowserSessionResult with paths and metadata
    """
    activity.logger.info("Starting browser session activity...")

    async with async_playwright() as p:
        # Connect to the existing browser via CDP
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]

        # Always create a new tab for this workflow run
        # This ensures clean isolation and avoids interfering with other tabs (e.g., background music)
        page = await context.new_page()
        activity.logger.info("Created new tab for this workflow run")

        try:
            # Visit gallery first for livestream viewers
            await visit_gallery(page)

            # Try to get a form submission from D1
            submission = await get_next_submission(page)

            # Determine if this is from a form submission or autogenerated
            if submission is None:
                # No form submissions found - generate our own prompt
                activity.logger.info("No form submissions available - generating autogenerated prompt")
                autogenerated_prompt_text = generate_autogenerated_prompt()
                prompt_text = format_artwork_prompt(autogenerated_prompt=autogenerated_prompt_text)

                # Set metadata for autogenerated artwork
                submission_id = None
                submission_email = None
            else:
                # Form submission found - use it
                activity.logger.info(f"Using form submission: {submission['submission_id']}")
                prompt_text = format_artwork_prompt(
                    user_prompt=submission['prompt'],
                )

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

            # Close side panel
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
async def upload_metadata_to_r2(artwork_id: str, metadata: Dict) -> None:
    """
    Upload artwork metadata JSON to R2.

    Args:
        artwork_id: Unique identifier for the artwork
        metadata: Dictionary containing artwork metadata
    """
    activity.logger.info(f"Uploading metadata for {artwork_id}")

    client = get_r2_client()

    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=f"{artwork_id}.json",
            Body=json.dumps(metadata, indent=2),
            ContentType="application/json",
        )

        activity.logger.info(f"✓ Uploaded metadata: {artwork_id}.json")

    except ClientError as e:
        activity.logger.error(f"✗ Error uploading metadata: {e}")
        raise


@activity.defn
async def append_to_gallery_metadata(artwork_id: str, image_url: str, metadata: Dict) -> None:
    """
    Append new artwork to local gallery metadata file.

    Args:
        artwork_id: Unique identifier for the artwork
        image_url: Public URL of the artwork image
        metadata: Dictionary containing artwork metadata
    """
    activity.logger.info(f"Appending {artwork_id} to gallery metadata")

    # Ensure directory exists
    GALLERY_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Handle case where a directory exists at the file path
    if GALLERY_METADATA_PATH.exists() and GALLERY_METADATA_PATH.is_dir():
        activity.logger.warning(f"Directory exists at {GALLERY_METADATA_PATH}, removing it")
        shutil.rmtree(GALLERY_METADATA_PATH)

    # Load existing gallery metadata or create new
    if GALLERY_METADATA_PATH.is_file():
        with open(GALLERY_METADATA_PATH, "r") as f:
            gallery_metadata = json.load(f)
    else:
        activity.logger.info("No existing gallery metadata file, creating new one")
        gallery_metadata = {"artworks": [], "lastUpdated": None}

    # Check if artwork already exists
    existing_ids = {artwork["id"] for artwork in gallery_metadata["artworks"]}
    if artwork_id in existing_ids:
        activity.logger.warning(f"⚠ Artwork {artwork_id} already exists, skipping")
        return

    # Construct full artwork entry
    artwork_entry = {
        "id": metadata["id"],
        "imageUrl": image_url,
        "title": metadata["title"],
        "artistStatement": metadata.get("artistStatement", ""),
        "submissionId": metadata.get("submissionId", None),
        "createdAt": metadata["createdAt"],
        "videoUrl": metadata.get("videoUrl", None),
        "prompt": metadata.get("prompt", ""),
    }

    # Append new artwork
    gallery_metadata["artworks"].append(artwork_entry)
    gallery_metadata["lastUpdated"] = datetime.now(timezone.utc).isoformat()

    # Save updated metadata
    with open(GALLERY_METADATA_PATH, "w") as f:
        json.dump(gallery_metadata, f, indent=2)

    activity.logger.info(f"✓ Appended {artwork_id} to gallery metadata")


@activity.defn
async def rebuild_static_site() -> None:
    """
    Rebuild the SvelteKit static site using npm.

    Runs `npm run build` in the gallery directory asynchronously.
    """
    activity.logger.info("Rebuilding static site...")

    try:
        # Use async subprocess to avoid blocking the event loop
        process = await asyncio.create_subprocess_exec(
            "npm", "run", "build",
            cwd=str(GALLERY_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for process to complete with timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60.0  # 1 minute timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            activity.logger.error("✗ Build timed out after 1 minute")
            raise

        # Check return code
        if process.returncode != 0:
            activity.logger.error(f"✗ Build failed with exit code {process.returncode}")
            activity.logger.error(f"stdout: {stdout.decode()}")
            activity.logger.error(f"stderr: {stderr.decode()}")
            raise RuntimeError(f"Build failed with exit code {process.returncode}")

        activity.logger.info("✓ Build completed successfully")
        activity.logger.debug(f"Build output: {stdout.decode()}")

    except Exception as e:
        if not isinstance(e, (asyncio.TimeoutError, RuntimeError)):
            activity.logger.error(f"✗ Unexpected error during build: {e}")
        raise


@activity.defn
async def deploy_to_cloudflare() -> str:
    """
    Deploy the built site to Cloudflare Workers using wrangler.

    Runs `wrangler deploy` in the gallery directory asynchronously.

    Returns:
        Gallery URL (e.g., https://claudedraws.com)
    """
    activity.logger.info("Deploying to Cloudflare Workers...")

    try:
        # Use async subprocess to avoid blocking the event loop
        process = await asyncio.create_subprocess_exec(
            "npx", "wrangler", "deploy",
            cwd=str(GALLERY_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for process to complete with timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60.0  # 1 minute timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            activity.logger.error("✗ Deployment timed out after 1 minute")
            raise

        # Check return code
        if process.returncode != 0:
            activity.logger.error(f"✗ Deployment failed with exit code {process.returncode}")
            activity.logger.error(f"stdout: {stdout.decode()}")
            activity.logger.error(f"stderr: {stderr.decode()}")
            raise RuntimeError(f"Deployment failed with exit code {process.returncode}")

        activity.logger.info("✓ Deployment completed successfully")
        activity.logger.debug(f"Deploy output: {stdout.decode()}")

        # Return the gallery URL (customize based on your domain)
        gallery_url = "https://claudedraws.com"
        return gallery_url

    except Exception as e:
        if not isinstance(e, (asyncio.TimeoutError, RuntimeError)):
            activity.logger.error(f"✗ Unexpected error during deployment: {e}")
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


@activity.defn
async def start_gallery_deployment_workflow(artwork_id: str) -> None:
    """
    Start a standalone gallery deployment workflow.

    This activity starts an independent DeployGalleryWorkflow that runs
    in parallel with the main CreateArtworkWorkflow, allowing the parent
    to continue with other activities (like sending email notifications) while
    the gallery builds and deploys in the background.

    Args:
        artwork_id: ID of the artwork being deployed
    """
    activity.logger.info(f"Starting gallery deployment workflow for {artwork_id}...")

    try:
        # Get Temporal client
        client = await Client.connect(TEMPORAL_HOST)

        # Start independent workflow
        workflow_id = f"deploy-gallery-{artwork_id}"

        await client.start_workflow(
            "DeployGalleryWorkflow",
            args=[artwork_id],
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        activity.logger.info(f"✓ Started gallery deployment workflow: {workflow_id}")

    except Exception as e:
        activity.logger.error(f"✗ Error starting gallery deployment workflow: {e}")
        # Re-raise to trigger Temporal retry
        raise


@activity.defn
async def schedule_next_workflow(cdp_url: str, continuous: bool) -> None:
    """
    Schedule the next workflow run for continuous operation.

    This activity is only called when continuous=True, so we always apply
    the infinite retry policy here.

    Args:
        cdp_url: Chrome DevTools Protocol URL to pass to next workflow
        continuous: Whether to continue scheduling (should always be True when called)
    """
    activity.logger.info("Scheduling next workflow run...")

    try:
        # Get Temporal client
        client = await Client.connect(TEMPORAL_HOST)

        # Start new workflow
        timestamp = int(time.time())
        workflow_id = f"claude-draws-{timestamp}"

        # Apply infinite retry policy for continuous mode
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=10),
            maximum_interval=timedelta(minutes=3),
            backoff_coefficient=2.0,
            maximum_attempts=0,  # Infinite retries
        )

        await client.start_workflow(
            "CreateArtworkWorkflow",
            args=[cdp_url, continuous],
            id=workflow_id,
            task_queue=TASK_QUEUE,
            retry_policy=retry_policy,
        )

        activity.logger.info(f"✓ Scheduled next workflow: {workflow_id}")

    except Exception as e:
        # Always try to schedule next run even if something fails
        activity.logger.error(f"✗ Error scheduling next workflow: {e}")
        # Re-raise to trigger Temporal retry
        raise
