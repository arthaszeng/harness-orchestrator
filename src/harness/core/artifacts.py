"""Programmatic artifact writers for task directories.

Every artifact that ``gates.py`` checks for existence should have a
corresponding writer here — this ensures artifacts are created by
deterministic code, not by hoping an AI agent follows a prompt.

Parallels:
- ``handoff.py`` → ``save_handoff()``
- ``gates.py`` → ``write_gate_snapshot()``
- **This module** → ``save_evaluation()``, ``save_build_log()``, ``save_ship_metrics()``
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

_PLAN_EVAL_ROUND_RE = re.compile(r"plan-eval-r(\d+)\.md$")
_CODE_EVAL_ROUND_RE = re.compile(r"code-eval-r(\d+)\.md$")
_LEGACY_EVAL_ROUND_RE = re.compile(r"evaluation-r(\d+)\.md$")
_BUILD_ROUND_RE = re.compile(r"build-r(\d+)\.md$")
_LEGACY_BUILD_ROUND_RE = re.compile(r"build-r(\d+)\.log$")


def _next_round(task_dir: Path, patterns: tuple[re.Pattern[str], ...]) -> int:
    """Return the next available round number (1-based)."""
    max_round = 0
    try:
        for p in task_dir.iterdir():
            for pattern in patterns:
                m = pattern.search(p.name)
                if m:
                    max_round = max(max_round, int(m.group(1)))
                    break
    except FileNotFoundError:
        pass
    return max_round + 1


def next_eval_round(task_dir: Path) -> int:
    """Return the next global eval round across plan/code eval files."""
    return _next_round(
        task_dir,
        (_PLAN_EVAL_ROUND_RE, _CODE_EVAL_ROUND_RE, _LEGACY_EVAL_ROUND_RE),
    )


def next_build_round(task_dir: Path) -> int:
    """Return the next build log round number."""
    return _next_round(task_dir, (_BUILD_ROUND_RE, _LEGACY_BUILD_ROUND_RE))


def save_evaluation(
    task_dir: Path,
    *,
    kind: Literal["plan", "code"] = "code",
    round_num: int | None = None,
    scores: dict[str, dict[str, Any]] | None = None,
    findings: list[str] | None = None,
    auto_fixed: list[str] | None = None,
    ask_items: list[str] | None = None,
    verdict: str = "PASS",
    raw_body: str | None = None,
) -> Path:
    """Write a ``{kind}-eval-rN.md`` file to *task_dir*.

    If *raw_body* is provided, it is written verbatim (for pre-formatted content
    from the review synthesis step).  Otherwise a structured template is
    generated from *scores*, *findings*, etc.

    If *round_num* is ``None``, auto-increments from existing files.
    Returns the path of the written file.
    """
    if round_num is None:
        round_num = next_eval_round(task_dir)

    if raw_body is not None:
        content = raw_body
    else:
        scores = scores or {}
        findings = findings or []
        auto_fixed = auto_fixed or []
        ask_items = ask_items or []

        title = "Plan Evaluation" if kind == "plan" else "Code Evaluation"
        lines: list[str] = [f"# {title} — Round {round_num}", ""]

        lines.append("## Dimension Scores")
        lines.append("| Dimension | Role | Score |")
        lines.append("|-----------|------|-------|")
        total = 0.0
        count = 0
        for dimension, info in scores.items():
            role = info.get("role", dimension)
            score = info.get("score", 0)
            lines.append(f"| {dimension} | {role} | {score}/10 |")
            total += float(score)
            count += 1
        if count > 0:
            avg = total / count
            lines.append(f"| **Average** | | **{avg:.1f}/10** |")
        lines.append("")

        lines.append("## Findings")
        if findings:
            for f in findings:
                lines.append(f"- {f}")
        else:
            lines.append("None")
        lines.append("")

        lines.append("## Auto-Fixed")
        if auto_fixed:
            for f in auto_fixed:
                lines.append(f"- {f}")
        else:
            lines.append("None")
        lines.append("")

        lines.append("## ASK Items")
        if ask_items:
            for a in ask_items:
                lines.append(f"- {a}")
        else:
            lines.append("None")
        lines.append("")

        lines.append(f"## Verdict: {verdict.upper()}")
        lines.append("")
        content = "\n".join(lines)

    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"{kind}-eval-r{round_num}.md"
    path.write_text(content, encoding="utf-8")

    if kind == "code":
        _snapshot_prediction_sidecar(
            task_dir, content=content, scores=scores, verdict=verdict,
            findings=findings,
        )

    return path


def _snapshot_prediction_sidecar(
    task_dir: Path,
    *,
    content: str,
    scores: dict[str, dict[str, Any]] | None,
    verdict: str,
    findings: list[str] | None,
) -> None:
    """Best-effort write of prediction snapshot to review-outcome.json.

    Called internally by ``save_evaluation`` for code evals only.
    Failures are logged but never propagate.
    """
    import logging as _log

    try:
        from harness.core.gates import parse_eval_aggregate_score
        from harness.core.review_calibration import (
            ReviewOutcome,
            ReviewPrediction,
            load_review_outcome,
            save_review_outcome,
        )

        if scores is not None:
            dim_scores = {
                dim: float(info.get("score", 0)) for dim, info in scores.items()
            }
            total = sum(dim_scores.values())
            count = len(dim_scores)
            aggregate = total / count if count > 0 else None
        else:
            aggregate = parse_eval_aggregate_score(content)
            if aggregate is None:
                aggregate = _parse_aggregate_from_table(content)
            dim_scores = _parse_dimension_scores(content)

        if scores is not None:
            parsed_verdict = verdict
        else:
            parsed_verdict = ""
            import re as _re
            m = _re.search(r"^##\s+Verdict:\s+(\S+)", content, _re.MULTILINE | _re.IGNORECASE)
            if m:
                parsed_verdict = m.group(1).upper()

        finding_count = len(findings) if findings else _count_findings_from_content(content)

        prediction = ReviewPrediction(
            eval_aggregate=aggregate,
            dimension_scores=dim_scores,
            verdict=parsed_verdict.upper() if parsed_verdict else "",
            finding_count=finding_count,
        )

        existing = load_review_outcome(task_dir)
        if existing is not None:
            existing.prediction = prediction
            save_review_outcome(task_dir, existing)
        else:
            outcome = ReviewOutcome(
                task_id=task_dir.name,
                prediction=prediction,
            )
            save_review_outcome(task_dir, outcome)
    except Exception:
        _log.getLogger(__name__).debug(
            "Failed to snapshot prediction sidecar", exc_info=True,
        )


_TABLE_AGGREGATE_RE = re.compile(
    r"\*\*Average\*\*.*?(\d+(?:\.\d+)?)\s*/\s*10",
    re.IGNORECASE,
)


def _parse_aggregate_from_table(content: str) -> float | None:
    """Fallback parser for aggregate score in table format with empty cells."""
    import math as _math

    m = _TABLE_AGGREGATE_RE.search(content)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except (ValueError, TypeError):
        return None
    if not _math.isfinite(val):
        return None
    return val


_DIM_SCORE_COL2_RE = re.compile(
    r"^\|\s*([^|*]+?)\s*\|\s*(\d+(?:\.\d+)?)\s*/\s*10\s*\|",
    re.MULTILINE,
)
_DIM_SCORE_COL3_RE = re.compile(
    r"^\|\s*([^|*]+?)\s*\|\s*[^|]*\|\s*(\d+(?:\.\d+)?)\s*/\s*10\s*\|",
    re.MULTILINE,
)

_DIM_SKIP_LABELS = frozenset({
    "average", "**average**", "weighted avg", "weighted average",
    "role", "dimension", "category",
})


def _parse_dimension_scores(content: str) -> dict[str, float]:
    """Extract per-dimension scores from markdown table.

    Handles both ``| Dim | X/10 | Verdict |`` (score in column 2) and
    ``| Dim | PASS | X/10 |`` (score in column 3) layouts.
    """
    results: dict[str, float] = {}
    for pat in (_DIM_SCORE_COL2_RE, _DIM_SCORE_COL3_RE):
        for m in pat.finditer(content):
            dim = m.group(1).strip()
            if dim.lower() in _DIM_SKIP_LABELS or "---" in dim:
                continue
            try:
                results.setdefault(dim, float(m.group(2)))
            except ValueError:
                continue
    return results


def _count_findings_from_content(content: str) -> int:
    """Count finding bullet points from markdown content (heuristic)."""
    in_findings = False
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Findings"):
            in_findings = True
            continue
        if in_findings:
            if stripped.startswith("##"):
                break
            if stripped.startswith("- ") and stripped != "- None":
                count += 1
    return count


def save_build_log(
    task_dir: Path,
    content: str,
    *,
    round_num: int | None = None,
) -> Path:
    """Write a ``build-rN.md`` file to *task_dir*.

    Returns the path of the written file.
    """
    if round_num is None:
        round_num = next_build_round(task_dir)

    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"build-r{round_num}.md"
    path.write_text(content, encoding="utf-8")
    return path


def save_ship_metrics(
    task_dir: Path,
    *,
    branch: str = "",
    pr_quality_score: float = 0.0,
    test_count: int = 0,
    eval_rounds: int = 1,
    findings_critical: int = 0,
    findings_informational: int = 0,
    auto_fixed: int = 0,
    plan_total: int = 0,
    plan_done: int = 0,
    coverage_pct: int = 0,
    e2e_total_time_sec: float = 0.0,
    manual_interventions_per_task: float = 0.0,
    first_pass_rate: float = 0.0,
) -> Path:
    """Write ``ship-metrics.json`` to *task_dir*.

    Returns the path of the written file.
    """
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": branch,
        "coverage_pct": coverage_pct,
        "plan_total": plan_total,
        "plan_done": plan_done,
        "pr_quality_score": pr_quality_score,
        "findings_critical": findings_critical,
        "findings_informational": findings_informational,
        "auto_fixed": auto_fixed,
        "test_count": test_count,
        "eval_rounds": eval_rounds,
        "efficiency_baseline": {
            "e2e_total_time_sec": round(float(e2e_total_time_sec), 2),
            "manual_interventions_per_task": round(float(manual_interventions_per_task), 2),
            "first_pass_rate": round(float(first_pass_rate), 4),
        },
        "models_used": [
            "architect", "product-owner", "engineer", "qa", "project-manager",
        ],
    }
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "ship-metrics.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    from harness.core.workflow_state import WORKFLOW_STATE_FILENAME, sync_task_state, task_dir_number

    # Keep generic helper usage (tmp dirs, ad-hoc scripts) backward-compatible.
    if task_dir_number(task_dir) is not None or (task_dir / WORKFLOW_STATE_FILENAME).exists():
        sync_task_state(task_dir, artifact_updates={"ship_metrics": path.name})
    return path
