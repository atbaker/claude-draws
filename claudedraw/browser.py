"""Browser automation using Playwright."""

import os
import sys
import time
from pathlib import Path

# IMPORTANT: Set this environment variable BEFORE importing playwright
# This enables the underlying Node.js server to attach to Chrome targets of type "other"
# (such as extension side panels) as if they were regular pages
os.environ['PW_CHROMIUM_ATTACH_TO_OTHER'] = '1'

import asyncpraw
import pyautogui
from dotenv import load_dotenv
from playwright.async_api import async_playwright
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


async def post_reddit_comment(page, reddit_post_url: str, post_id: str, artwork_title: str, artist_statement: str, artwork_image_path: str, gallery_url: str) -> None:
    """
    Post a comment on a Reddit post with the completed artwork.

    Uses Playwright to automate the Reddit comment UI, typing the title and artist
    statement, uploading the artwork image, adding the gallery URL, and submitting the comment.
    Also approves the comment and updates the post flair using PRAW.

    Args:
        page: Playwright Page object (already navigated to Kid Pix)
        reddit_post_url: URL of the Reddit post to comment on
        post_id: Reddit post ID (e.g., "1o59xzm")
        artwork_title: Title of the completed artwork
        artist_statement: Artist statement from Claude
        artwork_image_path: Path to the local PNG file to upload
        gallery_url: URL to the gallery page for this artwork
    """
    print("\nPosting comment to Reddit...")

    # Navigate back to the Reddit post
    print(f"Navigating to: {reddit_post_url}")
    await page.goto(reddit_post_url)
    await page.wait_for_load_state('domcontentloaded')
    await page.wait_for_timeout(2000)

    # Click "Join the conversation" to open comment composer
    print("Opening comment composer...")
    comment_trigger = page.locator('comment-composer-host').first
    await comment_trigger.wait_for(state="visible", timeout=10000)
    await comment_trigger.click()
    await page.wait_for_timeout(1000)

    # Click formatting toolbar button
    print("Opening formatting toolbar...")
    toolbar_button = page.locator('rte-toolbar-button[screenreadercontent="Show formatting options"]')
    await toolbar_button.wait_for(state="visible", timeout=10000)
    await toolbar_button.click()
    await page.wait_for_timeout(500)

    # Type the title
    print(f"Typing title: {artwork_title}")
    await page.keyboard.type(f'I call it "{artwork_title}"', delay=30)
    await page.keyboard.press('Enter')
    await page.wait_for_timeout(300)

    # Click block quote button
    print("Adding block quote...")
    blockquote_button = page.locator('rte-toolbar-button-block-quote')
    await blockquote_button.click()
    await page.wait_for_timeout(300)

    # Type the artist statement
    print("Typing artist statement...")
    await page.keyboard.type(artist_statement, delay=30)
    await page.wait_for_timeout(500)

    # Click insert image button and handle file chooser
    print("Inserting image...")
    print(f"Selecting file: {artwork_image_path}")
    async with page.expect_file_chooser() as fc_info:
        image_button = page.locator('rte-toolbar-button-image')
        await image_button.click()
    file_chooser = await fc_info.value
    await file_chooser.set_files(artwork_image_path)

    # Wait for image to upload (watch for upload completion)
    print("Waiting for image upload to complete...")
    await page.wait_for_timeout(3000)

    # Add gallery URL on the next line (cursor should already be positioned after the image)
    print("Adding gallery URL...")
    await page.keyboard.type(f"You can view the completed artwork at {gallery_url}", delay=30)
    await page.keyboard.press('Enter')
    await page.wait_for_timeout(500)

    # Click submit button
    print("Submitting comment...")
    submit_button = page.locator('button[slot="submit-button"][type="submit"]')
    await submit_button.click()

    # Wait for comment to post
    print("Waiting for comment to post...")
    await page.wait_for_timeout(2500)  # Increased wait time for comment to fully load

    print("✓ Comment posted successfully!")

    # Reddit keeps flagging our comments as spam, so we need to manually approve them
    # Extract the comment ID from the page HTML
    print("Extracting comment ID...")
    comment_element = page.locator('shreddit-comment[author="claudedraws"]').last
    await comment_element.wait_for(state="attached", timeout=10000)
    comment_id = await comment_element.get_attribute('thingid')
    print(f"Found comment ID: {comment_id}")

    # Use Async PRAW to approve the comment
    print("Approving comment via Async PRAW...")
    async with asyncpraw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        username=REDDIT_USERNAME,
        password=REDDIT_PASSWORD,
        user_agent=REDDIT_USER_AGENT,
    ) as reddit:
        comment = await reddit.comment(id=comment_id.replace('t1_', ''))  # Remove the 't1_' prefix
        await comment.mod.approve()
        print("✓ Comment approved!")

        # Sticky the comment so it appears at the top
        print("Stickying comment...")
        await comment.mod.distinguish(how="yes", sticky=True)
        print("✓ Comment stickied!")

    # Update post flair to "Completed" via Async PRAW
    print("\nUpdating post flair to 'Completed'...")
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
            print("✓ Post flair updated to 'Completed'!")

            # Refresh the page so viewers can see the updated flair
            print("Refreshing page to show updated flair...")
            await page.reload()
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_timeout(2000)  # Give viewers time to see it
            print("✓ Page refreshed!")
        else:
            print("⚠ Warning: 'Completed' flair template not found")


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
    reddit_prompt_path = Path(__file__).parent / 'reddit_prompt.md'
    with open(reddit_prompt_path, 'r') as f:
        static_prompt = f.read()

    # Combine: post details first (visible in chat), then static template
    return "\n".join(post_details) + "\n\n---\n\n" + static_prompt


