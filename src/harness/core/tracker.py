"""RunTracker — context manager that dual-writes to Registry + EventEmitter.

Provides a single ``with tracker.track(...):`` block for any agent invocation.
Both the SQLite registry and the append-only JSONL log are written on every
call, keeping the two systems in sync.

In cursor-native mode the driver is always "cursor".
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generator

from harness.core.roles import DEFAULT_DRIVER

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
        driver_name: str = DEFAULT_DRIVER,
        agent_name: str = "unknown",
        iteration: int | None = None,
        *,
        readonly: bool = False,
        cwd: str | None = None,
        branch: str | None = None,
        prompt: str = "",
    ) -> Generator[RunInfo, None, None]:
        """Context manager that brackets a single agent invocation.

        Usage::

            with tracker.track("architect", agent_name="harness-architect", iteration=1, readonly=True, prompt=p) as run:
                run.exit_code = 0
                run.output_len = 42
                run.success = True
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
