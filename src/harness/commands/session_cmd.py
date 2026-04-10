"""harness session write/read — intra-phase session context CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from harness.core.ui import get_ui

_EXIT_VALIDATION = 1
_EXIT_NOT_FOUND = 2


def _resolve_task_dir_strict(task: str) -> Path:
    """Resolve task dir, creating if needed."""
    from harness.core.config import HarnessConfig
    from harness.core.task_identity import TaskIdentityResolver

    cfg = HarnessConfig.load(Path.cwd())
    resolver = TaskIdentityResolver.from_config(cfg)
    if not resolver.is_valid_task_key(task):
        raise typer.BadParameter(
            f"Invalid task ID '{task}' for strategy '{resolver.strategy}'"
        )
    agents_dir = Path.cwd() / ".harness-flow"
    task_dir = (agents_dir / "tasks" / task).resolve()
    if not task_dir.is_relative_to((agents_dir / "tasks").resolve()):
        raise typer.BadParameter(f"Invalid task ID '{task}': path traversal detected")
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def _resolve_task_dir_readonly(task: str) -> Path | None:
    """Resolve task dir without creating. Returns None if absent."""
    from harness.core.config import HarnessConfig
    from harness.core.task_identity import TaskIdentityResolver

    cfg = HarnessConfig.load(Path.cwd())
    resolver = TaskIdentityResolver.from_config(cfg)
    if not resolver.is_valid_task_key(task):
        raise typer.BadParameter(
            f"Invalid task ID '{task}' for strategy '{resolver.strategy}'"
        )
    agents_dir = Path.cwd() / ".harness-flow"
    task_dir = (agents_dir / "tasks" / task).resolve()
    if not task_dir.is_relative_to((agents_dir / "tasks").resolve()):
        raise typer.BadParameter(f"Invalid task ID '{task}': path traversal detected")
    return task_dir if task_dir.is_dir() else None


def run_session_write(*, task: str) -> None:
    """Read JSON from stdin, validate as SessionContext, and save."""
    from harness.core.session_context import SessionContext, save_session_context

    ui = get_ui()

    if sys.stdin.isatty():
        ui.error("no input on stdin (expected JSON)")
        raise typer.Exit(code=_EXIT_VALIDATION)

    raw_text = sys.stdin.read().strip()
    if not raw_text:
        ui.error("empty stdin")
        raise typer.Exit(code=_EXIT_VALIDATION)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        ui.error(f"invalid JSON: {exc}")
        raise typer.Exit(code=_EXIT_VALIDATION)

    if not isinstance(payload, dict):
        ui.error("expected a JSON object")
        raise typer.Exit(code=_EXIT_VALIDATION)

    try:
        ctx = SessionContext.model_validate(payload)
    except Exception as exc:
        ui.error(f"validation failed: {exc}")
        raise typer.Exit(code=_EXIT_VALIDATION)

    task_dir = _resolve_task_dir_strict(task)
    path = save_session_context(task_dir, ctx)
    ui.info(f"session context written: {path.name}")


def run_session_read(*, task: str, as_json: bool = False) -> None:
    """Read session context and print to stdout."""
    from harness.core.session_context import load_session_context

    ui = get_ui()
    task_dir = _resolve_task_dir_readonly(task)
    if task_dir is None:
        ui.error(f"task directory not found for '{task}'")
        raise typer.Exit(code=_EXIT_NOT_FOUND)

    ctx = load_session_context(task_dir)
    if ctx is None:
        ui.error("no session context found")
        raise typer.Exit(code=_EXIT_NOT_FOUND)

    if as_json:
        typer.echo(ctx.model_dump_json(indent=2))
    else:
        typer.echo(f"phase: {ctx.current_phase}")
        typer.echo(f"step: {ctx.current_step}")
        typer.echo(f"state: {ctx.current_state}")
        typer.echo(f"next: {ctx.next_step}")
        if ctx.working_set:
            typer.echo(f"working_set: {', '.join(ctx.working_set)}")
        if ctx.open_loops:
            typer.echo(f"open_loops: {', '.join(ctx.open_loops)}")
