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
    deploy_to_cloudflare,
    rebuild_static_site,
    upload_image_to_r2,
    upload_metadata_to_r2,
)
from workflows.process_artwork import ProcessArtworkWorkflow

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
        workflows=[ProcessArtworkWorkflow],
        activities=[
            upload_image_to_r2,
            upload_metadata_to_r2,
            append_to_gallery_metadata,
            rebuild_static_site,
            deploy_to_cloudflare,
        ],
    )

    # Run worker
    logger.info("✓ Worker started and ready to process workflows")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
