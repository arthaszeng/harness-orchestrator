"""Core context-budget logic — pure functions for token estimation and budget checking.

Shared by both the ``harness context-budget`` CLI command and the
``harness preflight-bundle`` composite check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ARTIFACT_GLOBS: list[str] = [
    "plan.md",
    "handoff-*.json",
    "session-context.json",
    "build-r*.md",
    "code-eval-r*.md",
    "plan-eval-r*.md",
    "workflow-state.json",
    "ship-metrics.json",
    "feedback-ledger.jsonl",
    "failure-patterns.jsonl",
    "build-notes.md",
]

CHARS_PER_TOKEN = 4


@dataclass
class FileTokenInfo:
    """Token estimation for a single artifact file."""

    name: str
    chars: int
    tokens: int


@dataclass
class BudgetResult:
    """Aggregated budget check result."""

    files: list[FileTokenInfo] = field(default_factory=list)
    total_chars: int = 0
    total_tokens: int = 0
    budget: int = 0
    over_budget: bool = False


def scan_artifacts(task_dir: Path, globs: list[str] | None = None) -> list[FileTokenInfo]:
    """Scan *task_dir* for artifact files matching *globs* and estimate tokens.

    Returns one :class:`FileTokenInfo` per matched file.  Files that cannot
    be read (permission / encoding errors) are silently skipped.
    """
    patterns = globs if globs is not None else ARTIFACT_GLOBS
    results: list[FileTokenInfo] = []
    for pattern in patterns:
        for path in sorted(task_dir.glob(pattern)):
            if not path.is_file():
                continue
            try:
                chars = len(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            results.append(FileTokenInfo(name=path.name, chars=chars, tokens=chars // CHARS_PER_TOKEN))
    return results


def estimate_task_tokens(task_dir: Path, globs: list[str] | None = None) -> BudgetResult:
    """Scan artifacts and return total token estimation (no budget comparison)."""
    files = scan_artifacts(task_dir, globs)
    total_chars = sum(f.chars for f in files)
    total_tokens = total_chars // CHARS_PER_TOKEN
    return BudgetResult(files=files, total_chars=total_chars, total_tokens=total_tokens)


def check_budget(task_dir: Path, budget: int, globs: list[str] | None = None) -> BudgetResult:
    """Estimate tokens and compare against *budget*.

    Sets :attr:`BudgetResult.over_budget` to ``True`` when the estimated
    token count exceeds *budget*.
    """
    result = estimate_task_tokens(task_dir, globs)
    result.budget = budget
    result.over_budget = result.total_tokens > budget
    return result
