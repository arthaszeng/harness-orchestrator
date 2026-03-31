"""State machine and checkpoint persistence."""

from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    CONTRACTED = "contracted"
    BUILDING = "building"
    EVALUATING = "evaluating"
    DONE = "done"
    BLOCKED = "blocked"


# Allowed state transitions
_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.IDLE: {TaskState.PLANNING},
    TaskState.PLANNING: {TaskState.CONTRACTED, TaskState.BLOCKED},
    TaskState.CONTRACTED: {TaskState.BUILDING},
    TaskState.BUILDING: {TaskState.EVALUATING, TaskState.BLOCKED},
    TaskState.EVALUATING: {TaskState.DONE, TaskState.PLANNING, TaskState.BLOCKED},
    TaskState.DONE: {TaskState.IDLE},
    TaskState.BLOCKED: {TaskState.IDLE},
}


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


class SessionState(BaseModel):
    """Full session state, persisted to .agents/state.json."""
    session_id: str = ""
    mode: str = "idle"  # idle / run / auto
    current_task: TaskRecord | None = None
    completed: list[CompletedTask] = Field(default_factory=list)
    blocked: list[CompletedTask] = Field(default_factory=list)
    stats: SessionStats = Field(default_factory=SessionStats)

    def save(self, agents_dir: Path) -> None:
        """Persist to .agents/state.json."""
        agents_dir.mkdir(parents=True, exist_ok=True)
        state_file = agents_dir / "state.json"
        state_file.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, agents_dir: Path) -> SessionState:
        """Restore from .agents/state.json."""
        state_file = agents_dir / "state.json"
        if not state_file.exists():
            return cls()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return cls.model_validate(data)

    @classmethod
    def detect_incomplete(cls, agents_dir: Path) -> SessionState | None:
        """Return state if a session is in progress (non-idle with a current task)."""
        state = cls.load(agents_dir)
        if state.mode != "idle" and state.current_task is not None:
            return state
        return None


class StateMachine:
    """Manages task state transitions and checkpoints."""

    def __init__(self, project_root: Path) -> None:
        self._agents_dir = project_root / ".agents"
        self._state = SessionState.load(self._agents_dir)
        self._session_start = datetime.now(timezone.utc)
        self._register_sigint()

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def agents_dir(self) -> Path:
        return self._agents_dir

    def start_session(self, mode: str) -> None:
        """Start a new session."""
        self._state.session_id = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._state.mode = mode
        self._session_start = datetime.now(timezone.utc)
        self._checkpoint()

    def start_task(self, task_id: str, requirement: str, branch: str) -> TaskRecord:
        """Start a new task."""
        task = TaskRecord(
            id=task_id,
            requirement=requirement,
            state=TaskState.IDLE,
            branch=branch,
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self._state.current_task = task
        self._state.stats.total_tasks += 1
        self._checkpoint()
        return task

    def transition(self, to: TaskState) -> None:
        """Apply a state transition; each transition checkpoints."""
        task = self._state.current_task
        if task is None:
            raise RuntimeError("No active task")

        allowed = _TRANSITIONS.get(task.state, set())
        if to not in allowed:
            raise ValueError(f"Illegal transition: {task.state.value} → {to.value}")

        task.state = to

        if to == TaskState.PLANNING:
            task.iteration += 1
            self._state.stats.total_iterations += 1

        self._checkpoint()

    def complete_task(self, score: float, verdict: str) -> None:
        """Mark the current task complete."""
        task = self._state.current_task
        if task is None:
            raise RuntimeError("No active task")

        task.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = CompletedTask(
            id=task.id,
            requirement=task.requirement,
            score=score,
            verdict=verdict,
            iterations=task.iteration,
            elapsed_seconds=_elapsed(task.started_at),
        )

        if verdict == "PASS":
            self._state.completed.append(record)
            self._state.stats.completed += 1
        else:
            self._state.blocked.append(record)
            self._state.stats.blocked += 1

        self._update_avg_score()
        self._state.current_task = None
        self._checkpoint()

    def end_session(self) -> None:
        """End the session."""
        elapsed = (datetime.now(timezone.utc) - self._session_start).total_seconds()
        self._state.stats.elapsed_seconds = elapsed
        self._state.mode = "idle"
        self._state.current_task = None
        self._checkpoint()

    def stop_requested(self) -> bool:
        """Return True if a stop signal file is present."""
        return (self._agents_dir / ".stop").exists()

    def clear_stop_signal(self) -> None:
        """Remove the stop signal file if it exists."""
        stop_file = self._agents_dir / ".stop"
        if stop_file.exists():
            stop_file.unlink()

    def _checkpoint(self) -> None:
        """Persist current state and refresh progress.md."""
        self._state.save(self._agents_dir)
        # Lazy import to avoid circular dependency (progress imports state)
        from harness.core.progress import update_progress

        update_progress(self._agents_dir, self._state)

    def _update_avg_score(self) -> None:
        scores = [t.score for t in self._state.completed if t.score > 0]
        self._state.stats.avg_score = sum(scores) / len(scores) if scores else 0.0

    def _register_sigint(self) -> None:
        """Register SIGINT handler to checkpoint before exit."""
        def _handler(sig: int, frame: Any) -> None:
            self._checkpoint()
            sys.exit(130)
        signal.signal(signal.SIGINT, _handler)


def _elapsed(started_at: str) -> float:
    """Seconds from started_at (ISO) to now."""
    if not started_at:
        return 0.0
    start = datetime.fromisoformat(started_at)
    now = datetime.now(timezone.utc)
    return (now - start).total_seconds()
