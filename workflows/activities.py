"""Temporal activities for Claude Draws artwork processing."""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import asyncpraw
import boto3
import pyautogui
from botocore.exceptions import ClientError
from baml_client.sync_client import b
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from pydantic import BaseModel
from temporalio import activity
from temporalio.client import Client

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
CLAUDE_EXTENSION_ID = "fcoeoabgfenejglbffodgkkbkcdhcgfn"

# Reddit API credentials
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "claude-draws:v0.1.0")
SUBREDDIT_NAME = "ClaudeDraws"

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
GALLERY_DIR = PROJECT_ROOT / "gallery"
GALLERY_METADATA_PATH = GALLERY_DIR / "src" / "lib" / "gallery-metadata.json"


class BrowserSessionResult(BaseModel):
    """Result from browser_session_activity."""
    image_path: str
    response_html: str
    reddit_post_url: str
    reddit_post_title: str
    reddit_post_id: str
    page_url: str  # URL of the Kid Pix page to reconnect later


def get_r2_client():
    """Create and return an R2 client using boto3."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


async def get_image_urls_from_post(post):
    """
    Extract image URLs from a Reddit submission using Async PRAW.

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


async def format_reddit_post_prompt(post) -> str:
    """
    Format a Reddit post's data into a prompt for Claude.

    Loads the static template from reddit_prompt.md and prepends post details.

    Args:
        post: Async PRAW Submission object

    Returns:
        str: Formatted prompt with post details first, then template
    """
    author = post.author
    author_name = author.name if author else "[deleted]"

    # Build post details section (this will be visible in chat history)
    post_details = [
        "# Post Details:",
        f"\n**From:** u/{author_name}",
        f"\n**Title:** {post.title}",
    ]

    # Add post body if it exists
    if post.selftext:
        post_details.append(f"\n**Request:**\n{post.selftext}")

    # Add image URLs if present
    image_urls = await get_image_urls_from_post(post)
    if image_urls:
        post_details.append(f"\n**Reference Images ({len(image_urls)}):**")
        for i, url in enumerate(image_urls, 1):
            post_details.append(f"{i}. {url}")

    # Load static prompt template
    reddit_prompt_path = PROJECT_ROOT / "claudedraw" / "reddit_prompt.md"
    with open(reddit_prompt_path, 'r') as f:
        static_prompt = f.read()

    # Combine: post details first (visible in chat), then static template
    return "\n".join(post_details) + "\n\n---\n\n" + static_prompt


