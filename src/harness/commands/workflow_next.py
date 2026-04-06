"""harness workflow next — machine-readable next-step hint from workflow-state."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harness.core.state import TaskState
from harness.core.workflow_state import WORKFLOW_STATE_FILENAME, resolve_task_dir


def run_workflow_next(*, task: str | None = None) -> None:
    """Print one HARNESS_NEXT line; always exits 0 unless Typer raises."""
    cwd = Path.cwd()
    agents_dir = cwd / ".harness-flow"
    task_dir = resolve_task_dir(agents_dir, explicit_task_id=task or None)
    if task_dir is None:
        _emit(
            task="none",
            phase="unknown",
            skill="/harness-plan",
            hint="No task directory under .harness-flow/tasks",
        )
        _recovery_echo("workflow_next.recovery.no_tasks_dir")
        return

    tid = task_dir.name
    state_path = task_dir / WORKFLOW_STATE_FILENAME
    if not state_path.exists():
        _emit(
            task=tid,
            phase="unknown",
            skill="/harness-plan",
            hint="Missing workflow-state.json; run /harness-plan or create task state",
        )
        _recovery_echo("workflow_next.recovery.missing_state")
        return

    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        _emit(
            task=tid,
            phase="corrupt",
            skill="/harness-plan",
            hint="Invalid workflow-state.json; fix JSON or re-run plan",
        )
        _recovery_echo("workflow_next.recovery.corrupt")
        return

    if not isinstance(raw, dict):
        _emit(
            task=tid,
            phase="corrupt",
            skill="/harness-plan",
            hint="workflow-state.json must be a JSON object",
        )
        _recovery_echo("workflow_next.recovery.corrupt")
        return

    phase_val = raw.get("phase")
    if not isinstance(phase_val, str):
        _emit(
            task=tid,
            phase="unknown",
            skill="/harness-plan",
            hint="workflow-state phase missing or not a string",
        )
        _recovery_echo("workflow_next.recovery.unknown_phase")
        return

    try:
        phase = TaskState(phase_val)
    except ValueError:
        _emit(
            task=tid,
            phase="unknown",
            skill="/harness-plan",
            hint=f"Unknown phase value: {phase_val!r}",
        )
        _recovery_echo("workflow_next.recovery.unknown_phase")
        return

    skill, hint = _suggest(phase)
    _emit(task=tid, phase=phase.value, skill=skill, hint=hint)


def _emit(*, task: str, phase: str, skill: str, hint: str) -> None:
    safe_hint = hint.replace('"', "'")
    typer.echo(
        f'HARNESS_NEXT task={task} phase={phase} skill={skill} hint="{safe_hint}"',
    )


def _recovery_echo(i18n_key: str) -> None:
    from harness.i18n import t

    msg = t(i18n_key)
    if msg != i18n_key:
        typer.echo(msg, err=True)


def _suggest(phase: TaskState) -> tuple[str, str]:
    if phase in (TaskState.IDLE, TaskState.PLANNING):
        return "/harness-plan", "Continue planning or start a new task plan"
    if phase == TaskState.CONTRACTED:
        return "/harness-build", "Plan ready — implement contract then ship"
    if phase == TaskState.BUILDING:
        return "/harness-ship", "Implementation phase — run ship pipeline (tests, eval, gate, PR)"
    if phase == TaskState.EVALUATING:
        return "/harness-ship", "Code review / eval — continue ship workflow or fix loop"
    if phase == TaskState.SHIPPING:
        return "/harness-ship", "Delivery in progress — continue until PR URL"
    if phase == TaskState.DONE:
        return "/harness-plan", "Task done — start a new plan if needed"
    if phase == TaskState.BLOCKED:
        return "/harness-plan", "Blocked — resolve blocker then continue plan/build/ship"
    return "/harness-plan", "Continue harness workflow"
