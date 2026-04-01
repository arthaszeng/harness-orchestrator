"""Harness CLI entry point."""

from __future__ import annotations

from typing import Optional

import typer

from harness import __version__

app = typer.Typer(
    name="harness",
    help="Cursor-native multi-agent development framework",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"harness-flow {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Cursor-native multi-agent development framework."""


@app.command()
def install(
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing files and regenerate native artifacts",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Language for generated artifacts (en/zh); default from project config",
    ),
) -> None:
    """Generate native mode artifacts (.cursor/ skills, agents, rules)."""
    from harness.commands.install import run_install
    run_install(force=force, lang=lang)


@app.command()
def init(
    name: str = typer.Option("", "--name", "-n", help="Project name"),
    ci_command: str = typer.Option("", "--ci", help="CI command (e.g. make test)"),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", "-y", help="Skip interactive wizard, use defaults",
    ),
) -> None:
    """Initialize harness configuration in the current project (interactive wizard)"""
    from harness.commands.init import run_init
    run_init(name=name, ci_command=ci_command, non_interactive=non_interactive)


@app.command()
def status() -> None:
    """Show current progress and status"""
    from harness.commands.status import run_status
    run_status()


@app.command()
def update(
    check: bool = typer.Option(
        False, "--check", "-c",
        help="Only check for updates, do not install",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Force reinstall agent definitions even when already up to date",
    ),
) -> None:
    """Self-update harness, reinstall artifacts, and migrate config.

    Steps:
    1. Check PyPI for newer version and upgrade via pip
    2. Reinstall native artifacts (only after upgrade, or with --force)
    3. Check .agents/config.toml for new/deprecated keys
    """
    from harness.commands.update import run_update
    run_update(check=check, force=force)
