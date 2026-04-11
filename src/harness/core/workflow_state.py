"""Task-level canonical workflow state stored inside `.harness-flow/tasks/task-NNN/`.

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

from harness.core.config import HarnessConfig
from harness.core.state import TaskState
from harness.core.task_identity import TaskIdentityResolver

WORKFLOW_STATE_FILENAME = "workflow-state.json"
SCHEMA_VERSION = 1

_NUMERIC_TASK_DIR_RE = re.compile(r"^task-(\d+)$")


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

    task_prefix = Path(".harness-flow") / "tasks" / task_dir.name
    if ref_path.parts[:2] == (".harness-flow", "tasks"):
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
    plan_evaluation: str = Field(default="", max_length=400)
    code_evaluation: str = Field(default="", max_length=400)
    feedback_ledger: str = Field(default="", max_length=400)
    failure_patterns: str = Field(default="", max_length=400)
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
    landing: GateSnapshot = Field(default_factory=GateSnapshot)


class WorkflowBlocker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str = Field(default="", max_length=120)
    reason: str = Field(default="", max_length=800)


class WorkflowState(BaseModel):
    """Canonical per-task workflow state."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = SCHEMA_VERSION
    task_id: str = Field(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,95}$")
    branch: str = Field(default="", max_length=240)
    phase: TaskState = TaskState.IDLE
    iteration: int = Field(default=0, ge=0)
    active_plan: ActivePlanRef = Field(default_factory=ActivePlanRef)
    artifacts: ArtifactRefs = Field(default_factory=ArtifactRefs)
    gates: GateRefs = Field(default_factory=GateRefs)
    blocker: WorkflowBlocker = Field(default_factory=WorkflowBlocker)
    handoff_summary: str = Field(default="", max_length=2000)
    updated_at: str = Field(default_factory=_now_iso, max_length=64)

    def save(self, task_dir: Path) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        payload = self.model_copy(update={"updated_at": _now_iso()})
        _write_text_atomic(task_dir / WORKFLOW_STATE_FILENAME, payload.model_dump_json(indent=2))


def task_dir_number(task_dir: Path) -> int | None:
    match = _NUMERIC_TASK_DIR_RE.match(task_dir.name)
    if not match:
        return None
    return int(match.group(1))


def _resolver_for_agents_dir(agents_dir: Path) -> TaskIdentityResolver:
    try:
        cfg = HarnessConfig.load(agents_dir.parent)
        return TaskIdentityResolver.from_config(cfg)
    except Exception as exc:
        warnings.warn(
            f"failed to load task identity strategy from config ({type(exc).__name__}); "
            "falling back to default resolver",
            stacklevel=2,
        )
        return TaskIdentityResolver()


def _iter_validated_dirs(parent_dir: Path, agents_dir: Path) -> list[Path]:
    """Enumerate and sort validated task directories under *parent_dir*."""
    if not parent_dir.exists():
        return []
    resolver = _resolver_for_agents_dir(agents_dir)
    dirs = [p for p in parent_dir.iterdir() if p.is_dir() and resolver.is_valid_task_key(p.name)]
    return sorted(
        dirs,
        key=lambda p: (0, task_dir_number(p) or -1) if task_dir_number(p) is not None else (1, p.name),
    )


def iter_task_dirs(agents_dir: Path) -> list[Path]:
    return _iter_validated_dirs(agents_dir / "tasks", agents_dir)


def iter_archive_dirs(agents_dir: Path) -> list[Path]:
    return _iter_validated_dirs(agents_dir / "archive", agents_dir)


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
        resolver = _resolver_for_agents_dir(agents_dir)
        if not resolver.is_valid_task_key(name):
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
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
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
        warnings.warn(
            f"Workflow state task_id mismatch at {path} "
            f"(task_id={state.task_id!r}, dir={task_dir.name!r})",
            stacklevel=2,
        )
        return None
    return state


