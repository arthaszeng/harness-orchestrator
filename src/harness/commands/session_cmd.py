"""harness session write/read — intra-phase session context CLI."""

from __future__ import annotations

import json
import sys

import typer

from harness.commands._resolve import resolve_task_dir_readonly, resolve_task_dir_strict
from harness.core.ui import get_ui

_EXIT_VALIDATION = 1
_EXIT_NOT_FOUND = 2


def run_session_write(*, task: str) -> None:
    """Read JSON from stdin, validate as SessionContext, and save."""
    from pydantic import ValidationError

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
    except ValidationError as exc:
        ui.error(f"validation failed: {exc}")
        raise typer.Exit(code=_EXIT_VALIDATION)

    task_dir = resolve_task_dir_strict(task)
    path = save_session_context(task_dir, ctx)
    ui.info(f"session context written: {path.name}")


def run_session_read(*, task: str, as_json: bool = False) -> None:
    """Read session context and print to stdout."""
    from harness.core.session_context import load_session_context

    ui = get_ui()
    task_dir = resolve_task_dir_readonly(task)
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