@activity.defn
async def browser_session_activity(cdp_url: str) -> BrowserSessionResult:
    """
    Long-running activity that handles the full browser automation session.

    This activity:
    1. Navigates to r/ClaudeDraws and finds an open request
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

        # Find regular pages (not Claude extension side panels)
        regular_pages = [p for p in context.pages if CLAUDE_EXTENSION_ID not in p.url]

        if len(regular_pages) > 0:
            # Reuse existing tab
            page = regular_pages[0]
            activity.logger.info(f"Reusing existing tab: {page.url}")
        else:
            # Create new tab if none exist
            page = await context.new_page()
            activity.logger.info("Created new tab")

        # Navigate to r/ClaudeDraws
        activity.logger.info("Navigating to r/ClaudeDraws...")
        await page.goto('https://www.reddit.com/r/ClaudeDraws/')
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(2000)

        # Click "Community Guide" button
        activity.logger.info("Opening Community Guide...")
        community_guide_button = page.locator('#show-community-guide-btn')
        await community_guide_button.wait_for(state="visible", timeout=10000)
        await community_guide_button.click()
        await page.wait_for_timeout(1000)

        # Click "Open requests" link
        activity.logger.info("Clicking on 'Open requests' link...")
        open_requests_link = page.locator('a.resource:has-text("Open requests")')
        await open_requests_link.wait_for(state="visible", timeout=10000)
        await open_requests_link.evaluate('(element) => element.removeAttribute("target")')
        await open_requests_link.click()
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(2000)

        # Click on the first post in search results
        activity.logger.info("Clicking on top request...")
        first_post_link = page.locator('a[data-testid="post-title"]').first
        await first_post_link.wait_for(state="visible", timeout=10000)
        await first_post_link.click()
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(2000)

        # Extract post ID from URL
        current_url = page.url
        activity.logger.info(f"Post URL: {current_url}")

        import re
        post_id_match = re.search(r'/comments/([a-z0-9]+)/', current_url)
        if not post_id_match:
            raise RuntimeError(f"Could not extract post ID from URL: {current_url}")

        post_id = post_id_match.group(1)
        activity.logger.info(f"Extracted post ID: {post_id}")
        reddit_post_url = current_url

        # Fetch post data with Async PRAW
        activity.logger.info("Fetching post details with Async PRAW...")
        async with asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=REDDIT_USER_AGENT,
        ) as reddit:
            post = await reddit.submission(id=post_id)

            # Format the prompt with post details
            prompt = await format_reddit_post_prompt(post)
            author = post.author
            author_name = author.name if author else '[deleted]'
            post_title = post.title
            activity.logger.info(f"Request from u/{author_name}: {post_title}")

        # Navigate to Kid Pix
        activity.logger.info("Navigating to Kid Pix...")
        await page.goto('http://localhost:8000')
        await page.wait_for_load_state('domcontentloaded')

        # Open Claude side panel using OS-level keyboard shortcut
        await page.wait_for_timeout(1000)
        activity.logger.info("Opening Claude side panel with Command+E...")
        pyautogui.hotkey('command', 'e')
        await page.wait_for_timeout(5000)

        # Find the side panel page
        activity.logger.info("Finding side panel page...")
        side_panel_page = None
        for p in context.pages:
            if CLAUDE_EXTENSION_ID in p.url:
                side_panel_page = p
                activity.logger.info(f"Found side panel: {p.url}")
                break

        if not side_panel_page:
            raise RuntimeError("Could not find Claude side panel page")

        # Wait for message input and submit prompt
        activity.logger.info("Submitting prompt to Claude...")
        message_input = side_panel_page.locator('textarea[data-test-id="message-input"]')
        await message_input.wait_for(state="visible", timeout=10000)
        await message_input.fill(prompt)

        send_button = side_panel_page.locator('button[data-test-id="send-button"]')
        await send_button.click()
        activity.logger.info("Prompt submitted!")

        # Wait for Claude to start working
        activity.logger.info("Waiting for Claude to start working...")
        stop_button = side_panel_page.locator('button[data-test-id="stop-button"]')
        await stop_button.wait_for(state="visible", timeout=30000)

        # Wait for Claude to finish with heartbeats
        activity.logger.info("Claude is working... (sending heartbeats)")
        timeout_ms = 7 * 60 * 1000  # 7 minutes
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
                raise TimeoutError("Claude did not finish within 10 minutes")

            # Wait before next check
            await page.wait_for_timeout(1000)  # Check every second

        # Extract HTML from Claude's final response
        activity.logger.info("Extracting response metadata...")
        last_response = side_panel_page.locator('div.claude-response').last
        response_html = await last_response.inner_html()
        activity.logger.info(f"Extracted {len(response_html)} characters from response")

        # Save the artwork
        activity.logger.info("Saving artwork...")
        downloads_dir = PROJECT_ROOT / "downloads"
        downloads_dir.mkdir(exist_ok=True)

        async with page.expect_download() as download_info:
            save_button = page.locator('button#save')
            await save_button.click()

        download = await download_info.value
        timestamp = int(time.time())
        download_path = downloads_dir / f"kidpix-{timestamp}.png"
        await download.save_as(str(download_path))
        activity.logger.info(f"Artwork saved to: {download_path}")

        # Close side panel
        await side_panel_page.close()

        # Store the page URL for reconnection
        page_url = page.url

        # Don't close browser - we'll reconnect for comment posting

        return BrowserSessionResult(
            image_path=str(download_path),
            response_html=response_html,
            reddit_post_url=reddit_post_url,
            reddit_post_title=post_title,
            reddit_post_id=post_id,
            page_url=page_url,
        )


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

    # try:
    # Call BAML function to extract structured metadata
    metadata = b.ExtractArtworkMetadata(response_html)

    activity.logger.info(f"✓ Extracted title: {metadata.title}")
    activity.logger.info(f"✓ Extracted artist statement ({len(metadata.artist_statement)} chars)")

    return (metadata.title, metadata.artist_statement)

    # TODO: Proactively raise exceptions for now, would rather fix them via BAML than
    # swallow them
    # except Exception as e:
    #     activity.logger.error(f"✗ Error extracting metadata: {e}")
    #     # Return fallback values if extraction fails
    #     return ("Claude Draws Artwork", "Artwork created with Kid Pix")


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

    # Load existing gallery metadata or create new
    if GALLERY_METADATA_PATH.exists():
        with open(GALLERY_METADATA_PATH, "r") as f:
            gallery_metadata = json.load(f)
    else:
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
        "redditPostUrl": metadata["redditPostUrl"],
        "createdAt": metadata["createdAt"],
        "videoUrl": metadata.get("videoUrl", None),
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

    Runs `npm run build` in the gallery directory.
    """
    activity.logger.info("Rebuilding static site...")

    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(GALLERY_DIR),
            capture_output=True,
            text=True,
            check=True,
            timeout=60,  # 1 minute timeout
        )

        activity.logger.info("✓ Build completed successfully")
        activity.logger.debug(f"Build output: {result.stdout}")

    except subprocess.CalledProcessError as e:
        activity.logger.error(f"✗ Build failed with exit code {e.returncode}")
        activity.logger.error(f"stdout: {e.stdout}")
        activity.logger.error(f"stderr: {e.stderr}")
        raise
    except subprocess.TimeoutExpired:
        activity.logger.error("✗ Build timed out after 1 minute")
        raise


