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
from typing import Any

_EVAL_ROUND_RE = re.compile(r"evaluation-r(\d+)\.md$")
_BUILD_ROUND_RE = re.compile(r"build-r(\d+)\.log$")


def _next_round(task_dir: Path, pattern: re.Pattern[str]) -> int:
    """Return the next available round number (1-based)."""
    max_round = 0
    try:
        for p in task_dir.iterdir():
            m = pattern.search(p.name)
            if m:
                max_round = max(max_round, int(m.group(1)))
    except OSError:
        pass
    return max_round + 1


def next_eval_round(task_dir: Path) -> int:
    """Return the next evaluation round number."""
    return _next_round(task_dir, _EVAL_ROUND_RE)


def next_build_round(task_dir: Path) -> int:
    """Return the next build log round number."""
    return _next_round(task_dir, _BUILD_ROUND_RE)


def save_evaluation(
    task_dir: Path,
    *,
    round_num: int | None = None,
    scores: dict[str, dict[str, Any]] | None = None,
    findings: list[str] | None = None,
    auto_fixed: list[str] | None = None,
    ask_items: list[str] | None = None,
    verdict: str = "PASS",
) -> Path:
    """Write an ``evaluation-rN.md`` file to *task_dir*.

    If *round_num* is ``None``, auto-increments from existing files.
    Returns the path of the written file.
    """
    if round_num is None:
        round_num = next_eval_round(task_dir)

    scores = scores or {}
    findings = findings or []
    auto_fixed = auto_fixed or []
    ask_items = ask_items or []

    lines: list[str] = [f"# Code Evaluation — Round {round_num}", ""]

    # Dimension scores table
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
        lines.append(f"| **Weighted Average** | | **{avg:.1f}/10** |")
    lines.append("")

    # Findings
    lines.append("## Findings")
    if findings:
        for f in findings:
            lines.append(f"- {f}")
    else:
        lines.append("None")
    lines.append("")

    # Auto-Fixed
    lines.append("## Auto-Fixed")
    if auto_fixed:
        for f in auto_fixed:
            lines.append(f"- {f}")
    else:
        lines.append("None")
    lines.append("")

    # ASK Items
    lines.append("## ASK Items")
    if ask_items:
        for a in ask_items:
            lines.append(f"- {a}")
    else:
        lines.append("None")
    lines.append("")

    # Verdict
    lines.append(f"## Verdict: {verdict.upper()}")
    lines.append("")

    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"evaluation-r{round_num}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def save_build_log(
    task_dir: Path,
    content: str,
    *,
    round_num: int | None = None,
) -> Path:
    """Write a ``build-rN.log`` file to *task_dir*.

    Returns the path of the written file.
    """
    if round_num is None:
        round_num = next_build_round(task_dir)

    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"build-r{round_num}.log"
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
        "models_used": [
            "architect", "product-owner", "engineer", "qa", "project-manager",
        ],
    }
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "ship-metrics.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
