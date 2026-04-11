"""harness review-score — deterministic review score calibration and verdict."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer

from harness.core.score_calibration import (
    apply_repeat_penalty,
    classify_score,
)

app = typer.Typer(help="Review score calibration and verdict")

PLAN_WEIGHTS: dict[str, float] = {
    "architect": 0.25,
    "product_owner": 0.20,
    "engineer": 0.25,
    "qa": 0.15,
    "project_manager": 0.15,
}

CODE_WEIGHTS: dict[str, float] = {
    "architect": 0.20,
    "product_owner": 0.10,
    "engineer": 0.30,
    "qa": 0.25,
    "project_manager": 0.15,
}

PLAN_PASS_THRESHOLD: float = 7.0
CODE_PASS_THRESHOLD: float = 7.0


def _validate_input(data: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Validate stdin JSON and return roles list."""
    if "roles" not in data:
        typer.echo(json.dumps({"error": "missing field: roles"}), err=True)
        raise typer.Exit(1)

    roles = data["roles"]
    if not isinstance(roles, list):
        typer.echo(json.dumps({"error": "roles must be a list"}), err=True)
        raise typer.Exit(1)

    for i, role in enumerate(roles):
        if not isinstance(role, dict):
            typer.echo(json.dumps({"error": f"roles[{i}] must be an object"}), err=True)
            raise typer.Exit(1)
        if "role" not in role or "score" not in role:
            typer.echo(json.dumps({"error": f"roles[{i}] missing 'role' or 'score'"}), err=True)
            raise typer.Exit(1)
        try:
            float(role["score"])
        except (TypeError, ValueError):
            typer.echo(json.dumps({"error": f"roles[{i}].score must be numeric"}), err=True)
            raise typer.Exit(1)

    return roles


def _compute_weighted_average(
    roles: list[dict[str, Any]],
    weights: dict[str, float],
) -> tuple[dict[str, float], float]:
    """Compute weighted average from per-role scores."""
    dimensions: dict[str, float] = {}
    total_weight = 0.0
    weighted_sum = 0.0

    for role_data in roles:
        role_name = role_data["role"]
        score = float(role_data["score"])
        weight = weights.get(role_name, 0.0)
        dimensions[role_name] = score
        weighted_sum += score * weight
        total_weight += weight

    if total_weight > 0:
        aggregate = weighted_sum / total_weight
    else:
        aggregate = sum(dimensions.values()) / max(1, len(dimensions))

    return dimensions, round(aggregate, 2)


def _has_critical(roles: list[dict[str, Any]]) -> bool:
    """Check if any role reported CRITICAL findings."""
    for role_data in roles:
        for finding in role_data.get("findings", []):
            severity = finding.get("severity", "").upper() if isinstance(finding, dict) else ""
            if severity == "CRITICAL":
                return True
    return False


def _collect_finding_texts(roles: list[dict[str, Any]]) -> list[str]:
    """Collect finding text strings for repeat penalty."""
    texts: list[str] = []
    for role_data in roles:
        for finding in role_data.get("findings", []):
            if isinstance(finding, dict):
                texts.append(finding.get("text", ""))
            elif isinstance(finding, str):
                texts.append(finding)
    return [t for t in texts if t]


@app.command("compute")
def compute_cmd(
    kind: str = typer.Option(
        ..., "--kind", "-k", help="Review kind: plan or code",
    ),
    as_json: bool = typer.Option(True, "--json/--no-json", help="JSON output"),
) -> None:
    """Compute calibrated review score and verdict from stdin JSON."""
    if sys.stdin.isatty():
        typer.echo(json.dumps({"error": "empty input"}), err=True)
        raise typer.Exit(1)

    raw_text = sys.stdin.read().strip()
    if not raw_text:
        typer.echo(json.dumps({"error": "empty input"}), err=True)
        raise typer.Exit(1)

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        typer.echo(json.dumps({"error": f"invalid json: {exc}"}), err=True)
        raise typer.Exit(1)

    if not isinstance(data, dict):
        typer.echo(json.dumps({"error": "expected a JSON object"}), err=True)
        raise typer.Exit(1)

    if kind == "plan":
        weights = PLAN_WEIGHTS
        threshold = PLAN_PASS_THRESHOLD
    elif kind == "code":
        weights = CODE_WEIGHTS
        threshold = CODE_PASS_THRESHOLD
    else:
        typer.echo(json.dumps({"error": f"unknown kind: {kind}"}), err=True)
        raise typer.Exit(1)

    roles = _validate_input(data, kind)
    dimensions, aggregate = _compute_weighted_average(roles, weights)

    current_findings = _collect_finding_texts(roles)
    prior_findings = data.get("prior_round_findings", [])
    calibrated = apply_repeat_penalty(
        base_score=aggregate,
        current_findings=current_findings,
        prior_round_findings=prior_findings if isinstance(prior_findings, list) else None,
    )

    has_crit = _has_critical(roles)
    if has_crit:
        verdict = "ITERATE"
    elif calibrated >= threshold:
        verdict = "PASS"
    else:
        verdict = "ITERATE"

    band = classify_score(calibrated)

    result = {
        "dimensions": dimensions,
        "aggregate": aggregate,
        "calibrated": round(calibrated, 2),
        "verdict": verdict,
        "has_critical": has_crit,
        "score_band": band.value if band else None,
        "calibration_applied": round(aggregate - calibrated, 2),
        "threshold": threshold,
    }

    if as_json:
        typer.echo(json.dumps(result))
    else:
        typer.echo(f"Verdict: {verdict} ({calibrated:.2f}/10, band={band.value if band else 'N/A'})")
