"""Core task lifecycle operations (done / archive).

Filesystem-backed helpers shared by CLI commands and internal callers
(e.g. ``BranchLifecycleManager.preflight_repo_state``) without a
``core → commands`` reverse dependency.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from harness.core.state import TaskState
from harness.core.workflow_state import (
    load_workflow_state,
    sync_task_state,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskOpResult:
    """Structured result for task lifecycle operations."""

    ok: bool
    code: str
    message: str


def _resolve_agents_dir(agents_dir: Path) -> Path:
    """Follow symlinks so archive operations work in worktrees."""
    return agents_dir.resolve()


def _task_identity_check(agents_dir: Path, task_key: str) -> TaskOpResult | None:
    """Return a failure result if *task_key* is invalid, else ``None``."""
    from harness.core.workflow_state import _resolver_for_agents_dir

    resolver = _resolver_for_agents_dir(agents_dir)
    if not resolver.is_valid_task_key(task_key):
        return TaskOpResult(ok=False, code="INVALID_TASK_KEY", message=f"invalid task ID: {task_key}")
    return None


def mark_task_done(agents_dir: Path, task_key: str) -> TaskOpResult:
    """Set a task's phase to ``done`` and clear blockers."""
    agents_dir = _resolve_agents_dir(agents_dir)
    bad = _task_identity_check(agents_dir, task_key)
    if bad:
        return bad

    task_dir = agents_dir / "tasks" / task_key
    if not task_dir.is_dir():
        return TaskOpResult(ok=False, code="TASK_DIR_NOT_FOUND", message=f"task directory not found: {task_key}")

    ws = load_workflow_state(task_dir)
    if ws and ws.phase == TaskState.DONE:
        return TaskOpResult(ok=True, code="ALREADY_DONE", message=f"task {task_key} is already done")

    try:
        sync_task_state(task_dir, phase=TaskState.DONE, blocker={"kind": "", "reason": ""})
    except ValueError as exc:
        return TaskOpResult(ok=False, code="STATE_TRANSITION_FAILED", message=str(exc))

    return TaskOpResult(ok=True, code="MARKED_DONE", message=f"task {task_key} marked as done")


def archive_task(agents_dir: Path, task_key: str, *, force: bool = False) -> TaskOpResult:
    """Move a task directory from ``tasks/`` to ``archive/``."""
    agents_dir = _resolve_agents_dir(agents_dir)
    bad = _task_identity_check(agents_dir, task_key)
    if bad:
        return bad

    tasks_dir = agents_dir / "tasks"
    source = (tasks_dir / task_key).resolve()
    if not source.is_relative_to(tasks_dir.resolve()):
        return TaskOpResult(ok=False, code="INVALID_TASK_KEY", message=f"task path escapes sandbox: {task_key}")
    if not source.is_dir():
        return TaskOpResult(ok=False, code="TASK_DIR_NOT_FOUND", message=f"task directory not found: {task_key}")

    archive_dir = agents_dir / "archive"
    target = archive_dir / task_key
    if target.exists():
        return TaskOpResult(
            ok=False, code="ARCHIVE_TARGET_EXISTS", message=f"archive target already exists: archive/{task_key}",
        )

    if not force:
        ws = load_workflow_state(source)
        if ws is None:
            return TaskOpResult(
                ok=False,
                code="NO_WORKFLOW_STATE",
                message=f"no workflow-state.json for {task_key} (use force=True to skip)",
            )
        if ws.phase != TaskState.DONE:
            return TaskOpResult(
                ok=False,
                code="NOT_DONE",
                message=f"task {task_key} phase is '{ws.phase.value}', not 'done' (use force=True to skip)",
            )

    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    except OSError as exc:
        return TaskOpResult(ok=False, code="ARCHIVE_MOVE_FAILED", message=f"failed to move {task_key}: {exc}")

    return TaskOpResult(ok=True, code="ARCHIVED", message=f"archived {task_key} → archive/{task_key}")