@activity.defn
async def deploy_to_cloudflare() -> str:
    """
    Deploy the built site to Cloudflare Workers using wrangler.

    Runs `wrangler deploy` in the gallery directory.

    Returns:
        Gallery URL (e.g., https://claudedraws.com)
    """
    activity.logger.info("Deploying to Cloudflare Workers...")

    try:
        result = subprocess.run(
            ["wrangler", "deploy"],
            cwd=str(GALLERY_DIR),
            capture_output=True,
            text=True,
            check=True,
            timeout=60,  # 1 minute timeout
        )

        activity.logger.info("✓ Deployment completed successfully")
        activity.logger.debug(f"Deploy output: {result.stdout}")

        # Return the gallery URL (customize based on your domain)
        gallery_url = "https://claudedraws.com"
        return gallery_url

    except subprocess.CalledProcessError as e:
        activity.logger.error(f"✗ Deployment failed with exit code {e.returncode}")
        activity.logger.error(f"stdout: {e.stdout}")
        activity.logger.error(f"stderr: {e.stderr}")
        raise
    except subprocess.TimeoutExpired:
        activity.logger.error("✗ Deployment timed out after 1 minute")
        raise


@activity.defn
async def post_reddit_comment_activity(
    cdp_url: str,
    reddit_post_url: str,
    post_id: str,
    artwork_title: str,
    artist_statement: str,
    artwork_image_path: str,
    gallery_url: str,
) -> None:
    """
    Post a comment on Reddit with the completed artwork.

    Reconnects to Chrome via CDP, navigates to the Reddit post, and posts a comment
    with the artwork title, artist statement, image, and gallery link. Also approves
    and stickies the comment, and updates the post flair.

    Args:
        cdp_url: Chrome DevTools Protocol URL
        reddit_post_url: URL of the Reddit post
        post_id: Reddit post ID (for PRAW operations)
        artwork_title: Title of the artwork
        artist_statement: Artist statement from Claude
        artwork_image_path: Local path to the PNG file
        gallery_url: Gallery URL for the artwork
    """
    activity.logger.info("Posting comment to Reddit...")

    async with async_playwright() as p:
        # Reconnect to Chrome
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]

        # Try to find an existing page, or create a new one
        if len(context.pages) > 0:
            page = context.pages[0]
        else:
            page = await context.new_page()

        # Navigate to Reddit post
        activity.logger.info(f"Navigating to: {reddit_post_url}")
        await page.goto(reddit_post_url)
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(2000)

        # Click "Join the conversation" to open comment composer
        activity.logger.info("Opening comment composer...")
        comment_trigger = page.locator('comment-composer-host').first
        await comment_trigger.wait_for(state="visible", timeout=10000)
        await comment_trigger.click()
        await page.wait_for_timeout(1000)

        # Click formatting toolbar button
        activity.logger.info("Opening formatting toolbar...")
        toolbar_button = page.locator('rte-toolbar-button[screenreadercontent="Show formatting options"]')
        await toolbar_button.wait_for(state="visible", timeout=10000)
        await toolbar_button.click()
        await page.wait_for_timeout(500)

        # Type the title
        activity.logger.info(f"Typing title: {artwork_title}")
        await page.keyboard.type(f'I call it "{artwork_title}"', delay=30)
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(300)

        # Click block quote button
        activity.logger.info("Adding block quote...")
        blockquote_button = page.locator('rte-toolbar-button-block-quote')
        await blockquote_button.click()
        await page.wait_for_timeout(300)

        # Type the artist statement
        activity.logger.info("Typing artist statement...")
        await page.keyboard.type(artist_statement, delay=30)
        await page.wait_for_timeout(500)

        # Click insert image button and handle file chooser
        activity.logger.info("Inserting image...")
        activity.logger.info(f"Selecting file: {artwork_image_path}")
        async with page.expect_file_chooser() as fc_info:
            image_button = page.locator('rte-toolbar-button-image')
            await image_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(artwork_image_path)

        # Wait for image to upload
        activity.logger.info("Waiting for image upload to complete...")
        await page.wait_for_timeout(3000)

        # Add gallery URL
        activity.logger.info("Adding gallery URL...")
        await page.keyboard.type(f"You can view the completed artwork at {gallery_url}", delay=30)
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(500)

        # Click submit button
        activity.logger.info("Submitting comment...")
        submit_button = page.locator('button[slot="submit-button"][type="submit"]')
        await submit_button.click()

        # Wait for comment to post
        activity.logger.info("Waiting for comment to post...")
        await page.wait_for_timeout(2500)
        activity.logger.info("✓ Comment posted successfully!")

        # Extract comment ID from page HTML
        activity.logger.info("Extracting comment ID...")
        comment_element = page.locator('shreddit-comment[author="claudedraws"]').last
        await comment_element.wait_for(state="attached", timeout=10000)
        comment_id = await comment_element.get_attribute('thingid')
        activity.logger.info(f"Found comment ID: {comment_id}")

        # Use Async PRAW to approve and sticky the comment
        activity.logger.info("Approving and stickying comment via Async PRAW...")
        async with asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=REDDIT_USER_AGENT,
        ) as reddit:
            comment = await reddit.comment(id=comment_id.replace('t1_', ''))
            await comment.mod.approve()
            activity.logger.info("✓ Comment approved!")

            # Sticky the comment
            activity.logger.info("Stickying comment...")
            await comment.mod.distinguish(how="yes", sticky=True)
            activity.logger.info("✓ Comment stickied!")

        # Update post flair to "Completed" via Async PRAW
        activity.logger.info("Updating post flair to 'Completed'...")
        async with asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=REDDIT_USER_AGENT,
        ) as reddit:
            submission = await reddit.submission(id=post_id)

            # Find the "Completed" flair template
            choices = await submission.flair.choices()
            completed_template = next(
                (choice for choice in choices if choice.get('flair_text') == 'Completed'),
                None
            )

            if completed_template:
                await submission.flair.select(completed_template['flair_template_id'])
                activity.logger.info("✓ Post flair updated to 'Completed'!")

                # Refresh the page to show updated flair
                activity.logger.info("Refreshing page to show updated flair...")
                await page.reload()
                await page.wait_for_load_state('domcontentloaded')
                await page.wait_for_timeout(2000)
                activity.logger.info("✓ Page refreshed!")
            else:
                activity.logger.warning("⚠ Warning: 'Completed' flair template not found")


@activity.defn
async def schedule_next_workflow(cdp_url: str, continuous: bool) -> None:
    """
    Schedule the next workflow run for continuous operation.

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

        await client.start_workflow(
            "CreateArtworkWorkflow",
            args=[cdp_url, continuous],
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        activity.logger.info(f"✓ Scheduled next workflow: {workflow_id}")

    except Exception as e:
        # Always try to schedule next run even if something fails
        activity.logger.error(f"✗ Error scheduling next workflow: {e}")
        # Re-raise to trigger Temporal retry
        raise
