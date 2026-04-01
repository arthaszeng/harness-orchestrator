"""Harness CLI entry point."""

from __future__ import annotations

from typing import Optional

import typer

from harness import __version__

app = typer.Typer(
    name="harness",
    help="Contract-driven multi-agent autonomous development orchestration",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"harness-orchestrator {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """GAN-style multi-agent autonomous development framework"""


@app.command()
def install(
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Overwrite existing files, retry CLI installations without prompts (use to fix broken installs)",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Language for agent definitions (en/zh); default from project config or UI language",
    ),
) -> None:
    """Install agent definitions to local IDE (Cursor / Codex).

    Re-run with --force to fix a broken installation:
    overwrites existing agent files, retries CLI installations,
    and re-generates native mode artifacts.
    """
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
def vision() -> None:
    """Interactively create or update project vision (.agents/vision.md)"""
    from harness.commands.vision_cmd import run_vision
    run_vision()


@app.command()
def run(
    requirement: str = typer.Argument(..., help="Requirement description"),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume from last interruption"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Show full agent output"),
) -> None:
    """Run a single development task"""
    from harness.commands.run import run_task
    run_task(requirement=requirement, resume=resume, verbose=verbose)


@app.command()
def auto(
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume from last interruption"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Show full agent output"),
) -> None:
    """Start the autonomous development loop"""
    from harness.commands.auto import run_auto
    run_auto(resume=resume, verbose=verbose)


@app.command()
def status() -> None:
    """Show current progress and status"""
    from harness.commands.status import run_status
    run_status()


@app.command()
def stop() -> None:
    """Gracefully stop the currently running task"""
    from harness.commands.stop import run_stop
    run_stop()
