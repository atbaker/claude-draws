"""Temporal workflow for creating Claude Draws artwork."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        browser_session_activity,
        cleanup_tab_activity,
        compress_video,
        extract_artwork_metadata,
        insert_artwork_to_d1,
        send_email_notification,
        start_obs_recording,
        stop_obs_recording,
        update_submission_status,
        upload_image_to_r2,
        upload_video_to_r2,
        BrowserSessionResult,
    )


@workflow.defn
class CreateArtworkWorkflow:
    """
    Workflow for creating artwork from form submissions.

    This workflow handles the entire end-to-end process:
    1. Updates submission status to "processing" (if submission_id provided)
    2. Starts OBS recording of the artwork creation process
    3. Browser session: finds pending submission, submits to Claude, waits, downloads
    4. Stops OBS recording and retrieves video file path
    5. Compresses video using PyAV (H.264, ~70-75% size reduction)
    6. Extracts metadata (title and artist statement)
    7. Uploads image to R2
    8. Uploads compressed video to R2 (if recording was successful)
    9. Inserts metadata into D1 artworks table (including video URL)
    10. Updates submission status to "completed"
    11. Sends email notification (if email provided)

    Note: No build/deploy step required! Gallery pages fetch from D1 at runtime,
    so new artworks appear immediately without rebuilding the site.

    Note: Continuous mode scheduling is handled by CheckSubmissionsWorkflow.
    This workflow no longer schedules the next workflow run.

    Args:
        cdp_url: Chrome DevTools Protocol endpoint URL
        continuous: Deprecated parameter, no longer used (kept for backward compatibility)
        submission_id: Optional submission ID to process (if provided by CheckSubmissionsWorkflow)

    Returns:
        dict: Dictionary containing:
            - artwork_url: Gallery URL where the artwork can be viewed
            - submission_id: ID of the form submission that was fulfilled (if any)
            - artwork_id: ID of the created artwork
    """

    @workflow.run
    async def run(self, cdp_url: str, continuous: bool = False, submission_id: str = None) -> dict:
        workflow.logger.info(f"Starting CreateArtworkWorkflow (continuous={continuous}, submission_id={submission_id})")
        workflow.logger.info(f"CDP URL: {cdp_url}")

        # Update submission status to "processing" if this is a form submission
        if submission_id:
            await workflow.execute_activity(
                update_submission_status,
                args=[submission_id, "processing"],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            workflow.logger.info("✓ Updated submission status to 'processing'")

        # Start OBS recording to capture the entire artwork creation process
        try:
            await workflow.execute_activity(
                start_obs_recording,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            workflow.logger.info("✓ OBS recording started")
        except Exception as e:
            # Recording failure should not block artwork creation
            workflow.logger.warning(f"⚠ Failed to start OBS recording: {e}")
            workflow.logger.warning("Continuing without recording...")

        # Activity 1: Browser session - find request, submit to Claude, wait, download
        browser_result: BrowserSessionResult = await workflow.execute_activity(
            browser_session_activity,
            args=[cdp_url, submission_id],
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

        # Stop OBS recording and get video file path
        video_path = None
        try:
            video_path = await workflow.execute_activity(
                stop_obs_recording,
                start_to_close_timeout=timedelta(seconds=60),  # Longer timeout for recording to finalize
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            if video_path:
                workflow.logger.info(f"✓ OBS recording stopped. Video path: {video_path}")
            else:
                workflow.logger.warning("⚠ OBS recording stopped but no video path received")
        except Exception as e:
            # Recording failure should not block artwork creation
            workflow.logger.warning(f"⚠ Failed to stop OBS recording: {e}")
            workflow.logger.warning("Continuing without recording...")

        # Compress video (if recording was successful)
        compressed_video_path = None
        if video_path:
            try:
                compressed_video_path = await workflow.execute_activity(
                    compress_video,
                    args=[video_path],
                    start_to_close_timeout=timedelta(minutes=5),  # Allow time for compression
                    retry_policy=RetryPolicy(
                        maximum_attempts=2,
                        backoff_coefficient=2.0,
                    ),
                )
                workflow.logger.info(f"✓ Video compressed: {compressed_video_path}")
            except Exception as e:
                # Compression failure should not block artwork creation
                workflow.logger.warning(f"⚠ Failed to compress video: {e}")
                workflow.logger.warning("Continuing without video...")
                compressed_video_path = None

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

        # Activity 4: Upload video to R2 (if compression was successful)
        video_url = None
        if compressed_video_path:
            try:
                video_url = await workflow.execute_activity(
                    upload_video_to_r2,
                    args=[artwork_id, compressed_video_path],
                    start_to_close_timeout=timedelta(minutes=5),  # Reduced timeout for compressed videos
                    retry_policy=RetryPolicy(
                        maximum_attempts=3,
                        backoff_coefficient=2.0,
                    ),
                )
                workflow.logger.info(f"✓ Video uploaded: {video_url}")
            except Exception as e:
                # Video upload failure should not block artwork creation
                workflow.logger.warning(f"⚠ Failed to upload video to R2: {e}")
                workflow.logger.warning("Continuing without video...")
        else:
            workflow.logger.info("⊘ No video to upload (recording/compression was skipped or failed)")

        # Activity 5: Insert metadata into D1
        metadata = {
            "id": artwork_id,
            "title": title,
            "artistStatement": artist_statement,
            "imageUrl": image_url,  # Include image URL for D1
            "createdAt": workflow.now().isoformat(),
            "videoUrl": video_url,  # Include video URL (or None if recording failed)
            "prompt": browser_result.prompt,
            "submissionId": browser_result.submission_id,
            "autogenerated": browser_result.submission_id is None,  # Auto-generated if no submission
        }

        await workflow.execute_activity(
            insert_artwork_to_d1,
            args=[artwork_id, metadata],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        workflow.logger.info("✓ Metadata inserted into D1")

        # Artwork URL is immediately available (no build/deploy needed!)
        artwork_url = f"https://claudedraws.com/artwork/{artwork_id}"

        # Activity 5: Update submission status to "completed" and send email notification
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

        # Return result
        workflow.logger.info(f"✓ Workflow complete: {artwork_url}")
        return {
            "artwork_url": artwork_url,
            "submission_id": browser_result.submission_id,
            "artwork_id": artwork_id,
        }
