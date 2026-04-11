"""harness escalation-score — deterministic escalation score computation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from harness.core.config import HarnessConfig
from harness.core.escalation import (
    compute_plan_escalation,
    compute_ship_escalation,
)

app = typer.Typer(help="Escalation score computation")


def _get_trust_adjustment() -> int:
    """Best-effort trust adjustment from calibration data."""
    try:
        from harness.core.review_calibration import (
            collect_outcomes,
            generate_calibration_report,
        )
        from harness.core.trust_engine import TrustConfig, compute_trust_profile

        agents_dir = Path.cwd() / ".harness-flow"
        outcomes = collect_outcomes(agents_dir)
        if not outcomes:
            return 0
        report = generate_calibration_report(outcomes)
        profile = compute_trust_profile(report, outcomes, config=TrustConfig())
        return profile.escalation_adjustment
    except Exception:
        return 0


def _get_ship_diff_data() -> dict:
    """Collect diff data for ship escalation."""
    from harness.integrations.git_ops import run_git

    cwd = Path.cwd()
    try:
        cfg = HarnessConfig.load(cwd)
    except Exception:
        cfg = HarnessConfig()
    trunk = cfg.workflow.trunk_branch
    diff_range = f"origin/{trunk}..HEAD"

    result = run_git(["diff", "--name-only", diff_range], cwd, timeout=10)
    files = [f for f in (result.stdout or "").strip().splitlines() if f] if result.returncode == 0 else []

    stat_result = run_git(["diff", "--stat", diff_range], cwd, timeout=10)
    additions, deletions = 0, 0
    if stat_result.returncode == 0:
        for line in (stat_result.stdout or "").strip().splitlines():
            if "insertion" in line or "deletion" in line:
                parts = line.split(",")
                for part in parts:
                    part = part.strip()
                    if "insertion" in part:
                        try:
                            additions = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "deletion" in part:
                        try:
                            deletions = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass

    log_result = run_git(["rev-list", "--count", diff_range], cwd, timeout=10)
    commit_count = 1
    if log_result.returncode == 0:
        try:
            commit_count = int(log_result.stdout.strip())
        except ValueError:
            pass

    return {
        "files": files,
        "additions": additions,
        "deletions": deletions,
        "commit_count": commit_count,
    }


@app.command("compute")
def compute_cmd(
    phase: str = typer.Option(
        ..., "--phase", "-p", help="Phase: plan or ship",
    ),
    as_json: bool = typer.Option(True, "--json/--no-json", help="JSON output"),
    deliverables: int = typer.Option(0, "--deliverables", help="[plan] Number of deliverables"),
    estimated_files: int = typer.Option(0, "--estimated-files", help="[plan] Estimated files"),
    security: bool = typer.Option(False, "--security", help="[plan] Security change"),
    schema: bool = typer.Option(False, "--schema", help="[plan] Schema change"),
    api: bool = typer.Option(False, "--api", help="[plan] API surface change"),
    review_score: Optional[float] = typer.Option(None, "--review-score", help="[plan] Plan review score"),
    new_feature: bool = typer.Option(True, "--new-feature/--no-new-feature", help="[plan] Is new feature"),
    depth: str = typer.Option("low", "--depth", help="[plan] Interaction depth: low|medium|high"),
) -> None:
    """Compute escalation score for plan or ship phase."""
    trust_adj = _get_trust_adjustment()

    if phase == "plan":
        result = compute_plan_escalation(
            deliverable_count=deliverables,
            estimated_files=estimated_files,
            has_security_change=security,
            has_schema_change=schema,
            has_api_change=api,
            plan_review_score=review_score,
            is_new_feature=new_feature,
            interaction_depth=depth,  # type: ignore[arg-type]
            trust_adjustment=trust_adj,
        )
    elif phase == "ship":
        diff_data = _get_ship_diff_data()
        try:
            cfg = HarnessConfig.load()
        except Exception:
            cfg = HarnessConfig()
        result = compute_ship_escalation(
            changed_files=diff_data["files"],
            total_additions=diff_data["additions"],
            total_deletions=diff_data["deletions"],
            commit_count=diff_data["commit_count"],
            trust_adjustment=trust_adj,
            gate_full_review_min=cfg.native.gate_full_review_min,
            gate_summary_confirm_min=cfg.native.gate_summary_confirm_min,
        )
    else:
        if as_json:
            typer.echo(json.dumps({"error": f"unknown phase: {phase}"}))
        else:
            typer.echo(f"Error: unknown phase '{phase}'", err=True)
        raise typer.Exit(1)

    if as_json:
        typer.echo(json.dumps(result.to_dict()))
    else:
        typer.echo(f"Escalation: {result.level.value} (score={result.score})")
        for s in result.signals:
            if s.triggered:
                typer.echo(f"  +{s.points} {s.name}: {s.detail}")
