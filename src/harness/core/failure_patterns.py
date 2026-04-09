"""Structured failure pattern library for cross-task failure tracking.

Each task records its own failure patterns in ``failure-patterns.jsonl``.
``search_failure_patterns`` aggregates across all task (and archive) directories
to surface recurring issues during build planning.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness.core.score_calibration import normalize_finding_signature

FAILURE_PATTERNS_FILENAME = "failure-patterns.jsonl"

VALID_CATEGORIES = frozenset({
    "ci-failure",
    "lint-error",
    "type-error",
    "test-failure",
    "build-error",
    "eval-iterate",
    "gate-blocked",
    "runtime-error",
    "other",
})
"""Known categories for documentation/validation. Free-text is accepted at save
time — this set is used for CLI help and downstream aggregation, not enforcement."""


class FailurePattern(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=120)
    task_id: str = Field(min_length=1, max_length=120)
    phase: str = Field(min_length=1, max_length=30)
    category: str = Field(min_length=1, max_length=60)
    signature: str = Field(default="", max_length=500)
    summary: str = Field(min_length=1, max_length=2000)
    error_output: str = Field(default="", max_length=5000)
    root_cause: str = Field(default="", max_length=2000)
    fix_applied: str = Field(default="", max_length=2000)
    recurrence_count: int = Field(default=1, ge=1)
    first_seen: str = Field(default="", max_length=64)
    last_seen: str = Field(default="", max_length=64)


class FailurePatternLoadResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str = ""
    items: list[FailurePattern] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append_line(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(payload + "\n")


def save_failure_pattern(
    task_dir: Path,
    *,
    task_id: str,
    phase: str,
    category: str,
    summary: str,
    error_output: str = "",
    root_cause: str = "",
    fix_applied: str = "",
    recurrence_count: int = 1,
) -> FailurePattern:
    """Append a single failure pattern to ``failure-patterns.jsonl``."""
    now = _utc_now()
    sig = normalize_finding_signature(summary)
    pattern = FailurePattern(
        id=f"fp-{uuid4().hex[:12]}",
        task_id=task_id,
        phase=phase,
        category=category,
        signature=sig,
        summary=summary,
        error_output=error_output,
        root_cause=root_cause,
        fix_applied=fix_applied,
        recurrence_count=recurrence_count,
        first_seen=now,
        last_seen=now,
    )
    _append_line(task_dir / FAILURE_PATTERNS_FILENAME, pattern.model_dump_json())

    from harness.core.workflow_state import WORKFLOW_STATE_FILENAME, sync_task_state, task_dir_number

    if task_dir_number(task_dir) is not None or (task_dir / WORKFLOW_STATE_FILENAME).exists():
        sync_task_state(task_dir, artifact_updates={"failure_patterns": FAILURE_PATTERNS_FILENAME})

    return pattern


def load_failure_patterns(task_dir: Path) -> FailurePatternLoadResult:
    """Load all failure patterns from a single task directory."""
    path = task_dir / FAILURE_PATTERNS_FILENAME
    if not path.exists():
        return FailurePatternLoadResult(path=str(path))

    items: list[FailurePattern] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return FailurePatternLoadResult(
            path=str(path),
            errors=[f"file: {type(exc).__name__}: {exc}"],
        )

    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            items.append(FailurePattern.model_validate(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"line {idx}: {type(exc).__name__}: {exc}")

    return FailurePatternLoadResult(path=str(path), items=items, errors=errors)


def search_failure_patterns(
    agents_dir: Path,
    *,
    query: str = "",
    category: str = "",
    limit: int = 20,
) -> list[FailurePattern]:
    """Search failure patterns across all task and archive directories.

    Matching rules:
    - ``query``: normalized substring containment against the pattern signature
    - ``category``: case-insensitive exact match
    - Empty query + empty category returns all patterns (up to *limit*)
    """
    if limit < 1:
        limit = 1
    from harness.core.workflow_state import iter_archive_dirs, iter_task_dirs

    normalized_query = normalize_finding_signature(query) if query else ""
    category_lower = category.lower().strip() if category else ""

    results: list[FailurePattern] = []
    for task_dir in iter_task_dirs(agents_dir) + iter_archive_dirs(agents_dir):
        result = load_failure_patterns(task_dir)
        for item in result.items:
            if normalized_query and normalized_query not in item.signature:
                continue
            if category_lower and item.category.lower().strip() != category_lower:
                continue
            results.append(item)
            if len(results) >= limit:
                return results

    return results