async def submit_claude_prompt(cdp_url: str, prompt: str | None) -> str:
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
    async with async_playwright() as p:
        # Connect to the existing browser via CDP
        browser = await p.chromium.connect_over_cdp(cdp_url)

        # Get the default context (the browser's existing session)
        context = browser.contexts[0]

        # Create a new page
        page = await context.new_page()

        # Determine mode and navigate to appropriate starting page
        reddit_post_url = None  # Track Reddit post URL for workflow
        post_id = None  # Track Reddit post ID for comment posting

        if prompt is None:
            # Reddit mode: Navigate Reddit UI to find a request
            print("Navigating to r/ClaudeDraws...")
            await page.goto('https://www.reddit.com/r/ClaudeDraws/')
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_timeout(2000)  # Wait for page to fully render

            # Click "Community Guide" button
            print("Opening Community Guide...")
            community_guide_button = page.locator('#show-community-guide-btn')
            await community_guide_button.wait_for(state="visible", timeout=10000)
            await community_guide_button.click()
            await page.wait_for_timeout(1000)

            # Click "Open requests" link
            print("Clicking on 'Open requests' link...")
            # Find the <a> element that contains "Open requests" text in a descendant
            open_requests_link = page.locator('a.resource:has-text("Open requests")')
            await open_requests_link.wait_for(state="visible", timeout=10000)

            # Remove target="_blank" to prevent opening in new tab
            await open_requests_link.evaluate('(element) => element.removeAttribute("target")')

            await open_requests_link.click()
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_timeout(2000)

            # Click on the first post in search results
            print("Clicking on top request...")
            first_post_link = page.locator('a[data-testid="post-title"]').first
            await first_post_link.wait_for(state="visible", timeout=10000)
            await first_post_link.click()
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_timeout(2000)

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

            # Fetch post data with Async PRAW
            print("Fetching post details with Async PRAW...")
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
                print(f"Request from u/{author_name}: {post.title}")

            # Navigate to Kid Pix
            print("Navigating to Kid Pix...")
            await page.goto('http://localhost:8000')
            await page.wait_for_load_state('domcontentloaded')

        else:
            # Direct mode: Navigate to Kid Pix
            print("Navigating to Kid Pix...")
            await page.goto('http://localhost:8000')
            await page.wait_for_load_state('domcontentloaded')

        # Open Claude side panel using OS-level keyboard shortcut (Command+E on Mac)
        await page.wait_for_timeout(1000)
        print("Opening Claude side panel with Command+E...")
        pyautogui.hotkey('command', 'e')

        # Wait a moment for the side panel to open. We need to use Playwright's
        # wait_for_timeout instead of time.sleep to give Playwright time to update the
        # Context object asynchronously behind the scenes
        # https://playwright.dev/python/docs/library#timesleep-leads-to-outdated-state
        await page.wait_for_timeout(5000)

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
        await message_input.wait_for(state="visible", timeout=10000)

        # Type the prompt into the textarea
        print(f"Typing prompt: {prompt}")
        await message_input.fill(prompt)

        # Click the send button
        print("Clicking send button...")
        send_button = side_panel_page.locator('button[data-test-id="send-button"]')
        await send_button.click()

        print("Prompt submitted successfully!")

        # Wait for Claude to start working (stop button appears)
        print("Waiting for Claude to start working...")
        stop_button = side_panel_page.locator('button[data-test-id="stop-button"]')
        await stop_button.wait_for(state="visible", timeout=30000)

        # Wait for Claude to finish (stop button disappears)
        # Set a long timeout since illustrations can take 5-10 minutes
        print("Claude is working...")
        await stop_button.wait_for(state="hidden", timeout=10 * 60 * 1000)  # 10 minutes

        print("Claude has completed the task!")

        # Extract HTML from Claude's final response
        print("Extracting response metadata...")
        last_response = side_panel_page.locator('div.claude-response').last
        response_html = await last_response.inner_html()
        print(f"Extracted {len(response_html)} characters from Claude's response")

        # Save the artwork
        print("Saving artwork...")

        # Create downloads directory if it doesn't exist
        downloads_dir = Path("./downloads")
        downloads_dir.mkdir(exist_ok=True)

        # Set up download handling and click save button
        async with page.expect_download() as download_info:
            save_button = page.locator('button#save')
            await save_button.click()

        # Wait for download to complete and save it
        download = await download_info.value
        timestamp = int(time.time())
        download_path = downloads_dir / f"kidpix-{timestamp}.png"
        await download.save_as(str(download_path))

        print(f"Artwork saved to: {download_path}")

        # Trigger Temporal workflow to process and publish the artwork
        print("\nProcessing artwork through workflow...")

        async def trigger_workflow():
            """Trigger the ProcessArtworkWorkflow and return result."""
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

        # Run the async workflow and get the result
        # Result is a dict with: artwork_url, title, artist_statement
        result = await trigger_workflow()

        # Close the side panel before continuing
        side_panel_page.close()

        # Post comment to Reddit if we're in Reddit mode
        if reddit_post_url is not None:
            await post_reddit_comment(
                page=page,
                reddit_post_url=reddit_post_url,
                post_id=post_id,
                artwork_title=result["title"],
                artist_statement=result["artist_statement"],
                artwork_image_path=str(download_path),
                gallery_url=result["artwork_url"],
            )

        # All done, close the browser
        await browser.close()

    # Return the gallery URL
    return result["artwork_url"]
