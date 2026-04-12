"""Structured failure pattern library for cross-task failure tracking.

Each task records its own failure patterns in ``failure-patterns.jsonl``.
``search_failure_patterns`` aggregates across all task (and archive) directories
to surface recurring issues during build planning.

When Memverse integration is enabled, ``save_failure_pattern`` attaches a
``memverse_sync`` payload to the returned ``FailurePattern``.  The Cursor
agent (which has an authenticated MCP session) executes the actual
``upsert_memory`` call — Python never touches the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
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

    memverse_sync: dict | None = Field(default=None, exclude=True)
    """When set, contains MCP ``upsert_memory`` arguments for the Cursor agent."""


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


def _is_memverse_enabled(task_dir: Path) -> bool:
    """Check config to see if Memverse integration is on.

    Delegates to a cached helper keyed on the resolved project root so
    repeated calls within the same CLI invocation skip file I/O.
    """
    project_root = _find_project_root(task_dir)
    if project_root is None:
        return False
    return _memverse_enabled_cached(str(project_root))


def _memverse_domain(task_dir: Path) -> str:
    """Return the configured Memverse domain for failure patterns."""
    project_root = _find_project_root(task_dir)
    if project_root is None:
        return "harness-flow"
    return _memverse_domain_cached(str(project_root))


def _find_project_root(start: Path) -> Path | None:
    cur = start
    for _ in range(6):
        if (cur / ".harness-flow" / "config.toml").exists():
            return cur
        parent = cur.parent
        if parent == cur:
            return None
        cur = parent
    return None


@lru_cache(maxsize=4)
def _memverse_enabled_cached(project_root_str: str) -> bool:
    try:
        from harness.core.config import HarnessConfig

        cfg = HarnessConfig.load(Path(project_root_str))
        return cfg.integrations.memverse.enabled
    except Exception:
        import logging

        logging.getLogger(__name__).debug("Failed to load memverse config", exc_info=True)
        return False


@lru_cache(maxsize=4)
def _memverse_domain_cached(project_root_str: str) -> str:
    try:
        from harness.core.config import HarnessConfig

        cfg = HarnessConfig.load(Path(project_root_str))
        return (
            cfg.integrations.memverse.domain_prefix.strip()
            or cfg.project.name
            or "harness-flow"
        )
    except Exception:
        import logging

        logging.getLogger(__name__).debug("Failed to load memverse domain config", exc_info=True)
        return "harness-flow"


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
    memverse_enabled: bool | None = None,
) -> FailurePattern:
    """Append a single failure pattern to ``failure-patterns.jsonl``.

    When *memverse_enabled* is ``True`` (or auto-detected from config),
    ``pattern.memverse_sync`` is populated with MCP ``upsert_memory``
    arguments.  The caller (Cursor agent) is responsible for executing
    the MCP call within its authenticated session.
    """
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

    if memverse_enabled is None:
        memverse_enabled = _is_memverse_enabled(task_dir)

    if memverse_enabled:
        from harness.integrations.memverse import build_upsert_payload

        domain = _memverse_domain(task_dir)
        sync = build_upsert_payload(
            summary=summary,
            category=category,
            phase=phase,
            task_id=task_id,
            fp_id=pattern.id,
            signature=sig,
            first_seen=now,
            error_output=error_output,
            root_cause=root_cause,
            fix_applied=fix_applied,
            domain=domain,
        )
        pattern.memverse_sync = sync.payload.as_dict()

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


def _build_search_text(pattern: FailurePattern) -> str:
    """Build a normalized search text from all relevant fields of *pattern*.

    Used by both :func:`search_failure_patterns` and
    :func:`aggregate_failure_patterns` to match queries against the full
    content of a failure pattern (not just the signature).
    """
    parts = [
        pattern.summary,
        pattern.root_cause,
        pattern.fix_applied,
        pattern.error_output,
    ]
    return normalize_finding_signature(" ".join(parts))


def search_failure_patterns(
    agents_dir: Path,
    *,
    query: str = "",
    category: str = "",
    phase: str = "",
    limit: int = 20,
) -> list[FailurePattern]:
    """Search failure patterns across project-level, task, and archive directories.

    Collects **all** matching patterns, sorts by ``recurrence_count`` (desc)
    then ``last_seen`` (desc), and truncates to *limit*.

    Matching rules:
    - ``query``: normalized substring against full search text
      (summary + root_cause + fix_applied + error_output)
    - ``category``: case-insensitive exact match
    - ``phase``: case-insensitive exact match
    - Empty filters return all patterns
    """
    if limit < 1:
        limit = 1
    from harness.core.workflow_state import iter_archive_dirs, iter_task_dirs

    normalized_query = normalize_finding_signature(query) if query else ""
    category_lower = category.lower().strip() if category else ""
    phase_lower = phase.lower().strip() if phase else ""

    candidates: list[FailurePattern] = []

    def _collect(source_dir: Path) -> None:
        result = load_failure_patterns(source_dir)
        for item in result.items:
            if normalized_query and normalized_query not in _build_search_text(item):
                continue
            if category_lower and item.category.lower().strip() != category_lower:
                continue
            if phase_lower and item.phase.lower().strip() != phase_lower:
                continue
            candidates.append(item)

    _collect(agents_dir)
    for task_dir in iter_task_dirs(agents_dir) + iter_archive_dirs(agents_dir):
        _collect(task_dir)

    candidates.sort(key=lambda p: (p.recurrence_count, p.last_seen), reverse=True)
    return candidates[:limit]


@dataclass
class AggregatedPattern:
    """A failure pattern aggregated by signature across tasks."""

    signature: str
    total_recurrence: int
    categories: list[str]
    tasks: list[str]
    latest_summary: str
    latest_fix: str


def aggregate_failure_patterns(
    patterns: list[FailurePattern],
) -> list[AggregatedPattern]:
    """Aggregate failure patterns by signature, summing recurrence counts.

    Returns results sorted by ``total_recurrence`` descending.
    """
    groups: dict[str, AggregatedPattern] = {}
    for p in patterns:
        key = p.signature
        if key not in groups:
            groups[key] = AggregatedPattern(
                signature=key,
                total_recurrence=0,
                categories=[],
                tasks=[],
                latest_summary=p.summary,
                latest_fix=p.fix_applied,
            )
        agg = groups[key]
        agg.total_recurrence += p.recurrence_count
        if p.category not in agg.categories:
            agg.categories.append(p.category)
        if p.task_id not in agg.tasks:
            agg.tasks.append(p.task_id)
        agg.latest_summary = p.summary
        agg.latest_fix = p.fix_applied

    result = sorted(groups.values(), key=lambda a: a.total_recurrence, reverse=True)
    return result
