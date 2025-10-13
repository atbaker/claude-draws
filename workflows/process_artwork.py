"""Temporal workflow for processing Claude Draws artwork."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        append_to_gallery_metadata,
        deploy_to_cloudflare,
        rebuild_static_site,
        upload_image_to_r2,
        upload_metadata_to_r2,
    )


@workflow.defn
class ProcessArtworkWorkflow:
    """
    Workflow for processing newly created artwork.

    This workflow:
    1. Uploads the artwork image to R2
    2. Creates and uploads metadata to R2
    3. Appends artwork to local gallery metadata
    4. Rebuilds the static site
    5. Deploys to Cloudflare Workers
    6. Returns the gallery URL

    Args:
        image_path: Path to the downloaded PNG file
        title: Artwork title (from Claude)
        reddit_url: URL of Reddit post that inspired this artwork

    Returns:
        Gallery URL where the artwork can be viewed
    """

    @workflow.run
    async def run(self, image_path: str, title: str, reddit_url: str) -> str:
        # Generate artwork ID based on timestamp
        # Use workflow.now() for deterministic time
        artwork_id = f"kidpix-{int(workflow.now().timestamp())}"

        workflow.logger.info(f"Processing artwork: {artwork_id}")
        workflow.logger.info(f"Title: {title}")
        workflow.logger.info(f"Reddit URL: {reddit_url}")

        # Activity 1: Upload image to R2
        image_url = await workflow.execute_activity(
            upload_image_to_r2,
            args=[artwork_id, image_path],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0,
            ),
        )

        workflow.logger.info(f"Image uploaded: {image_url}")

        # Activity 2: Upload metadata JSON to R2
        metadata = {
            "id": artwork_id,
            "title": title,
            "redditPostUrl": reddit_url,
            "createdAt": workflow.now().isoformat(),
            "videoUrl": None,
        }

        await workflow.execute_activity(
            upload_metadata_to_r2,
            args=[artwork_id, metadata],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        workflow.logger.info("Metadata uploaded to R2")

        # Activity 3: Append to local gallery-metadata.json
        await workflow.execute_activity(
            append_to_gallery_metadata,
            args=[artwork_id, image_url, metadata],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        workflow.logger.info("Appended to gallery metadata")

        # Activity 4: Rebuild static site (fast - just HTML generation)
        await workflow.execute_activity(
            rebuild_static_site,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        workflow.logger.info("Static site rebuilt")

        # Activity 5: Deploy to Cloudflare Workers
        gallery_url = await workflow.execute_activity(
            deploy_to_cloudflare,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        workflow.logger.info(f"Deployed to Cloudflare: {gallery_url}")

        # Return the full artwork URL
        artwork_url = f"{gallery_url}/artwork/{artwork_id}"
        workflow.logger.info(f"✓ Artwork processing complete: {artwork_url}")

        return artwork_url
