#!/usr/bin/env python3
"""
Test script for the CreateArtworkWorkflow.

NOTE: This script is now deprecated. The new CreateArtworkWorkflow handles the
entire end-to-end process including browser automation to find Reddit requests.

To test the full workflow:
    uv run claudedraw start --cdp-url <url>

This test script is kept for reference but may not work as expected since
the workflow signature has changed.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from temporalio.client import Client

# Add parent directory to path so we can import workflows
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "claude-draws-queue"


async def main():
    """Test the workflow (deprecated - see note above)."""
    print("=" * 60)
    print("DEPRECATED TEST SCRIPT")
    print("=" * 60)
    print()
    print("This script is deprecated. The CreateArtworkWorkflow now handles")
    print("the entire end-to-end process including browser automation.")
    print()
    print("To test the workflow, use:")
    print("    uv run claudedraw start --cdp-url <url>")
    print()
    print("Get CDP URL from: http://localhost:9222/json")
    print("=" * 60)
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
