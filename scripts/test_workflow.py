#!/usr/bin/env python3
"""Test script for the ProcessArtworkWorkflow."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client

# Add parent directory to path so we can import workflows
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows.process_artwork import ProcessArtworkWorkflow

# Load environment variables
load_dotenv()

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "claude-draws-queue"


async def main():
    """Test the artwork processing workflow."""
    # Get test image path from command line or use default
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        # Use the existing test image
        image_path = str(Path(__file__).parent.parent / "downloads" / "kidpix-1760288744.png")

    if not Path(image_path).exists():
        print(f"Error: Image file not found: {image_path}")
        print(f"\nUsage: {sys.argv[0]} [path/to/image.png]")
        sys.exit(1)

    print(f"Testing ProcessArtworkWorkflow with image: {image_path}")
    print(f"Connecting to Temporal at: {TEMPORAL_HOST}")
    print()

    # Connect to Temporal
    client = await Client.connect(TEMPORAL_HOST)

    # Start the workflow
    print("Starting workflow...")
    result = await client.execute_workflow(
        ProcessArtworkWorkflow.run,
        args=[
            image_path,
            "Test Artwork (Workflow Test)",
            "https://reddit.com/r/test/comments/test123",
        ],
        id=f"test-workflow-{int(asyncio.get_event_loop().time())}",
        task_queue=TASK_QUEUE,
    )

    print()
    print("=" * 60)
    print("✓ Workflow completed successfully!")
    print(f"Artwork URL: {result}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
