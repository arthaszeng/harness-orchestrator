"""harness task list / archive / done — task lifecycle management commands."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer

from harness.core.state import TaskState
from harness.core.task_identity import TaskIdentityResolver
from harness.core.workflow_state import (
    iter_task_dirs,
    load_workflow_state,
    sync_task_state,
    task_dir_number,
)


def _resolver_for_cwd() -> TaskIdentityResolver:
    from harness.core.config import HarnessConfig

    try:
        cfg = HarnessConfig.load(Path.cwd())
        return TaskIdentityResolver.from_config(cfg)
    except Exception:
        return TaskIdentityResolver()


def iter_archive_dirs(agents_dir: Path) -> list[Path]:
    """Enumerate validated task directories under archive/, sorted like iter_task_dirs."""
    archive_dir = agents_dir / "archive"
    if not archive_dir.exists():
        return []
    try:
        from harness.core.config import HarnessConfig

        cfg = HarnessConfig.load(agents_dir.parent)
        resolver = TaskIdentityResolver.from_config(cfg)
    except Exception:
        resolver = TaskIdentityResolver()
    dirs = [p for p in archive_dir.iterdir() if p.is_dir() and resolver.is_valid_task_key(p.name)]
    return sorted(
        dirs,
        key=lambda p: (0, task_dir_number(p) or -1) if task_dir_number(p) is not None else (1, p.name),
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
    tasks_dir = agents_dir / "tasks"
    archive_dir = agents_dir / "archive"

    resolver = _resolver_for_cwd()
    if not resolver.is_valid_task_key(task):
        typer.echo(f"  ✗ Invalid task ID: {task}", err=True)
        raise typer.Exit(1)

    source = tasks_dir / task
    if not source.is_relative_to(tasks_dir):
        typer.echo(f"  ✗ Invalid task path: {task}", err=True)
        raise typer.Exit(1)

    if not source.is_dir():
        typer.echo(f"  ✗ Task directory not found: {task}", err=True)
        raise typer.Exit(1)

    target = archive_dir / task
    if target.exists():
        typer.echo(f"  ✗ Archive target already exists: {target.relative_to(cwd)}", err=True)
        raise typer.Exit(1)

    ws = load_workflow_state(source)
    if not force:
        if ws is None:
            typer.echo(f"  ✗ No workflow-state.json found for {task} (use --force to skip)", err=True)
            raise typer.Exit(1)
        if ws.phase != TaskState.DONE:
            typer.echo(
                f"  ✗ Task {task} is in phase '{ws.phase.value}', not 'done' (use --force to skip)",
                err=True,
            )
            raise typer.Exit(1)

    if not (source / "plan.md").exists():
        typer.echo(f"  ⚠ Warning: {task}/plan.md not found", err=True)

    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    typer.echo(f"  ✓ Archived {task} → archive/{task}", err=True)


def run_task_done(*, task: str) -> None:
    """Transition a task to phase=done and clear blockers."""
    cwd = Path.cwd()
    agents_dir = cwd / ".harness-flow"
    tasks_dir = agents_dir / "tasks"

    resolver = _resolver_for_cwd()
    if not resolver.is_valid_task_key(task):
        typer.echo(f"  ✗ Invalid task ID: {task}", err=True)
        raise typer.Exit(1)

    task_dir = tasks_dir / task
    if not task_dir.is_dir():
        typer.echo(f"  ✗ Task directory not found: {task}", err=True)
        raise typer.Exit(1)

    ws = load_workflow_state(task_dir)
    if ws and ws.phase == TaskState.DONE:
        typer.echo(f"  ✓ Task {task} is already done.", err=True)
        return

    sync_task_state(
        task_dir,
        phase=TaskState.DONE,
        blocker={"kind": "", "reason": ""},
    )
    typer.echo(f"  ✓ Task {task} marked as done.", err=True)
