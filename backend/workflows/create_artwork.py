"""Temporal workflow for creating Claude Draws artwork."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        append_to_gallery_metadata,
        browser_session_activity,
        cleanup_tab_activity,
        extract_artwork_metadata,
        schedule_next_workflow,
        send_email_notification,
        start_gallery_deployment_workflow,
        update_submission_status,
        upload_image_to_r2,
        upload_metadata_to_r2,
        BrowserSessionResult,
    )


@workflow.defn
class CreateArtworkWorkflow:
    """
    Workflow for creating artwork from form submissions.

    This workflow handles the entire end-to-end process:
    1. Finds a pending form submission from D1 database
    2. Updates submission status to "processing"
    3. Submits prompt to Claude for Chrome
    4. Waits for Claude to complete the artwork
    5. Downloads the artwork image
    6. Extracts metadata (title and artist statement)
    7. Uploads image and metadata to R2
    8. Updates submission status to "completed"
    9. Starts standalone gallery deployment workflow (runs independently)
    10. Sends email notification (if email provided)
    11. Optionally schedules the next workflow (for continuous mode)

    Note: Gallery deployment (step 9) runs as an independent workflow to
    avoid blocking the main workflow.

    Args:
        cdp_url: Chrome DevTools Protocol endpoint URL
        continuous: If True, schedule another workflow run after completion

    Returns:
        dict: Dictionary containing:
            - artwork_url: Gallery URL where the artwork can be viewed
            - submission_id: ID of the form submission that was fulfilled (if any)
    """

    @workflow.run
    async def run(self, cdp_url: str, continuous: bool = False) -> dict:
        workflow.logger.info(f"Starting CreateArtworkWorkflow (continuous={continuous})")
        workflow.logger.info(f"CDP URL: {cdp_url}")

        # Activity 1: Browser session - find request, submit to Claude, wait, download
        browser_result: BrowserSessionResult = await workflow.execute_activity(
            browser_session_activity,
            args=[cdp_url],
            start_to_close_timeout=timedelta(minutes=15),  # Long timeout for drawing
            heartbeat_timeout=timedelta(seconds=30),  # Expect heartbeats every 30 seconds
            retry_policy=RetryPolicy(
                maximum_attempts=2,  # Only retry once for browser automation
                backoff_coefficient=2.0,
            ),
        )

        workflow.logger.info(f"✓ Browser session complete")
        workflow.logger.info(f"  Submission ID: {browser_result.submission_id}")
        workflow.logger.info(f"  Image path: {browser_result.image_path}")

        # Update submission status to "processing" if this was a form submission
        if browser_result.submission_id:
            await workflow.execute_activity(
                update_submission_status,
                args=[browser_result.submission_id, "processing"],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            workflow.logger.info("✓ Updated submission status to 'processing'")

        # Generate artwork ID based on timestamp
        artwork_id = f"claudedraws-{int(workflow.now().timestamp())}"

        # Activity 2: Extract metadata from Claude's response using BAML
        title, artist_statement = await workflow.execute_activity(
            extract_artwork_metadata,
            args=[browser_result.response_html],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0,
            ),
        )

        workflow.logger.info(f"✓ Metadata extracted")
        workflow.logger.info(f"  Title: {title}")
        workflow.logger.info(f"  Artist statement: {artist_statement[:100]}...")

        # Activity 3: Upload image to R2
        image_url = await workflow.execute_activity(
            upload_image_to_r2,
            args=[artwork_id, browser_result.image_path],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0,
            ),
        )

        workflow.logger.info(f"✓ Image uploaded: {image_url}")

        # Activity 4: Upload metadata JSON to R2
        metadata = {
            "id": artwork_id,
            "title": title,
            "artistStatement": artist_statement,
            "createdAt": workflow.now().isoformat(),
            "videoUrl": None,
            "prompt": browser_result.prompt,
            "submissionId": browser_result.submission_id,
        }

        await workflow.execute_activity(
            upload_metadata_to_r2,
            args=[artwork_id, metadata],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        workflow.logger.info("✓ Metadata uploaded to R2")

        # Activity 5: Append to local gallery-metadata.json
        await workflow.execute_activity(
            append_to_gallery_metadata,
            args=[artwork_id, image_url, metadata],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        workflow.logger.info("✓ Appended to gallery metadata")

        # Activity 6: Start standalone gallery deployment workflow
        # This runs independently in parallel with email notification sending below
        await workflow.execute_activity(
            start_gallery_deployment_workflow,
            args=[artwork_id],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0,
            ),
        )

        workflow.logger.info("✓ Gallery deployment workflow started")

        # Use predictable URL - deployment will complete in background
        artwork_url = f"https://claudedraws.com/artwork/{artwork_id}"

        # Activity 7: Update submission status to "completed" and send email notification
        if browser_result.submission_id:
            # Update submission status
            await workflow.execute_activity(
                update_submission_status,
                args=[browser_result.submission_id, "completed", artwork_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            workflow.logger.info("✓ Updated submission status to 'completed'")

            # Send email notification if email was provided
            if browser_result.submission_email:
                await workflow.execute_activity(
                    send_email_notification,
                    args=[
                        browser_result.submission_email,
                        artwork_id,
                        title,
                        artwork_url,
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                workflow.logger.info(f"✓ Sent email notification to {browser_result.submission_email}")
            else:
                workflow.logger.info("⊘ No email provided, skipping notification")
        else:
            workflow.logger.info("⊘ Autogenerated artwork, no submission to update")

        # Clean up the tab
        await workflow.execute_activity(
            cleanup_tab_activity,
            args=[cdp_url, browser_result.tab_url],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0,
            ),
        )
        workflow.logger.info("✓ Tab cleaned up")

        # Activity 8: Schedule next workflow if continuous mode
        if continuous:
            workflow.logger.info("Continuous mode: scheduling next workflow...")
            await workflow.execute_activity(
                schedule_next_workflow,
                args=[cdp_url, continuous],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    backoff_coefficient=2.0,
                ),
            )
            workflow.logger.info("✓ Next workflow scheduled")

        # Return result
        workflow.logger.info(f"✓ Workflow complete: {artwork_url}")
        return {
            "artwork_url": artwork_url,
            "submission_id": browser_result.submission_id,
            "artwork_id": artwork_id,
        }
