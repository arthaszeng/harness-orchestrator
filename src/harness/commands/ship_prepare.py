"""harness ship-prepare — combined pre-computation for ship phase.

Runs diff-stat + escalation-score + review metadata in one call,
designed to execute while CI runs in background.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harness.core.config import HarnessConfig
from harness.core.escalation import compute_ship_escalation


def run_ship_prepare(*, task: str | None = None, as_json: bool = True) -> None:
    """Pre-compute ship phase metadata (diff + escalation + review hints)."""
    from harness.commands.diff_stat import _classify_file
    from harness.core.workflow_state import resolve_task_dir
    from harness.integrations.git_ops import run_git

    cwd = Path.cwd()
    try:
        cfg = HarnessConfig.load(cwd)
    except Exception:
        cfg = HarnessConfig()

    trunk = cfg.workflow.trunk_branch
    diff_range = f"origin/{trunk}..HEAD"

    result = run_git(["diff", "--name-only", diff_range], cwd, timeout=10)
    if result.returncode != 0:
        err_msg = result.stderr.strip() or f"git diff failed (exit {result.returncode})"
        if as_json:
            typer.echo(json.dumps({"error": err_msg}))
        raise typer.Exit(1)

    files = [f for f in (result.stdout or "").strip().splitlines() if f]
    categories: dict[str, list[str]] = {"code": [], "test": [], "doc": [], "other": []}
    for f in files:
        categories[_classify_file(f)].append(f)

    stat_result = run_git(["diff", "--shortstat", diff_range], cwd, timeout=10)
    additions, deletions = 0, 0
    if stat_result.returncode == 0:
        stat_line = (stat_result.stdout or "").strip()
        import re
        add_m = re.search(r"(\d+)\s+insertion", stat_line)
        del_m = re.search(r"(\d+)\s+deletion", stat_line)
        if add_m:
            additions = int(add_m.group(1))
        if del_m:
            deletions = int(del_m.group(1))

    log_result = run_git(["rev-list", "--count", diff_range], cwd, timeout=10)
    commit_count = 1
    if log_result.returncode == 0:
        try:
            commit_count = int(log_result.stdout.strip())
        except ValueError:
            pass

    trust_adj = 0
    try:
        from harness.core.review_calibration import (
            collect_outcomes,
            generate_calibration_report,
        )
        from harness.core.trust_engine import TrustConfig, compute_trust_profile

        agents_dir = cwd / ".harness-flow"
        outcomes = collect_outcomes(agents_dir)
        if outcomes:
            report = generate_calibration_report(outcomes)
            profile = compute_trust_profile(report, outcomes, config=TrustConfig())
            trust_adj = profile.escalation_adjustment
    except Exception:
        pass

    escalation = compute_ship_escalation(
        changed_files=files,
        total_additions=additions,
        total_deletions=deletions,
        commit_count=commit_count,
        trust_adjustment=trust_adj,
        gate_full_review_min=cfg.native.gate_full_review_min,
        gate_summary_confirm_min=cfg.native.gate_summary_confirm_min,
    )

    agents_dir = cwd / ".harness-flow"
    task_dir = resolve_task_dir(agents_dir, explicit_task_id=task)

    output = {
        "diff_stat": {
            "total_files": len(files),
            "code_files": len(categories["code"]),
            "test_files": len(categories["test"]),
            "doc_files": len(categories["doc"]),
            "additions": additions,
            "deletions": deletions,
        },
        "escalation": escalation.to_dict(),
        "review_dispatch": {
            "level": escalation.level.value,
            "roles": _roles_for_level(escalation.level.value),
        },
        "task_dir": str(task_dir) if task_dir else None,
    }

    if as_json:
        typer.echo(json.dumps(output))
    else:
        typer.echo(f"Ship Prepare: {escalation.level.value} review ({len(files)} files, +{additions}/-{deletions})")


def _roles_for_level(level: str) -> list[str]:
    """Return role list based on escalation level."""
    if level == "FULL":
        return ["architect", "product_owner", "engineer", "qa", "project_manager"]
    if level == "LITE":
        return ["engineer", "qa"]
    return []
