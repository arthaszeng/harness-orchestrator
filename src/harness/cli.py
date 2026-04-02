"""Harness CLI entry point."""

from __future__ import annotations

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
def init(
    name: str = typer.Option("", "--name", "-n", help="Project name"),
    ci_command: str = typer.Option("", "--ci", help="CI command (e.g. make test)"),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", "-y", help="Skip interactive wizard, use defaults",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Skip wizard and regenerate artifacts from existing config",
    ),
) -> None:
    """Initialize harness in the current project (interactive wizard)."""
    from harness.commands.init import run_init
    run_init(name=name, ci_command=ci_command, non_interactive=non_interactive, force=force)


@app.command()
def gate(
    task: str = typer.Option(
        "", "--task", "-t",
        help="Explicit task ID (e.g. task-001). Auto-detects if omitted.",
    ),
) -> None:
    """Check ship-readiness gates for the current task"""
    from harness.commands.gate import run_gate
    run_gate(task=task or None)


@app.command()
def status() -> None:
    """Show current progress and status"""
    from harness.commands.status import run_status
    run_status()


@app.command(name="save-eval")
def save_eval(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    verdict: str = typer.Option(
        "PASS", "--verdict",
        help="Evaluation verdict: PASS or ITERATE",
    ),
    score: float = typer.Option(
        0.0, "--score",
        help="Weighted average score (0-10)",
    ),
    body: str = typer.Option(
        "", "--body",
        help="Full evaluation body (markdown). If empty, generates minimal template.",
    ),
) -> None:
    """Save evaluation results to task directory (programmatic artifact write)."""
    from harness.commands.artifact import run_save_eval
    run_save_eval(task=task, verdict=verdict, score=score, body=body)


@app.command(name="save-build-log")
def save_build_log(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    body: str = typer.Option(
        "", "--body",
        help="Build log content. If empty, reads from stdin.",
    ),
) -> None:
    """Save build log to task directory (programmatic artifact write)."""
    from harness.commands.artifact import run_save_build_log
    run_save_build_log(task=task, body=body)


@app.command(name="save-feedback-ledger")
def save_feedback_ledger(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    body: str = typer.Option(
        "", "--body",
        help="Feedback ledger JSONL content. If empty, reads from stdin.",
    ),
) -> None:
    """Save feedback-ledger.jsonl to task directory (programmatic artifact write)."""
    from harness.commands.artifact import run_save_feedback_ledger
    run_save_feedback_ledger(task=task, body=body)


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
