"""CLI interface for Claude Draws."""

import click
from claudedraw.browser import submit_claude_prompt


@click.group()
def cli():
    """Claude Draws - Crowdsourced illustrations using Claude for Chrome and Kid Pix."""
    pass


@cli.command()
@click.option(
    '--cdp-url',
    required=True,
    help='Chrome DevTools Protocol URL (e.g., http://localhost:9222)'
)
@click.option(
    '--prompt',
    required=False,
    default=None,
    help='Optional prompt to send directly to Claude. If not provided, Claude will navigate Reddit for requests.'
)
def start(cdp_url: str, prompt: str | None):
    """Connect to a running Chrome browser and submit a prompt to Claude."""
    click.echo(f"Connecting to Chrome at {cdp_url}...")

    if prompt:
        click.echo(f"Direct mode: Submitting prompt: {prompt}")
    else:
        click.echo("Reddit mode: Claude will navigate to r/ClaudeDraws for requests")

    gallery_url = submit_claude_prompt(cdp_url, prompt)
    click.echo(f"\n✓ Done! Artwork available at: {gallery_url}")


if __name__ == '__main__':
    cli()
