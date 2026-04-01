"""Structured task execution context.

Inspired by Claude Code's queryTracking + createSubagentContext: every agent
invocation carries a trace_id (pipeline-level) and span_id (invocation-level)
for structured observability. The depth field tracks nesting level.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class TaskContext:
    """Immutable context passed through the workflow pipeline.

    trace_id: identifies the entire task pipeline (plan → build → eval)
    span_id:  identifies a single agent invocation within the pipeline
    depth:    nesting level (0 = top-level, 1 = sub-eval, etc.)
    """
    task_id: str
    trace_id: str = field(default_factory=_new_id)
    span_id: str = field(default_factory=_new_id)
    iteration: int = 1
    depth: int = 0
    readonly: bool = False
    working_dir: Path = field(default_factory=Path.cwd)

    def child_span(self, *, readonly: bool | None = None) -> TaskContext:
        """Create a child context with a new span_id and incremented depth."""
        return TaskContext(
            task_id=self.task_id,
            trace_id=self.trace_id,
            span_id=_new_id(),
            iteration=self.iteration,
            depth=self.depth + 1,
            readonly=readonly if readonly is not None else self.readonly,
            working_dir=self.working_dir,
        )

    def next_iteration(self) -> TaskContext:
        """Create context for the next iteration with a new span_id."""
        return TaskContext(
            task_id=self.task_id,
            trace_id=self.trace_id,
            span_id=_new_id(),
            iteration=self.iteration + 1,
            depth=self.depth,
            readonly=self.readonly,
            working_dir=self.working_dir,
        )
