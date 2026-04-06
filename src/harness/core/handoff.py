"""Structured stage handoff contract for cross-stage context passing.

Each pipeline stage (plan → build → eval → ship) writes a compact JSON handoff
at its exit point.  The next stage reads that handoff instead of re-processing
the full upstream artifact, keeping context windows focused and enabling
reliable resume after interruption.

Handoff files live alongside other task artifacts in
``.harness-flow/tasks/task-NNN/handoff-<phase>.json``.
"""

from __future__ import annotations

__all__ = [
    "StageHandoff",
    "save_handoff",
    "load_handoff",
    "load_latest_handoff",
]

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness.core.task_identity import TASK_ID_STORAGE_PATTERN

HANDOFF_SCHEMA_VERSION = 1

HandoffPhase = Literal["plan", "build", "eval", "ship"]

PHASE_ORDER: tuple[HandoffPhase, ...] = ("plan", "build", "eval", "ship")


def _handoff_filename(phase: HandoffPhase) -> str:
    return f"handoff-{phase}.json"


class Decision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    what: str = Field(default="", max_length=400)
    why: str = Field(default="", max_length=400)
    classification: str = Field(default="", max_length=60)


class Risk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = Field(default="", max_length=400)
    mitigation: str = Field(default="", max_length=400)
    severity: str = Field(default="", max_length=30)


class OpenItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = Field(default="", max_length=400)
    owner: str = Field(default="", max_length=120)
    priority: str = Field(default="", max_length=30)


class StageHandoff(BaseModel):
    """Compact cross-stage summary written at each pipeline boundary."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = HANDOFF_SCHEMA_VERSION
    source_phase: HandoffPhase
    target_phase: HandoffPhase
    task_id: str = Field(..., pattern=TASK_ID_STORAGE_PATTERN)
    summary: str = Field(default="", max_length=2000)
    decisions: list[Decision] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    open_items: list[OpenItem] = Field(default_factory=list)
    artifacts_produced: list[str] = Field(default_factory=list)
    scope_changes: list[str] = Field(default_factory=list)
    created_at: str = Field(default="", max_length=64)


def save_handoff(task_dir: Path, handoff: StageHandoff) -> Path:
    """Write a handoff JSON file to *task_dir*.  Returns the written path.

    Creates *task_dir* if it does not exist.  OSError propagates to caller
    (consistent with ``WorkflowState.save``).
    """
    task_dir.mkdir(parents=True, exist_ok=True)
    if not handoff.created_at:
        handoff = handoff.model_copy(
            update={"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        )
    path = task_dir / _handoff_filename(handoff.source_phase)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(handoff.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_handoff(task_dir: Path, source_phase: HandoffPhase) -> StageHandoff | None:
    """Load a specific handoff file.

    Returns ``None`` on missing/corrupt/invalid content. Schema mismatches emit a
    warning but still attempt to validate known fields for forward compatibility.
    """
    path = task_dir / _handoff_filename(source_phase)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        warnings.warn(f"Corrupt handoff at {path} ({type(exc).__name__})", stacklevel=2)
        return None
    if not isinstance(raw, dict):
        warnings.warn(f"Corrupt handoff at {path} (not a JSON object)", stacklevel=2)
        return None
    if raw.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        warnings.warn(
            f"Schema version mismatch in {path} "
            f"(got {raw.get('schema_version')!r}, expected {HANDOFF_SCHEMA_VERSION})",
            stacklevel=2,
        )
    try:
        return StageHandoff.model_validate(raw)
    except ValidationError as exc:
        warnings.warn(f"Invalid handoff at {path} ({exc})", stacklevel=2)
        return None


def load_latest_handoff(task_dir: Path) -> StageHandoff | None:
    """Return the most-advanced handoff that exists and validates.

    Scans ``PHASE_ORDER`` in reverse so the latest stage wins.  Corrupted or
    invalid files are skipped silently.
    """
    for phase in reversed(PHASE_ORDER):
        result = load_handoff(task_dir, phase)
        if result is not None:
            return result
    return None
