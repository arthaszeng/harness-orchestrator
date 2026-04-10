"""harness handoff write/read — structured cross-stage handoff CLI."""

from __future__ import annotations

import json
import sys

import typer

from harness.commands._resolve import resolve_task_dir_readonly, resolve_task_dir_strict
from harness.core.ui import get_ui

_EXIT_VALIDATION = 1
_EXIT_NOT_FOUND = 2


def run_handoff_write(*, task: str) -> None:
    """Read JSON from stdin, validate as StageHandoff, and save."""
    from pydantic import ValidationError

    from harness.core.handoff import StageHandoff, save_handoff
    from harness.core.workflow_state import load_workflow_state

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
        handoff = StageHandoff.model_validate(payload)
    except ValidationError as exc:
        ui.error(f"validation failed: {exc}")
        raise typer.Exit(code=_EXIT_VALIDATION)

    task_dir = resolve_task_dir_strict(task)
    path = save_handoff(task_dir, handoff)

    ws = load_workflow_state(task_dir)
    if ws is not None:
        ws.handoff_summary = handoff.summary[:2000]
        ws.save(task_dir)

    ui.info(f"handoff written: {path.name}")


def run_handoff_read(
    *,
    task: str,
    phase: str | None = None,
    as_json: bool = False,
) -> None:
    """Read a handoff file and print to stdout."""
    from harness.core.handoff import (
        PHASE_ORDER,
        load_handoff,
        load_latest_handoff,
    )

    ui = get_ui()
    task_dir = resolve_task_dir_readonly(task)
    if task_dir is None:
        ui.error(f"task directory not found for '{task}'")
        raise typer.Exit(code=_EXIT_NOT_FOUND)

    if phase:
        if phase not in PHASE_ORDER:
            raise typer.BadParameter(f"phase must be one of: {', '.join(PHASE_ORDER)}")
        result = load_handoff(task_dir, phase)  # type: ignore[arg-type]
    else:
        result = load_latest_handoff(task_dir)

    if result is None:
        label = f"phase={phase}" if phase else "any phase"
        ui.error(f"no handoff found for {label}")
        raise typer.Exit(code=_EXIT_NOT_FOUND)

    if as_json:
        typer.echo(result.model_dump_json(indent=2))
    else:
        typer.echo(f"source_phase: {result.source_phase}")
        typer.echo(f"target_phase: {result.target_phase}")
        typer.echo(f"task_id: {result.task_id}")
        typer.echo(f"summary: {result.summary}")
        if result.working_set:
            typer.echo(f"working_set: {', '.join(result.working_set)}")
        if result.active_constraints:
            typer.echo(f"active_constraints: {', '.join(result.active_constraints)}")
        if result.resume_prompt:
            typer.echo(f"resume_prompt: {result.resume_prompt}")
