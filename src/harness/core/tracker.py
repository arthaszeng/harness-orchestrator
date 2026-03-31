"""RunTracker — context manager that dual-writes to Registry + EventEmitter.

Replaces manual ev.agent_start() / ev.agent_end() pairs scattered across
workflow.py and autonomous.py with a single ``with tracker.track(...):`` block.
Both the SQLite registry and the append-only JSONL log are written on every
agent invocation, keeping the two systems in sync.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from harness.core.events import EventEmitter, NullEventEmitter
    from harness.core.registry import Registry


@dataclass
class RunInfo:
    """Mutable bag yielded by ``tracker.track()`` — caller sets fields inside the block."""
    run_id: int
    exit_code: int = -1
    output_len: int = 0
    success: bool = False
    log_path: str | None = None
    error: str | None = None


@dataclass
class RunTracker:
    """Wraps an agent invocation with registry + events dual-write."""

    registry: Registry
    events: EventEmitter | NullEventEmitter
    task_id: str | None = None
    parent_run_id: int | None = None

    @contextmanager
    def track(
        self,
        role: str,
        driver_name: str,
        agent_name: str,
        iteration: int | None = None,
        *,
        readonly: bool = False,
        cwd: str | None = None,
        branch: str | None = None,
        prompt: str = "",
    ) -> Generator[RunInfo, None, None]:
        """Context manager that brackets a single agent invocation.

        Usage::

            with tracker.track("planner", "cursor", "harness-planner", 1, readonly=True, prompt=p) as run:
                result = driver.invoke(...)
                run.exit_code = result.exit_code
                run.output_len = len(result.output)
                run.success = result.success
        """
        run_id = self.registry.register(
            role=role,
            driver=driver_name,
            agent_name=agent_name,
            task_id=self.task_id,
            parent_run_id=self.parent_run_id,
            iteration=iteration,
            readonly=readonly,
            cwd=cwd,
            branch=branch,
            prompt=prompt,
        )

        self.events.agent_start(
            role=role, driver=driver_name,
            agent_name=agent_name, iteration=iteration or 0,
        )

        t0 = time.monotonic()
        info = RunInfo(run_id=run_id)
        try:
            yield info
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            self.registry.fail(
                run_id,
                error=str(exc),
                exit_code=info.exit_code,
                output_len=info.output_len,
                elapsed_ms=elapsed_ms,
                log_path=info.log_path,
            )
            self.events.agent_end(
                role=role, driver=driver_name,
                agent_name=agent_name, iteration=iteration or 0,
                exit_code=info.exit_code, success=False,
                output_len=info.output_len, elapsed_ms=elapsed_ms,
            )
            raise
        else:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if info.success:
                self.registry.complete(
                    run_id,
                    exit_code=info.exit_code,
                    output_len=info.output_len,
                    elapsed_ms=elapsed_ms,
                    log_path=info.log_path,
                )
            else:
                self.registry.fail(
                    run_id,
                    error=info.error or "",
                    exit_code=info.exit_code,
                    output_len=info.output_len,
                    elapsed_ms=elapsed_ms,
                    log_path=info.log_path,
                )
            self.events.agent_end(
                role=role, driver=driver_name,
                agent_name=agent_name, iteration=iteration or 0,
                exit_code=info.exit_code, success=info.success,
                output_len=info.output_len, elapsed_ms=elapsed_ms,
            )
