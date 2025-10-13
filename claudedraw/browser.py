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

import praw
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

# Reddit API credentials
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "claude-draws:v0.1.0")
SUBREDDIT_NAME = "ClaudeDraws"


def get_image_urls_from_post(post):
    """
    Extract image URLs from a Reddit submission using PRAW.

    Returns:
        list: List of image URLs found in the post
    """
    urls = []

    # Check if it's a gallery post
    if hasattr(post, "is_gallery") and post.is_gallery:
        if hasattr(post, "media_metadata"):
            for item in post.media_metadata.values():
                if "s" in item and "u" in item["s"]:
                    url = item["s"]["u"].replace("&amp;", "&")
                    urls.append(url)

    # Check if it's a direct image post
    elif hasattr(post, "post_hint") and post.post_hint == "image":
        urls.append(post.url)

    # Check if URL points to common image hosts
    elif post.url and any(ext in post.url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif"]):
        urls.append(post.url)

    return urls


def format_reddit_post_prompt(post) -> str:
    """
    Format a Reddit post's data into a prompt for Claude.

    Loads the static template from reddit_prompt.md and prepends post details.

    Args:
        post: PRAW Submission object

    Returns:
        str: Formatted prompt with post details first, then template
    """
    author = post.author.name if post.author else "[deleted]"

    # Build post details section (this will be visible in chat history)
    post_details = [
        "# Post Details:\n",
        f"**From:** u/{author}",
        f"**Title:** {post.title}",
    ]

    # Add post body if it exists
    if post.selftext:
        post_details.append(f"\n**Request:**\n{post.selftext}")

    # Add image URLs if present
    image_urls = get_image_urls_from_post(post)
    if image_urls:
        post_details.append(f"\n**Reference Images ({len(image_urls)}):**")
        for i, url in enumerate(image_urls, 1):
            post_details.append(f"{i}. {url}")

    # Load static prompt template
    reddit_prompt_path = Path(__file__).parent / 'reddit_prompt.md'
    with open(reddit_prompt_path, 'r') as f:
        static_prompt = f.read()

    # Combine: post details first (visible in chat), then static template
    return "\n".join(post_details) + "\n\n---\n\n" + static_prompt


def submit_claude_prompt(cdp_url: str, prompt: str | None) -> str:
    """
    Connect to a Chrome browser via CDP and submit a prompt to Claude for Chrome.

    Args:
        cdp_url: Chrome DevTools Protocol endpoint URL
        prompt: The prompt to send to Claude (optional).
                If None, Claude will navigate Reddit for requests.
                If provided, Claude will go directly to Kid Pix with this prompt.

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

        # Determine mode and navigate to appropriate starting page
        reddit_post_url = None  # Track Reddit post URL for workflow

        if prompt is None:
            # Reddit mode: Navigate Reddit UI to find a request
            print("Navigating to r/ClaudeDraws...")
            page.goto('https://www.reddit.com/r/ClaudeDraws/')
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(2000)  # Wait for page to fully render

            # Click "Community Guide" button
            print("Opening Community Guide...")
            community_guide_button = page.locator('#show-community-guide-btn')
            community_guide_button.wait_for(state="visible", timeout=10000)
            community_guide_button.click()
            page.wait_for_timeout(1000)

            # Click "Open requests" link
            print("Clicking on 'Open requests' link...")
            # Find the <a> element that contains "Open requests" text in a descendant
            open_requests_link = page.locator('a.resource:has-text("Open requests")')
            open_requests_link.wait_for(state="visible", timeout=10000)

            # Remove target="_blank" to prevent opening in new tab
            open_requests_link.evaluate('(element) => element.removeAttribute("target")')

            open_requests_link.click()
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(2000)

            # Click on the first post in search results
            print("Clicking on top request...")
            first_post_link = page.locator('a[data-testid="post-title"]').first
            first_post_link.wait_for(state="visible", timeout=10000)
            first_post_link.click()
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(2000)

            # Extract post ID from URL
            current_url = page.url
            print(f"Post URL: {current_url}")

            # URL format: /r/ClaudeDraws/comments/{POST_ID}/...
            # Extract post ID from URL
            import re
            post_id_match = re.search(r'/comments/([a-z0-9]+)/', current_url)
            if not post_id_match:
                raise RuntimeError(f"Could not extract post ID from URL: {current_url}")

            post_id = post_id_match.group(1)
            print(f"Extracted post ID: {post_id}")
            reddit_post_url = current_url

            # Fetch post data with PRAW
            print("Fetching post details with PRAW...")
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                username=REDDIT_USERNAME,
                password=REDDIT_PASSWORD,
                user_agent=REDDIT_USER_AGENT,
            )
            post = reddit.submission(id=post_id)

            # Format the prompt with post details
            prompt = format_reddit_post_prompt(post)
            print(f"Request from u/{post.author.name if post.author else '[deleted]'}: {post.title}")

            # Navigate to Kid Pix
            print("Navigating to Kid Pix...")
            page.goto('http://localhost:8000')
            page.wait_for_load_state('domcontentloaded')

        else:
            # Direct mode: Navigate to Kid Pix
            print("Navigating to Kid Pix...")
            page.goto('http://localhost:8000')
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

        # Extract HTML from Claude's final response
        print("Extracting response metadata...")
        last_response = side_panel_page.locator('div.claude-response').last
        response_html = last_response.inner_html()
        print(f"Extracted {len(response_html)} characters from Claude's response")

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
                response_html,  # HTML from Claude's final response
                reddit_post_url,  # Reddit post URL (None for direct mode)
            ],
            id=f"process-artwork-{timestamp}",
            task_queue=TASK_QUEUE,
        )

        return result

    # Run the async workflow and get the gallery URL
    gallery_url = asyncio.run(trigger_workflow())

    return gallery_url
