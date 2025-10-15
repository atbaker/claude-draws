"""CLI interface for Claude Draws."""

import asyncio
import os
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv
from temporalio.client import Client

# Add parent directory to path so we can import workflows
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()

# Temporal configuration
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "claude-draws-queue"


@click.group()
def cli():
    """Claude Draws - Crowdsourced illustrations using Claude for Chrome and Kid Pix."""
    pass


@cli.command()
@click.option(
    '--cdp-url',
    required=True,
    help='Chrome DevTools Protocol URL (e.g., ws://127.0.0.1:9222/devtools/browser/...)'
)
@click.option(
    '--continuous',
    is_flag=True,
    default=False,
    help='Run continuously for livestream mode (schedules new workflow after each completion)'
)
def start(cdp_url: str, continuous: bool):
    """Start the Claude Draws workflow."""
    click.echo("=" * 60)
    click.echo("Claude Draws - Workflow Launcher")
    click.echo("=" * 60)
    click.echo(f"\nCDP URL: {cdp_url}")
    click.echo(f"Continuous mode: {continuous}")
    click.echo(f"Temporal server: {TEMPORAL_HOST}")
    click.echo(f"Task queue: {TASK_QUEUE}\n")

    asyncio.run(start_workflow(cdp_url, continuous))


async def start_workflow(cdp_url: str, continuous: bool):
    """Connect to Temporal and start the CreateArtworkWorkflow."""
    try:
        # Connect to Temporal
        click.echo("Connecting to Temporal server...")
        client = await Client.connect(TEMPORAL_HOST)
        click.echo("✓ Connected to Temporal\n")

        # Generate workflow ID
        timestamp = int(time.time())
        workflow_id = f"claude-draws-{timestamp}"

        # Start workflow
        click.echo(f"Starting workflow: {workflow_id}")
        click.echo("This workflow will:")
        click.echo("  1. Find an open request on r/ClaudeDraws")
        click.echo("  2. Submit prompt to Claude for Chrome")
        click.echo("  3. Wait for Claude to complete the artwork")
        click.echo("  4. Process and upload to gallery")
        click.echo("  5. Post comment on Reddit with result")
        if continuous:
            click.echo("  6. Schedule next workflow run (continuous mode)")
        click.echo()

        from workflows.create_artwork import CreateArtworkWorkflow

        handle = await client.start_workflow(
            CreateArtworkWorkflow.run,
            args=[cdp_url, continuous],
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        click.echo("✓ Workflow started successfully!\n")
        click.echo(f"Workflow ID: {workflow_id}")
        click.echo(f"Temporal UI: http://localhost:8233/namespaces/default/workflows/{workflow_id}")
        click.echo()

        if continuous:
            click.echo("Running in CONTINUOUS mode:")
            click.echo("  - This workflow will schedule new workflows automatically")
            click.echo("  - Monitor progress in the Temporal UI")
            click.echo("  - To stop: Cancel the active workflow in Temporal UI")
        else:
            click.echo("Running in SINGLE mode:")
            click.echo("  - One artwork will be created")
            click.echo("  - Monitor progress in the Temporal UI")

        click.echo("\nCLI will now exit. The workflow continues running in Temporal.")
        click.echo("Check the Temporal UI link above for real-time progress.")

    except Exception as e:
        click.echo(f"\n✗ Error starting workflow: {e}", err=True)
        raise


if __name__ == '__main__':
    cli()
