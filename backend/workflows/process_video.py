"""Temporal workflow for processing artwork videos in the background."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        compress_video,
        update_artwork_video_url,
        upload_video_to_r2,
    )


@workflow.defn
class ProcessVideoWorkflow:
    """
    Background workflow for processing artwork creation videos.

    This workflow runs independently from CreateArtworkWorkflow to avoid
    blocking the main workflow while video compression is in progress.
    The artwork is already visible in the gallery; this workflow adds
    the video URL later when processing completes.

    Steps:
    1. Compress video using ffmpeg (H.264, ~70-75% size reduction)
    2. Upload compressed video to R2
    3. Update D1 artwork row with video URL
    4. Clean up local files (handled automatically in activities)

    If any step fails, the workflow logs the error and exits gracefully.
    The artwork remains visible in the gallery without a video.

    Args:
        artwork_id: Unique identifier for the artwork (e.g., "claudedraws-1234567890")
        video_path: Absolute path to uncompressed video file from OBS recording

    Returns:
        dict: Dictionary containing:
            - artwork_id: ID of the artwork
            - video_url: Public URL of the uploaded video (or None if processing failed)
            - success: Boolean indicating if video processing succeeded
    """

    @workflow.run
    async def run(self, artwork_id: str, video_path: str) -> dict:
        workflow.logger.info(f"Starting ProcessVideoWorkflow for artwork: {artwork_id}")
        workflow.logger.info(f"Video path: {video_path}")

        video_url = None
        success = False

        try:
            # Step 1: Compress video
            workflow.logger.info("Compressing video...")
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

            # Step 2: Upload to R2
            workflow.logger.info("Uploading video to R2...")
            video_url = await workflow.execute_activity(
                upload_video_to_r2,
                args=[artwork_id, compressed_video_path],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    backoff_coefficient=2.0,
                ),
            )
            workflow.logger.info(f"✓ Video uploaded: {video_url}")

            # Step 3: Update D1 with video URL
            workflow.logger.info("Updating artwork in D1...")
            await workflow.execute_activity(
                update_artwork_video_url,
                args=[artwork_id, video_url],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            workflow.logger.info("✓ Artwork updated with video URL in D1")

            success = True
            workflow.logger.info(f"✓ Video processing complete for artwork: {artwork_id}")

        except Exception as e:
            # Log error but don't raise - artwork is already visible without video
            workflow.logger.error(f"✗ Video processing failed for artwork {artwork_id}: {e}")
            workflow.logger.info("Artwork remains visible in gallery without video")

        return {
            "artwork_id": artwork_id,
            "video_url": video_url,
            "success": success,
        }
