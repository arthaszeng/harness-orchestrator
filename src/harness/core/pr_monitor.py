"""PR CI monitoring and failure diagnosis for the ship landing phase.

Composes :mod:`~harness.integrations.gh_ops` helpers to provide a
higher-level API that the ``/harness-ship`` Step 9 template can drive
through the ``harness pr-status`` and ``harness ci-logs`` CLI commands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from harness.integrations.gh_ops import (
    FailedJobLog,
    PrStatusSummary,
    gh_ci_logs,
    gh_pr_status,
)
from harness.integrations.git_ops import GitOperationResult

log = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """Diagnosis category for a CI failure."""

    AUTO_FIXABLE = "auto-fixable"
    NEEDS_HUMAN = "needs-human"
    INFRA_ISSUE = "infra-issue"


@dataclass(frozen=True)
class CiDiagnosis:
    """Structured diagnosis for a single failed job."""

    job_name: str
    category: FailureCategory
    summary: str
    log_excerpt: str = ""


@dataclass
class PrMonitor:
    """Monitors a PR's CI status and provides failure diagnosis."""

    project_root: Path

    @classmethod
    def create(cls, project_root: Path | None = None) -> "PrMonitor":
        return cls(project_root=(project_root or Path.cwd()).resolve())

    def check_status(
        self,
        *,
        pr_number: int | None = None,
        branch: str | None = None,
    ) -> tuple[GitOperationResult, PrStatusSummary | None]:
        """Query the current CI and merge status of a PR."""
        return gh_pr_status(
            self.project_root,
            pr_number=pr_number,
            branch=branch,
        )

    def get_failure_logs(
        self,
        *,
        pr_number: int | None = None,
        branch: str | None = None,
        max_lines: int = 200,
    ) -> tuple[GitOperationResult, list[FailedJobLog]]:
        """Retrieve log excerpts from failed CI jobs."""
        return gh_ci_logs(
            self.project_root,
            pr_number=pr_number,
            branch=branch,
            max_lines=max_lines,
        )

    def diagnose_failures(
        self,
        failed_jobs: list[FailedJobLog],
    ) -> list[CiDiagnosis]:
        """Classify each failed job into an actionable category.

        Heuristic keyword matching — intentionally simple; the agent
        template can refine the diagnosis using full log context.
        """
        diagnoses: list[CiDiagnosis] = []
        for job in failed_jobs:
            category, summary = _classify_failure(job.log_tail)
            diagnoses.append(CiDiagnosis(
                job_name=job.name,
                category=category,
                summary=summary,
                log_excerpt=job.log_tail[-500:] if job.log_tail else "",
            ))
        return diagnoses


_INFRA_KEYWORDS = frozenset({
    "rate limit",
    "rate_limit",
    "quota exceeded",
    "internal server error",
    "503 service unavailable",
    "runner error",
    "out of disk",
    "no space left",
    "network unreachable",
    "connection timed out",
    "could not resolve host",
})

def _classify_failure(log_text: str) -> tuple[FailureCategory, str]:
    """Classify a failure log into a category with a one-line summary."""
    lower = log_text.lower()

    for kw in _INFRA_KEYWORDS:
        if kw in lower:
            return FailureCategory.INFRA_ISSUE, f"Infrastructure issue detected: '{kw}'"

    for kw in ("syntaxerror", "indentationerror", "ruff", "lint", "formatting",
                "black", "isort", "mypy", "type error", "missing import",
                "undefined name", "unused import"):
        if kw in lower:
            return FailureCategory.AUTO_FIXABLE, f"Likely auto-fixable: '{kw}' detected"

    if "importerror" in lower or "modulenotfounderror" in lower:
        return FailureCategory.AUTO_FIXABLE, "Missing import or dependency"

    if "assert" in lower or "failed" in lower or "error" in lower:
        return FailureCategory.AUTO_FIXABLE, "Test failure — agent can attempt fix"

    return FailureCategory.NEEDS_HUMAN, "Unrecognized failure pattern — manual review needed"