_VALID_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.IDLE: frozenset({
        TaskState.PLANNING,
        TaskState.BUILDING,       # hotfix fast-path
        TaskState.EVALUATING,     # standalone eval
        TaskState.BLOCKED,
    }),
    TaskState.PLANNING: frozenset({
        TaskState.CONTRACTED,
        TaskState.BUILDING,       # small tasks without formal contract
        TaskState.EVALUATING,     # plan-eval
        TaskState.BLOCKED,
        TaskState.IDLE,           # cancellation
    }),
    TaskState.CONTRACTED: frozenset({
        TaskState.BUILDING,
        TaskState.EVALUATING,     # plan-eval after contract
        TaskState.PLANNING,       # re-planning
        TaskState.BLOCKED,
        TaskState.IDLE,           # cancellation
    }),
    TaskState.BUILDING: frozenset({
        TaskState.EVALUATING,
        TaskState.BLOCKED,
        TaskState.SHIPPING,       # direct ship after build
    }),
    TaskState.EVALUATING: frozenset({
        TaskState.BUILDING,       # fix loop
        TaskState.PLANNING,       # re-plan after eval
        TaskState.SHIPPING,
        TaskState.BLOCKED,
        TaskState.DONE,
    }),
    TaskState.SHIPPING: frozenset({
        TaskState.DONE,
        TaskState.BLOCKED,
        TaskState.EVALUATING,     # ship eval ITERATE fallback
        TaskState.BUILDING,       # rebuild during ship
        TaskState.LANDING,        # PR submitted, monitoring CI
    }),
    TaskState.LANDING: frozenset({
        TaskState.DONE,           # CI green, PR merge-ready
        TaskState.BLOCKED,
        TaskState.SHIPPING,       # pushed hotfix, back to ship flow
    }),
    TaskState.DONE: frozenset({
        TaskState.IDLE,           # new task
        TaskState.PLANNING,       # follow-up iteration
        TaskState.BUILDING,       # post-done rebuild
        TaskState.EVALUATING,     # re-eval after done
    }),
    TaskState.BLOCKED: frozenset(TaskState),  # unblock to any state
}


def _validate_phase_transition(
    old_phase: TaskState,
    new_phase: TaskState,
    *,
    strict: bool = False,
) -> None:
    """Validate that a phase transition is allowed.

    When *strict* is True, raises ``ValueError`` on illegal transitions.
    Otherwise emits a warning.  Self-transitions (no-ops) are always allowed.
    """
    if old_phase == new_phase:
        return
    allowed = _VALID_TRANSITIONS.get(old_phase)
    if allowed is not None and new_phase in allowed:
        return
    msg = (
        f"Potentially illegal phase transition: {old_phase.value!r} → {new_phase.value!r}. "
        f"Allowed targets from {old_phase.value!r}: "
        f"{sorted(s.value for s in (allowed or set()))}"
    )
    if strict:
        raise ValueError(msg)
    warnings.warn(msg, stacklevel=3)


def sync_task_state(
    task_dir: Path,
    *,
    artifact_updates: dict[str, str] | None = None,
    gate_updates: dict[str, dict[str, str]] | None = None,
    phase: TaskState | None = None,
    blocker: dict[str, str] | None = None,
    handoff_summary: str | None = None,
    strict_transitions: bool = False,
) -> WorkflowState:
    """Load-merge-save task workflow state through a single entrypoint."""
    state_path = task_dir / WORKFLOW_STATE_FILENAME
    state = load_workflow_state(task_dir)
    if state is None and state_path.exists():
        warnings.warn(
            f"Rebuilding corrupt workflow-state.json at {state_path}",
            stacklevel=2,
        )
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
        _validate_phase_transition(state.phase, phase, strict=strict_transitions)
        state.phase = phase

    if blocker:
        state.blocker = WorkflowBlocker.model_validate({
            "kind": blocker.get("kind", state.blocker.kind),
            "reason": blocker.get("reason", state.blocker.reason),
        })

    if handoff_summary is not None:
        state.handoff_summary = handoff_summary[:2000]

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
    mismatch guard is skipped so that a copied ``state.json`` with a stale
    ``session_task_id`` does not block state loading.
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
        ("plan_eval", state.artifacts.plan_evaluation),
        ("code_eval", state.artifacts.code_evaluation),
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
        ("landing", state.gates.landing),
    ]
    return [
        (label, snapshot)
        for label, snapshot in pairs
        if snapshot.status != GateStatus.UNKNOWN or snapshot.reason
    ]

