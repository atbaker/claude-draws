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
    required=True,
    help='Prompt to send to Claude for Chrome'
)
def start(cdp_url: str, prompt: str):
    """Connect to a running Chrome browser and submit a prompt to Claude."""
    click.echo(f"Connecting to Chrome at {cdp_url}...")
    click.echo(f"Submitting prompt: {prompt}")
    submit_claude_prompt(cdp_url, prompt)
    click.echo("Done!")


if __name__ == '__main__':
    cli()
