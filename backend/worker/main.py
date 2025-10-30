"""Temporal worker for Claude Draws artwork processing."""

import asyncio
import logging
import os

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

# Load environment variables
load_dotenv()

# Import workflow and activities
from workflows.activities import (
    append_to_gallery_metadata,
    browser_session_activity,
    check_for_pending_submissions,
    cleanup_tab_activity,
    deploy_to_cloudflare,
    extract_artwork_metadata,
    rebuild_static_site,
    send_email_notification,
    start_gallery_deployment_workflow,
    switch_obs_scene,
    update_countdown_text,
    update_submission_status,
    upload_image_to_r2,
    upload_metadata_to_r2,
    visit_gallery_activity,
)
from workflows.check_submissions import CheckSubmissionsWorkflow
from workflows.create_artwork import CreateArtworkWorkflow
from workflows.deploy_gallery import DeployGalleryWorkflow

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporal configuration
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "claude-draws-queue"


async def main():
    """Start the Temporal worker."""
    logger.info(f"Connecting to Temporal server at {TEMPORAL_HOST}")

    # Connect to Temporal
    client = await Client.connect(TEMPORAL_HOST)

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")

    # Create worker
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CheckSubmissionsWorkflow, CreateArtworkWorkflow, DeployGalleryWorkflow],
        activities=[
            browser_session_activity,
            check_for_pending_submissions,
            cleanup_tab_activity,
            extract_artwork_metadata,
            upload_image_to_r2,
            upload_metadata_to_r2,
            append_to_gallery_metadata,
            update_submission_status,
            send_email_notification,
            start_gallery_deployment_workflow,
            rebuild_static_site,
            deploy_to_cloudflare,
            switch_obs_scene,
            update_countdown_text,
            visit_gallery_activity,
        ],
        max_concurrent_activities=4,
    )

    # Run worker
    logger.info("✓ Worker started and ready to process workflows")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
