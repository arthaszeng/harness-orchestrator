"""Session context for intra-phase continuity.

Each pipeline phase (plan/build/eval/ship) maintains a lightweight JSON file
updated at Step boundaries.  This provides L1 (session-level) memory in the
three-layer memory model: L1 session → L2 handoff → L3 Memverse.
"""

from __future__ import annotations

__all__ = [
    "SessionContext",
    "SessionDecision",
    "SessionErrorFix",
    "save_session_context",
    "load_session_context",
]

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SESSION_CONTEXT_SCHEMA_VERSION = 1
_SESSION_CONTEXT_FILENAME = "session-context.json"

SessionPhase = Literal["plan", "build", "eval", "ship"]


class SessionDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    what: str = Field(default="", max_length=400)
    why: str = Field(default="", max_length=400)


class SessionErrorFix(BaseModel):
    model_config = ConfigDict(extra="ignore")
    error: str = Field(default="", max_length=400)
    fix: str = Field(default="", max_length=400)
    step: str = Field(default="", max_length=20)


_WORKING_SET_MAX = 20
_DECISIONS_MAX = 10
_ERRORS_MAX = 10
_OPEN_LOOPS_MAX = 10


class SessionContext(BaseModel):
    """Lightweight intra-phase state updated at each Step boundary."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = SESSION_CONTEXT_SCHEMA_VERSION
    task_id: str = Field(default="", max_length=60)
    current_phase: SessionPhase = "build"
    current_step: str = Field(default="", max_length=20)
    updated_at: str = Field(default="", max_length=64)
    current_state: str = Field(default="", max_length=400)
    next_step: str = Field(default="", max_length=400)
    working_set: list[str] = Field(default_factory=list)
    active_constraints: list[str] = Field(default_factory=list)
    recent_decisions: list[SessionDecision] = Field(default_factory=list)
    errors_and_fixes: list[SessionErrorFix] = Field(default_factory=list)
    open_loops: list[str] = Field(default_factory=list)

    @field_validator("working_set", mode="before")
    @classmethod
    def _cap_working_set(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(x)[:400] for x in v[:_WORKING_SET_MAX] if x]

    @field_validator("active_constraints", mode="before")
    @classmethod
    def _cap_constraints(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(x)[:400] for x in v[:_WORKING_SET_MAX] if x]

    @field_validator("recent_decisions", mode="before")
    @classmethod
    def _cap_decisions(cls, v: object) -> list:
        if not isinstance(v, list):
            return []
        return v[:_DECISIONS_MAX]

    @field_validator("errors_and_fixes", mode="before")
    @classmethod
    def _cap_errors(cls, v: object) -> list:
        if not isinstance(v, list):
            return []
        return v[:_ERRORS_MAX]

    @field_validator("open_loops", mode="before")
    @classmethod
    def _cap_open_loops(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(x)[:400] for x in v[:_OPEN_LOOPS_MAX] if x]


def save_session_context(task_dir: Path, ctx: SessionContext) -> Path:
    """Atomically write session context to *task_dir*. Returns written path."""
    task_dir.mkdir(parents=True, exist_ok=True)
    if not ctx.updated_at:
        ctx = ctx.model_copy(
            update={"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        )
    path = task_dir / _SESSION_CONTEXT_FILENAME
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(ctx.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_session_context(task_dir: Path) -> SessionContext | None:
    """Load session context. Returns None on missing/corrupt."""
    path = task_dir / _SESSION_CONTEXT_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        warnings.warn(f"Corrupt session context at {path} ({type(exc).__name__})", stacklevel=2)
        return None
    if not isinstance(raw, dict):
        warnings.warn(f"Corrupt session context at {path} (not a JSON object)", stacklevel=2)
        return None
    try:
        return SessionContext.model_validate(raw)
    except ValidationError as exc:
        warnings.warn(f"Invalid session context at {path} ({exc})", stacklevel=2)
        return None
