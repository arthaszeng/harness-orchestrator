"""harness task next-id / resolve — task directory queries for agents and scripts."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harness.core.workflow_state import (
    iter_task_dirs,
    load_workflow_state,
    resolve_task_dir,
    task_dir_number,
)


def run_task_next_id(*, as_json: bool = False) -> None:
    """Print the next available task-NNN identifier."""
    cwd = Path.cwd()
    agents_dir = cwd / ".harness-flow"
    dirs = iter_task_dirs(agents_dir)
    max_num = max(
        (task_dir_number(d) for d in dirs if task_dir_number(d) is not None),
        default=0,
    )
    next_num = max_num + 1
    next_id = f"task-{next_num:03d}"

    if as_json:
        typer.echo(json.dumps({
            "next_id": next_id,
            "max_existing": max_num,
            "total_task_dirs": len(dirs),
        }))
    else:
        typer.echo(next_id)


def run_task_resolve(*, task: str | None = None, as_json: bool = False) -> None:
    """Print the currently active task directory and its state."""
    import os

    cwd = Path.cwd()
    agents_dir = cwd / ".harness-flow"
    env_task_id = os.environ.get("HARNESS_TASK_ID") or None

    if task:
        resolution_source = "explicit"
    elif env_task_id:
        env_dir = resolve_task_dir(agents_dir, explicit_task_id=env_task_id)
        resolution_source = "env" if env_dir is not None else "latest_numeric"
    else:
        resolution_source = "latest_numeric"

    task_dir = resolve_task_dir(agents_dir, explicit_task_id=task or None)

    if task_dir is None:
        if as_json:
            typer.echo(json.dumps({"error": "no task directory found"}))
        else:
            typer.echo("  ✗ No task directory found", err=True)
        raise typer.Exit(1)

    tid = task_dir.name
    ws = load_workflow_state(task_dir)
    phase = ws.phase.value if ws else "unknown"
    has_plan = (task_dir / "plan.md").exists()
    has_handoff = bool(ws and ws.handoff_summary)
    blocker_data: dict | None = None
    if ws and ws.blocker and ws.blocker.reason:
        blocker_data = ws.blocker.model_dump()

    if as_json:
        rel_path = task_dir.relative_to(cwd) if task_dir.is_relative_to(cwd) else task_dir
        typer.echo(json.dumps({
            "task_id": tid,
            "task_dir": str(rel_path),
            "phase": phase,
            "has_plan": has_plan,
            "has_handoff_summary": has_handoff,
            "blocker": blocker_data,
            "resolution_source": resolution_source,
        }))
    else:
        typer.echo(tid)
