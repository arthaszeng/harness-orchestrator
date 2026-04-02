"""Session state and checkpoint persistence."""

from __future__ import annotations

import json
import warnings
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class TaskState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    CONTRACTED = "contracted"
    BUILDING = "building"
    EVALUATING = "evaluating"
    SHIPPING = "shipping"
    DONE = "done"
    BLOCKED = "blocked"


class TaskArtifacts(BaseModel):
    spec: str = ""
    contract: str = ""
    evaluation: str = ""
    build_notes: str = ""


class TaskRecord(BaseModel):
    id: str
    requirement: str
    state: TaskState = TaskState.IDLE
    iteration: int = 0
    branch: str = ""
    started_at: str = ""
    finished_at: str = ""
    artifacts: TaskArtifacts = Field(default_factory=TaskArtifacts)


class CompletedTask(BaseModel):
    id: str
    requirement: str
    score: float = 0.0
    verdict: str = ""
    iterations: int = 0
    elapsed_seconds: float = 0.0


class SessionStats(BaseModel):
    total_tasks: int = 0
    completed: int = 0
    blocked: int = 0
    total_iterations: int = 0
    avg_score: float = 0.0
    elapsed_seconds: float = 0.0


class StopContext(BaseModel):
    """Structured context captured when a task is stopped."""
    stop_kind: str = ""
    threshold_snapshot: dict[str, Any] = Field(default_factory=dict)
    stop_reason: str = ""
    reflection_signal: str | None = None
    stopped_at: str = ""


class SessionState(BaseModel):
    """Full session state, persisted to .harness-flow/state.json."""
    session_id: str = ""
    mode: str = "idle"
    current_task: TaskRecord | None = None
    completed: list[CompletedTask] = Field(default_factory=list)
    blocked: list[CompletedTask] = Field(default_factory=list)
    stats: SessionStats = Field(default_factory=SessionStats)
    stop_context: StopContext | None = None

    def save(self, agents_dir: Path) -> None:
        """Persist to .harness-flow/state.json."""
        agents_dir.mkdir(parents=True, exist_ok=True)
        state_file = agents_dir / "state.json"
        state_file.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, agents_dir: Path) -> SessionState:
        """Restore from .harness-flow/state.json.

        Never raises on corrupt or invalid data — returns a fresh default
        state and emits a visible warning so the user knows recovery occurred.
        """
        state_file = agents_dir / "state.json"
        if not state_file.exists():
            return cls()
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return cls.model_validate(data)
        except (json.JSONDecodeError, ValidationError, OSError) as exc:
            warnings.warn(
                f"Corrupt session state at {state_file} ({type(exc).__name__}: {exc}); "
                "using fresh default state",
                stacklevel=2,
            )
            return cls()

    @classmethod
    def detect_incomplete(cls, agents_dir: Path) -> SessionState | None:
        """Return state if a session is in progress (non-idle with a current task)."""
        state = cls.load(agents_dir)
        if state.mode != "idle" and state.current_task is not None:
            return state
        return None


