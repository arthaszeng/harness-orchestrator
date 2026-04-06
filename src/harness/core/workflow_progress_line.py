"""CLI `HARNESS_PROGRESS` line — machine-readable workflow snapshot.

Separate from ``progress.py`` (progress.md narrative + human suggestions).
This module is the SSOT for TaskState → (phase slug, step/total) used by
``harness status --progress-line``.
"""

from __future__ import annotations

from harness.core.state import TaskState

PROGRESS_TOTAL = 4


def task_state_to_slug_and_step(state: TaskState) -> tuple[str, int, int]:
    """Return ``(phase_slug, step, total)`` for HARNESS_PROGRESS; *total* is fixed at 4."""
    total = PROGRESS_TOTAL
    if state in (TaskState.IDLE, TaskState.PLANNING):
        return "plan", 1, total
    if state in (TaskState.CONTRACTED, TaskState.BUILDING):
        return "build", 2, total
    if state == TaskState.EVALUATING:
        return "eval", 3, total
    if state == TaskState.SHIPPING:
        return "ship", 4, total
    if state == TaskState.DONE:
        return "plan", 1, total
    if state == TaskState.BLOCKED:
        return "eval", 3, total
    return "plan", 1, total


def format_harness_progress_line(*, phase: TaskState) -> str:
    """Single stdout line: ``HARNESS_PROGRESS step=… phase=… next=…``."""
    from harness.i18n import t

    slug, step, total = task_state_to_slug_and_step(phase)
    key = f"progress_line.next.{phase.value}"
    nxt = t(key)
    if nxt == key:
        nxt = t("progress_line.next.fallback")
    safe_next = nxt.replace('"', "'")
    return (
        f"HARNESS_PROGRESS step={step}/{total} phase={slug} next={safe_next}"
    )
