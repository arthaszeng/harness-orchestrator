"""Structured stage handoff contract for cross-stage context passing.

Each pipeline stage (plan → build → eval → ship) writes a compact JSON handoff
at its exit point.  The next stage reads that handoff instead of re-processing
the full upstream artifact, keeping context windows focused and enabling
reliable resume after interruption.

Schema v2 adds :class:`ContextFootprint` (bounded ``explored_paths``,
``primary_read_files``, ``primary_touched_files``).  Schema v3 adds
``working_set``, ``active_constraints``, and ``resume_prompt`` on
:class:`StageHandoff`.  :func:`load_handoff` accepts schema versions **1**,
**2**, and **3** without emitting a version-mismatch warning.

Handoff files live alongside other task artifacts in
``.harness-flow/tasks/task-NNN/handoff-<phase>.json``.
"""

from __future__ import annotations

__all__ = [
    "ContextFootprint",
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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from harness.core.task_identity import TASK_ID_STORAGE_PATTERN

# Written by ``save_handoff``; ``load_handoff`` accepts v1–v3 payloads.
HANDOFF_SCHEMA_VERSION = 3

_SUPPORTED_HANDOFF_SCHEMA_VERSIONS: frozenset[int] = frozenset({1, 2, 3})

_CONTEXT_PATH_LIST_MAX_ITEMS = 40
_CONTEXT_PATH_MAX_CHARS = 240

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


class ContextFootprint(BaseModel):
    """Bounded exploration / touch hints so later stages reuse prior context (schema ≥ 2)."""

    model_config = ConfigDict(extra="ignore")

    explored_paths: list[str] = Field(default_factory=list)
    primary_read_files: list[str] = Field(default_factory=list)
    primary_touched_files: list[str] = Field(default_factory=list)

    @field_validator("explored_paths", "primary_read_files", "primary_touched_files", mode="before")
    @classmethod
    def _normalize_path_lists(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value[:_CONTEXT_PATH_LIST_MAX_ITEMS]:
            if isinstance(item, str) and item.strip():
                out.append(item.strip()[:_CONTEXT_PATH_MAX_CHARS])
        return out


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
    context_footprint: ContextFootprint = Field(default_factory=ContextFootprint)
    working_set: list[str] = Field(default_factory=list)
    active_constraints: list[str] = Field(default_factory=list)
    resume_prompt: str = Field(default="", max_length=500)
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
    sv = raw.get("schema_version")
    if sv not in _SUPPORTED_HANDOFF_SCHEMA_VERSIONS:
        warnings.warn(
            f"Schema version mismatch in {path} "
            f"(got {sv!r}, supported {_SUPPORTED_HANDOFF_SCHEMA_VERSIONS})",
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
