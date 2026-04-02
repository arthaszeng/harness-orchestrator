"""Task-level canonical workflow state stored inside `.agents/tasks/task-NNN/`.

This module provides the machine-readable task state contract used by W1
workflow-intelligence features. The per-task file is authoritative for phase,
gate, blocker, and artifact references; session state remains a derived summary.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness.core.state import TaskState

WORKFLOW_STATE_FILENAME = "workflow-state.json"
SCHEMA_VERSION = 1

_TASK_DIR_RE = re.compile(r"^task-(\d+)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _normalize_artifact_ref(task_dir: Path, ref: str) -> str:
    ref_path = Path(ref)
    if ref_path.is_absolute() or ".." in ref_path.parts:
        raise ValueError(f"artifact ref must stay inside task dir: {ref}")

    task_prefix = Path(".agents") / "tasks" / task_dir.name
    if ref_path.parts[:2] == (".agents", "tasks"):
        if len(ref_path.parts) < 4 or ref_path.parts[:3] != task_prefix.parts:
            raise ValueError(f"artifact ref must point to {task_dir.name}: {ref}")
        return ref_path.as_posix()

    return (task_prefix / ref_path).as_posix()


class GateStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    PASS = "pass"
    BLOCKED = "blocked"


class ActivePlanRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=240)


class ArtifactRefs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plan: str = Field(default="", max_length=400)
    build_log: str = Field(default="", max_length=400)
    evaluation: str = Field(default="", max_length=400)
    feedback_ledger: str = Field(default="", max_length=400)
    ship_metrics: str = Field(default="", max_length=400)
    handoff: str = Field(default="", max_length=400)


class GateSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: GateStatus = GateStatus.UNKNOWN
    reason: str = Field(default="", max_length=400)
    updated_at: str = Field(default="", max_length=64)


class GateRefs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plan_review: GateSnapshot = Field(default_factory=GateSnapshot)
    evaluation: GateSnapshot = Field(default_factory=GateSnapshot)
    ship_readiness: GateSnapshot = Field(default_factory=GateSnapshot)


class WorkflowBlocker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str = Field(default="", max_length=120)
    reason: str = Field(default="", max_length=800)


class WorkflowState(BaseModel):
    """Canonical per-task workflow state."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = SCHEMA_VERSION
    task_id: str = Field(..., pattern=r"^task-\d+$")
    branch: str = Field(default="", max_length=240)
    phase: TaskState = TaskState.IDLE
    iteration: int = Field(default=0, ge=0)
    active_plan: ActivePlanRef = Field(default_factory=ActivePlanRef)
    artifacts: ArtifactRefs = Field(default_factory=ArtifactRefs)
    gates: GateRefs = Field(default_factory=GateRefs)
    blocker: WorkflowBlocker = Field(default_factory=WorkflowBlocker)
    updated_at: str = Field(default_factory=_now_iso, max_length=64)

    def save(self, task_dir: Path) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        payload = self.model_copy(update={"updated_at": _now_iso()})
        _write_text_atomic(task_dir / WORKFLOW_STATE_FILENAME, payload.model_dump_json(indent=2))


def task_dir_number(task_dir: Path) -> int | None:
    match = _TASK_DIR_RE.match(task_dir.name)
    if not match:
        return None
    return int(match.group(1))


def iter_task_dirs(agents_dir: Path) -> list[Path]:
    tasks_dir = agents_dir / "tasks"
    if not tasks_dir.exists():
        return []
    task_dirs = [p for p in tasks_dir.iterdir() if p.is_dir() and task_dir_number(p) is not None]
    return sorted(task_dirs, key=lambda p: task_dir_number(p) or -1)


def resolve_task_dir(
    agents_dir: Path,
    *,
    explicit_task_id: str | None = None,
    env_task_id: str | None = None,
    session_task_id: str | None = None,
) -> Path | None:
    """Resolve the active task directory.

    Priority: explicit_task_id → env_task_id → session_task_id → latest numeric.
    ``env_task_id`` defaults to ``os.environ.get("HARNESS_TASK_ID")`` when
    ``None`` is passed by the caller.
    """
    tasks_dir = agents_dir / "tasks"
    if env_task_id is None:
        env_task_id = os.environ.get("HARNESS_TASK_ID") or None

    def _safe_child(name: str) -> Path | None:
        """Resolve *name* under tasks_dir, rejecting path-traversal attempts."""
        if not _TASK_DIR_RE.match(name):
            return None
        candidate = (tasks_dir / name).resolve()
        if not candidate.is_relative_to(tasks_dir.resolve()):
            return None
        return candidate if candidate.is_dir() else None

    if explicit_task_id:
        return _safe_child(explicit_task_id)
    if env_task_id:
        result = _safe_child(env_task_id)
        if result:
            return result
    if session_task_id:
        result = _safe_child(session_task_id)
        if result:
            return result
    ordered = iter_task_dirs(agents_dir)
    return ordered[-1] if ordered else None


