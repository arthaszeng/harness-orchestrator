"""Task-level canonical workflow state stored inside `.agents/tasks/task-NNN/`.

This module provides the machine-readable task state contract used by W1
workflow-intelligence features. The per-task file is authoritative for phase,
gate, blocker, and artifact references; session state remains a derived summary.
"""

from __future__ import annotations

import json
import re
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
        (task_dir / WORKFLOW_STATE_FILENAME).write_text(
            payload.model_dump_json(indent=2),
            encoding="utf-8",
        )


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
    session_task_id: str | None = None,
) -> Path | None:
    tasks_dir = agents_dir / "tasks"
    if explicit_task_id:
        explicit_dir = tasks_dir / explicit_task_id
        return explicit_dir if explicit_dir.is_dir() else None
    if session_task_id:
        session_dir = tasks_dir / session_task_id
        if session_dir.is_dir():
            return session_dir
    ordered = iter_task_dirs(agents_dir)
    return ordered[-1] if ordered else None


def load_workflow_state(task_dir: Path) -> WorkflowState | None:
    path = task_dir / WORKFLOW_STATE_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("schema_version") != SCHEMA_VERSION:
        return None
    try:
        state = WorkflowState.model_validate(raw)
    except ValidationError:
        return None
    if state.task_id != task_dir.name:
        return None
    return state


def load_current_workflow_state(
    agents_dir: Path,
    *,
    explicit_task_id: str | None = None,
    session_task_id: str | None = None,
) -> tuple[Path | None, WorkflowState | None]:
    task_dir = resolve_task_dir(
        agents_dir,
        explicit_task_id=explicit_task_id,
        session_task_id=session_task_id,
    )
    if explicit_task_id is None and session_task_id and task_dir is not None and task_dir.name != session_task_id:
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

