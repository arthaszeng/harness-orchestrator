"""结构化事件日志 — 每个 agent 调用、CI 执行和状态转换写入 events.jsonl"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventEmitter:
    """Append-only JSONL event writer for a single session run."""

    def __init__(self, agents_dir: Path, session_id: str) -> None:
        self._run_dir = agents_dir / "runs" / session_id
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._run_dir / "events.jsonl"

    def _emit(self, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": event,
            **fields,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ── agent lifecycle ──────────────────────────────────────────

    def agent_start(
        self, *, role: str, driver: str, agent_name: str, iteration: int,
    ) -> float:
        """Record agent invocation start; returns a monotonic timestamp for elapsed calc."""
        self._emit(
            "agent_start",
            role=role, driver=driver, agent_name=agent_name, iteration=iteration,
        )
        return time.monotonic()

    def agent_end(
        self,
        *,
        role: str,
        driver: str,
        agent_name: str,
        iteration: int,
        exit_code: int,
        success: bool,
        output_len: int,
        elapsed_ms: int,
    ) -> None:
        self._emit(
            "agent_end",
            role=role, driver=driver, agent_name=agent_name, iteration=iteration,
            exit_code=exit_code, success=success, output_len=output_len,
            elapsed_ms=elapsed_ms,
        )

    # ── CI gate ──────────────────────────────────────────────────

    def ci_result(
        self, *, command: str, exit_code: int, verdict: str, elapsed_ms: int,
    ) -> None:
        self._emit(
            "ci_result",
            command=command, exit_code=exit_code, verdict=verdict,
            elapsed_ms=elapsed_ms,
        )

    # ── state transitions ────────────────────────────────────────

    def state_transition(
        self, *, from_state: str, to_state: str, task_id: str,
    ) -> None:
        self._emit(
            "state_transition",
            from_state=from_state, to_state=to_state, task_id=task_id,
        )

    # ── workflow-level events ────────────────────────────────────

    def task_start(self, *, task_id: str, requirement: str, branch: str) -> None:
        self._emit("task_start", task_id=task_id, requirement=requirement, branch=branch)

    def task_end(
        self, *, task_id: str, verdict: str, score: float, iterations: int,
    ) -> None:
        self._emit(
            "task_end",
            task_id=task_id, verdict=verdict, score=score, iterations=iterations,
        )


class NullEventEmitter(EventEmitter):
    """No-op emitter for when observability is disabled or session_id is unknown."""

    def __init__(self) -> None:
        pass  # skip directory creation

    def _emit(self, event: str, **fields: Any) -> None:
        pass
