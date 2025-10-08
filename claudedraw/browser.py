"""Browser automation using Playwright."""

import os
import time

# IMPORTANT: Set this environment variable BEFORE importing playwright
# This enables the underlying Node.js server to attach to Chrome targets of type "other"
# (such as extension side panels) as if they were regular pages
os.environ['PW_CHROMIUM_ATTACH_TO_OTHER'] = '1'

import pyautogui
from playwright.sync_api import sync_playwright

# TODO: Make this an environment variable - Anthropic would probably prefer to keep it secret
CLAUDE_EXTENSION_ID = "fcoeoabgfenejglbffodgkkbkcdhcgfn"


def submit_claude_prompt(cdp_url: str, prompt: str):
    """
    Connect to a Chrome browser via CDP and submit a prompt to Claude for Chrome.

    Args:
        cdp_url: Chrome DevTools Protocol endpoint URL
        prompt: The prompt to send to Claude
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
        browser.close()