def load_workflow_state(task_dir: Path) -> WorkflowState | None:
    """Load workflow state, returning ``None`` on any failure with a warning."""
    path = task_dir / WORKFLOW_STATE_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warnings.warn(
            f"Corrupt workflow state at {path} ({type(exc).__name__})",
            stacklevel=2,
        )
        return None
    if not isinstance(raw, dict):
        warnings.warn(f"Corrupt workflow state at {path} (not a JSON object)", stacklevel=2)
        return None
    if raw.get("schema_version") != SCHEMA_VERSION:
        warnings.warn(
            f"Schema version mismatch in {path} "
            f"(got {raw.get('schema_version')!r}, expected {SCHEMA_VERSION})",
            stacklevel=2,
        )
    try:
        state = WorkflowState.model_validate(raw)
    except ValidationError as exc:
        warnings.warn(f"Invalid workflow state at {path} ({exc})", stacklevel=2)
        return None
    if state.task_id != task_dir.name:
        return None
    return state


def sync_task_state(
    task_dir: Path,
    *,
    artifact_updates: dict[str, str] | None = None,
    gate_updates: dict[str, dict[str, str]] | None = None,
    phase: TaskState | None = None,
    blocker: dict[str, str] | None = None,
) -> WorkflowState:
    """Load-merge-save task workflow state through a single entrypoint."""
    state_path = task_dir / WORKFLOW_STATE_FILENAME
    state = load_workflow_state(task_dir)
    if state is None and state_path.exists():
        raise ValueError("existing workflow-state.json is invalid")
    if state is None:
        state = WorkflowState(task_id=task_dir.name)

    if artifact_updates:
        unknown_artifact_keys = [key for key in artifact_updates if not hasattr(state.artifacts, key)]
        if unknown_artifact_keys:
            keys = ", ".join(sorted(unknown_artifact_keys))
            raise ValueError(f"unknown artifact_updates keys: {keys}")
        for key, value in artifact_updates.items():
            setattr(state.artifacts, key, _normalize_artifact_ref(task_dir, value))

    if gate_updates:
        unknown_gate_keys = [key for key in gate_updates if not hasattr(state.gates, key)]
        if unknown_gate_keys:
            keys = ", ".join(sorted(unknown_gate_keys))
            raise ValueError(f"unknown gate_updates keys: {keys}")
        for key, payload in gate_updates.items():
            current = getattr(state.gates, key)
            update = {
                "status": payload.get("status", current.status),
                "reason": payload.get("reason", current.reason),
                "updated_at": payload.get("updated_at", _now_iso()),
            }
            setattr(state.gates, key, GateSnapshot.model_validate(update))

    if phase is not None:
        state.phase = phase

    if blocker:
        state.blocker = WorkflowBlocker.model_validate({
            "kind": blocker.get("kind", state.blocker.kind),
            "reason": blocker.get("reason", state.blocker.reason),
        })

    state.save(task_dir)
    return state


def load_current_workflow_state(
    agents_dir: Path,
    *,
    explicit_task_id: str | None = None,
    env_task_id: str | None = None,
    session_task_id: str | None = None,
) -> tuple[Path | None, WorkflowState | None]:
    """Load workflow state for the currently active task.

    When *explicit_task_id* or *env_task_id* (including ``HARNESS_TASK_ID``)
    resolves to a directory, that result is authoritative — the session
    mismatch guard is skipped so that worktree-copied ``state.json`` with
    a stale ``session_task_id`` does not block state loading.
    """
    if env_task_id is None:
        env_task_id = os.environ.get("HARNESS_TASK_ID") or None
    task_dir = resolve_task_dir(
        agents_dir,
        explicit_task_id=explicit_task_id,
        env_task_id=env_task_id,
        session_task_id=session_task_id,
    )
    authoritative_hit = (
        (explicit_task_id and task_dir is not None and task_dir.name == explicit_task_id)
        or (env_task_id and task_dir is not None and task_dir.name == env_task_id)
    )
    if not authoritative_hit and session_task_id and task_dir is not None and task_dir.name != session_task_id:
        return None, None
    if task_dir is None:
        return None, None
    return task_dir, load_workflow_state(task_dir)


def artifact_pairs(state: WorkflowState) -> list[tuple[str, str]]:
    pairs = [
        ("plan", state.artifacts.plan),
        ("build", state.artifacts.build_log),
        ("evaluation", state.artifacts.evaluation),
        ("feedback", state.artifacts.feedback_ledger),
        ("ship", state.artifacts.ship_metrics),
        ("handoff", state.artifacts.handoff),
    ]
    return [(label, value) for label, value in pairs if value]


def gate_pairs(state: WorkflowState) -> list[tuple[str, GateSnapshot]]:
    pairs = [
        ("plan_review", state.gates.plan_review),
        ("evaluation", state.gates.evaluation),
        ("ship_readiness", state.gates.ship_readiness),
    ]
    return [
        (label, snapshot)
        for label, snapshot in pairs
        if snapshot.status != GateStatus.UNKNOWN or snapshot.reason
    ]

