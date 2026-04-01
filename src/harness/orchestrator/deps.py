"""Workflow dependency injection — seam for testing.

Inspired by Claude Code's QueryDeps pattern: expose a narrow Protocol
with replaceable functions so tests can swap out real drivers, git, and CI
without monkeypatching.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

from harness.drivers.base import AgentResult

if TYPE_CHECKING:
    from harness.drivers.resolver import DriverResolver


@dataclass
class CIResult:
    """Minimal CI check outcome."""

    verdict: str  # PASS / CI_FAIL
    feedback: str
    exit_code: int = 0


@runtime_checkable
class WorkflowDeps(Protocol):
    """Replaceable seam for the workflow loop's external dependencies."""

    def invoke_agent(
        self,
        role: str,
        agent_name: str,
        prompt: str,
        cwd: Path,
        *,
        readonly: bool = False,
        on_output: Callable[[str], None] | None = None,
        model: str = "",
    ) -> AgentResult: ...

    def run_ci(
        self, command: str, cwd: Path, *, on_output: Callable[[str], None] | None = None
    ) -> CIResult: ...

    def ensure_clean(self, cwd: Path) -> None: ...

    def create_branch(self, name: str, cwd: Path) -> None: ...

    def has_changes(self, cwd: Path, trunk: str) -> bool: ...

    def rebase_and_merge(self, branch: str, trunk: str, cwd: Path) -> bool: ...

    def head_commit(self, cwd: Path) -> str: ...

    def uuid(self) -> str: ...


class ProductionDeps:
    """Default implementation that delegates to real drivers and git_ops."""

    def __init__(self, resolver: "DriverResolver") -> None:
        self._resolver = resolver

    def invoke_agent(
        self,
        role: str,
        agent_name: str,
        prompt: str,
        cwd: Path,
        *,
        readonly: bool = False,
        on_output: Callable[[str], None] | None = None,
        model: str = "",
    ) -> AgentResult:
        driver = self._resolver.resolve(role)
        return driver.invoke(
            agent_name, prompt, cwd, readonly=readonly, on_output=on_output, model=model
        )

    def run_ci(
        self, command: str, cwd: Path, *, on_output: Callable[[str], None] | None = None
    ) -> CIResult:
        from harness.methodology.evaluation import run_ci_check

        result = run_ci_check(command, cwd, on_output=on_output)
        return CIResult(verdict=result.verdict, feedback=result.feedback)

    def ensure_clean(self, cwd: Path) -> None:
        from harness.integrations.git_ops import ensure_clean

        ensure_clean(cwd)

    def create_branch(self, name: str, cwd: Path) -> None:
        from harness.integrations.git_ops import create_branch

        create_branch(name, cwd)

    def has_changes(self, cwd: Path, trunk: str) -> bool:
        from harness.orchestrator.workflow import _has_build_changes

        return _has_build_changes(cwd, trunk)

    def rebase_and_merge(self, branch: str, trunk: str, cwd: Path) -> bool:
        from harness.integrations.git_ops import rebase_and_merge

        return rebase_and_merge(branch, trunk, cwd)

    def head_commit(self, cwd: Path) -> str:
        from harness.orchestrator.workflow import _git_head_commit

        return _git_head_commit(cwd)

    def uuid(self) -> str:
        return _uuid.uuid4().hex[:8]
