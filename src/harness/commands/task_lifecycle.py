"""harness task list / archive / done — task lifecycle management commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harness.core.task_ops import archive_task, mark_task_done
from harness.core.workflow_state import (
    iter_archive_dirs,
    iter_task_dirs,
    load_workflow_state,
)


def _task_summary(task_dir: Path, source: str) -> dict:
    """Build a summary dict for one task directory."""
    ws = load_workflow_state(task_dir)
    phase = ws.phase.value if ws else "unknown"

    gates: dict[str, str] = {}
    if ws:
        for label in ("plan_review", "evaluation", "ship_readiness"):
            snap = getattr(ws.gates, label, None)
            if snap and snap.status.value != "unknown":
                gates[label] = snap.status.value

    artifact_count = sum(1 for f in task_dir.iterdir() if f.is_file()) if task_dir.exists() else 0

    return {
        "task_id": task_dir.name,
        "phase": phase,
        "source": source,
        "gates": gates,
        "artifact_count": artifact_count,
    }


def run_task_list(
    *,
    phase_filter: str = "",
    include_archived: bool = False,
    as_json: bool = False,
) -> None:
    """List tasks with phase, gates, and artifact count."""
    cwd = Path.cwd()
    agents_dir = cwd / ".harness-flow"

    entries: list[dict] = []
    for td in iter_task_dirs(agents_dir):
        entries.append(_task_summary(td, "tasks"))

    if include_archived:
        for td in iter_archive_dirs(agents_dir):
            entries.append(_task_summary(td, "archive"))

    if phase_filter:
        allowed = {p.strip().lower() for p in phase_filter.split(",")}
        entries = [e for e in entries if e["phase"] in allowed]

    if as_json:
        typer.echo(json.dumps(entries, indent=2))
        return

    if not entries:
        typer.echo("  No tasks found.", err=True)
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(
        title="Tasks",
        show_header=True,
        header_style="bold",
        border_style="dim",
        padding=(0, 1),
    )
    table.add_column("Task", min_width=10)
    table.add_column("Phase", min_width=10)
    table.add_column("Source", min_width=7)
    table.add_column("Gates", min_width=15)
    table.add_column("Files", justify="right", min_width=5)

    for entry in entries:
        gates_str = ", ".join(f"{k}={v}" for k, v in entry["gates"].items()) if entry["gates"] else "—"
        table.add_row(
            entry["task_id"],
            entry["phase"],
            entry["source"],
            gates_str,
            str(entry["artifact_count"]),
        )

    console = Console(stderr=True)
    console.print(table)


def run_task_archive(*, task: str, force: bool = False) -> None:
    """Move a done task from tasks/ to archive/."""
    cwd = Path.cwd()
    agents_dir = cwd / ".harness-flow"

    if not (agents_dir / "tasks" / task / "plan.md").exists():
        typer.echo(f"  ⚠ Warning: {task}/plan.md not found", err=True)

    result = archive_task(agents_dir, task, force=force)
    if result.ok:
        typer.echo(f"  ✓ {result.message}", err=True)
    else:
        typer.echo(f"  ✗ {result.message}", err=True)
        raise typer.Exit(1)


def run_task_done(*, task: str) -> None:
    """Transition a task to phase=done and clear blockers."""
    result = mark_task_done(Path.cwd() / ".harness-flow", task)
    if result.ok:
        typer.echo(f"  ✓ {result.message}", err=True)
    else:
        typer.echo(f"  ✗ {result.message}", err=True)
        raise typer.Exit(1)
