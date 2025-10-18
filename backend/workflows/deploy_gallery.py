"""Temporal workflow for deploying the gallery site."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        deploy_to_cloudflare,
        rebuild_static_site,
    )


@workflow.defn
class DeployGalleryWorkflow:
    """
    Workflow for rebuilding and deploying the gallery site.

    This workflow handles the static site build and Cloudflare deployment
    steps. It's designed to run independently (often in parallel with other
    workflows) to update the live gallery after new artworks are added.

    This separation allows the main CreateArtworkWorkflow to continue with
    other activities (like posting Reddit comments) while the gallery
    deployment happens in the background.

    Args:
        artwork_id: ID of the artwork being deployed (for logging/URL generation)

    Returns:
        str: Full URL to the deployed artwork page
    """

    @workflow.run
    async def run(self, artwork_id: str) -> str:
        workflow.logger.info(f"Starting DeployGalleryWorkflow for artwork: {artwork_id}")

        # Activity 1: Rebuild static site
        await workflow.execute_activity(
            rebuild_static_site,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
                backoff_coefficient=2.0,
            ),
        )

        workflow.logger.info("✓ Static site rebuilt")

        # Activity 2: Deploy to Cloudflare Workers
        gallery_base_url = await workflow.execute_activity(
            deploy_to_cloudflare,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0,
            ),
        )

        artwork_url = f"{gallery_base_url}/artwork/{artwork_id}"
        workflow.logger.info(f"✓ Deployed to Cloudflare: {artwork_url}")

        return artwork_url
