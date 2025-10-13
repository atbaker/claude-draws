"""Browser automation using Playwright."""

import asyncio
import os
import sys
import time
from pathlib import Path

# IMPORTANT: Set this environment variable BEFORE importing playwright
# This enables the underlying Node.js server to attach to Chrome targets of type "other"
# (such as extension side panels) as if they were regular pages
os.environ['PW_CHROMIUM_ATTACH_TO_OTHER'] = '1'

import pyautogui
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from temporalio.client import Client

# Add parent directory to path so we can import workflows
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows.process_artwork import ProcessArtworkWorkflow

# Load environment variables
load_dotenv()

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "claude-draws-queue"

# TODO: Make this an environment variable - Anthropic would probably prefer to keep it secret
CLAUDE_EXTENSION_ID = "fcoeoabgfenejglbffodgkkbkcdhcgfn"


def submit_claude_prompt(cdp_url: str, prompt: str, reddit_url: str | None) -> str:
    """
    Connect to a Chrome browser via CDP and submit a prompt to Claude for Chrome.

    Args:
        cdp_url: Chrome DevTools Protocol endpoint URL
        prompt: The prompt to send to Claude
        reddit_url: URL of Reddit post that inspired this artwork (optional)

    Returns:
        Gallery URL where the artwork can be viewed
    """
    with sync_playwright() as p:
        # Connect to the existing browser via CDP
        browser = p.chromium.connect_over_cdp(cdp_url)

        # Get the default context (the browser's existing session)
        context = browser.contexts[0]

        # Create a new page
        page = context.new_page()

        # Navigate to Kid Pix first (Claude needs a real page to work with)
        print("Navigating to Kid Pix...")
        # page.goto('https://kidpix.app/')
        page.goto('http://localhost:8000') # TODO: Switch to live server after I deploy my Kid Pix fork

        # Wait for page to load
        page.wait_for_load_state('domcontentloaded')

        # Open Claude side panel using OS-level keyboard shortcut (Command+E on Mac)
        page.wait_for_timeout(1000)
        print("Opening Claude side panel with Command+E...")
        pyautogui.hotkey('command', 'e')

        # Wait a moment for the side panel to open. We need to use Playwright's
        # wait_for_timeout instead of time.sleep to give Playwright time to update the
        # Context object asynchronously behind the scenes
        # https://playwright.dev/python/docs/library#timesleep-leads-to-outdated-state
        page.wait_for_timeout(5000)

        # Find the side panel page by looking for the extension URL
        print("Finding side panel page...")
        side_panel_page = None
        for p in context.pages:
            if CLAUDE_EXTENSION_ID in p.url:
                side_panel_page = p
                print(f"Found side panel: {p.url}")
                break

        if not side_panel_page:
            raise RuntimeError("Could not find Claude side panel page")

        # Wait for the message input to be visible in the side panel
        print("Waiting for message input to load...")
        message_input = side_panel_page.locator('textarea[data-test-id="message-input"]')
        message_input.wait_for(state="visible", timeout=10000)

        # Type the prompt into the textarea
        print(f"Typing prompt: {prompt}")
        message_input.fill(prompt)

        # Click the send button
        print("Clicking send button...")
        send_button = side_panel_page.locator('button[data-test-id="send-button"]')
        send_button.click()

        print("Prompt submitted successfully!")

        # Wait for Claude to start working (stop button appears)
        print("Waiting for Claude to start working...")
        stop_button = side_panel_page.locator('button[data-test-id="stop-button"]')
        stop_button.wait_for(state="visible", timeout=30000)

        # Wait for Claude to finish (stop button disappears)
        # Set a long timeout since illustrations can take 5-10 minutes
        print("Claude is working...")
        stop_button.wait_for(state="hidden", timeout=10 * 60 * 1000)  # 10 minutes

        print("Claude has completed the task!")

        # Save the artwork
        print("Saving artwork...")

        # Create downloads directory if it doesn't exist
        downloads_dir = Path("./downloads")
        downloads_dir.mkdir(exist_ok=True)

        # Set up download handling and click save button
        with page.expect_download() as download_info:
            save_button = page.locator('button#save')
            save_button.click()

        # Wait for download to complete and save it
        download = download_info.value
        timestamp = int(time.time())
        download_path = downloads_dir / f"kidpix-{timestamp}.png"
        download.save_as(str(download_path))

        print(f"Artwork saved to: {download_path}")

        # All done, close the browser
        browser.close()

    # Exit Playwright context before running workflow
    # (Playwright has a running event loop that conflicts with asyncio)

    # Trigger Temporal workflow to process and publish the artwork
    print("\nProcessing artwork through workflow...")

    async def trigger_workflow():
        """Trigger the ProcessArtworkWorkflow and return gallery URL."""
        # Connect to Temporal
        client = await Client.connect(TEMPORAL_HOST)

        # Execute workflow
        result = await client.execute_workflow(
            ProcessArtworkWorkflow.run,
            args=[
                str(download_path),
                "Claude Draws Artwork",  # Placeholder title
                reddit_url,
            ],
            id=f"process-artwork-{timestamp}",
            task_queue=TASK_QUEUE,
        )

        return result

    # Run the async workflow and get the gallery URL
    gallery_url = asyncio.run(trigger_workflow())

    return gallery_url
