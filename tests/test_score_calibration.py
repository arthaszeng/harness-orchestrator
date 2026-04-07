"""Tests for score_calibration — existing helpers + ScoreBand, classify_score, parse_eval_aggregate_score."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.gates import parse_eval_aggregate_score
from harness.core.score_calibration import (
    ScoreBand,
    apply_repeat_penalty,
    classify_score,
    dispersion_improvement_pct,
    normalize_finding_signature,
    score_dispersion,
)


# ── Pre-existing calibration helper tests ────────────────────────


def test_normalize_finding_signature_removes_tags_and_noise():
    value = normalize_finding_signature("[HIGH CONFIDENCE] Missing null check in handler!")
    assert value == "MISSING NULL CHECK IN HANDLER"


def test_repeat_penalty_accumulates_and_caps():
    base = 8.5
    prior = [["Missing null check in handler"]]
    current = ["Missing null check in handler", "Missing null check in handler"]
    adjusted = apply_repeat_penalty(base_score=base, current_findings=current, prior_round_findings=prior)
    assert adjusted == 8.2


def test_high_confidence_repeat_has_extra_penalty():
    base = 8.5
    prior = [["Missing null check in handler"]]
    current = ["[HIGH CONFIDENCE] Missing null check in handler"]
    adjusted = apply_repeat_penalty(base_score=base, current_findings=current, prior_round_findings=prior)
    assert adjusted == 7.7


def test_dispersion_improvement_pct_positive_when_current_more_spread():
    baseline = [7.5, 8.0] * 15
    current = [6.8, 8.9] * 15
    assert score_dispersion(current) > score_dispersion(baseline)
    assert dispersion_improvement_pct(baseline=baseline, current=current) > 20.0


def test_repeat_penalty_total_cap_is_enforced():
    base = 9.0
    prior = [[f"Issue {i}" for i in range(8)]]
    current = [f"Issue {i}" for i in range(8)]
    adjusted = apply_repeat_penalty(base_score=base, current_findings=current, prior_round_findings=prior)
    assert adjusted == 7.5


# ── ScoreBand / classify_score ───────────────────────────────────


@pytest.mark.parametrize(
    "score, expected",
    [
        (10.0, ScoreBand.SHIP),
        (8.0, ScoreBand.SHIP),
        (9.5, ScoreBand.SHIP),
        (7.9, ScoreBand.ITERATE),
        (6.0, ScoreBand.ITERATE),
        (7.0, ScoreBand.ITERATE),
        (5.9, ScoreBand.REDO),
        (0.0, ScoreBand.REDO),
        (3.0, ScoreBand.REDO),
    ],
    ids=[
        "10.0→SHIP",
        "8.0→SHIP(boundary)",
        "9.5→SHIP",
        "7.9→ITERATE(boundary)",
        "6.0→ITERATE(boundary)",
        "7.0→ITERATE",
        "5.9→REDO(boundary)",
        "0.0→REDO",
        "3.0→REDO",
    ],
)
def test_classify_score_bands(score: float, expected: ScoreBand) -> None:
    assert classify_score(score) is expected


@pytest.mark.parametrize(
    "score, expected",
    [
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
    ],
    ids=["NaN→None", "inf→None", "-inf→None"],
)
def test_classify_score_non_finite(score: float, expected: None) -> None:
    assert classify_score(score) is expected


def test_classify_score_clamp_above_10() -> None:
    assert classify_score(12.0) is ScoreBand.SHIP


def test_classify_score_clamp_below_0() -> None:
    assert classify_score(-3.0) is ScoreBand.REDO


# --- parse_eval_aggregate_score ---


@pytest.mark.parametrize(
    "content, expected",
    [
        ("Weighted avg:  8.2/10\n", 8.2),
        ("Weighted Average: 7.0/10", 7.0),
        ("| **Average** | **6.5/10** |", 6.5),
        ("Weighted avg: **9.0**/10\n", 9.0),
        ("no score here", None),
        ("", None),
        ("Weighted avg: NaN/10", None),
    ],
    ids=[
        "weighted_avg",
        "weighted_average",
        "table_bold",
        "bold_number",
        "no_match",
        "empty",
        "nan_in_text",
    ],
)
def test_parse_eval_aggregate_score(content: str, expected: float | None) -> None:
    result = parse_eval_aggregate_score(content)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


# --- CLI integration: gate output includes score band ---

runner = CliRunner()


def test_classify_score_non_numeric_inputs() -> None:
    """Non-numeric inputs should return None gracefully."""
    assert classify_score(None) is None  # type: ignore[arg-type]
    assert classify_score("8.5") is ScoreBand.SHIP  # type: ignore[arg-type]
    assert classify_score("x") is None  # type: ignore[arg-type]


def _make_gate_task(tmp_path, score: str, verdict: str = "PASS"):
    """Helper: create minimal task structure for gate CLI test."""
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-099"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "plan.md").write_text("# Plan\nSome content\n")
    (task_dir / "code-eval-r1.md").write_text(
        f"# Eval\n## Verdict: {verdict}\nWeighted avg: {score}/10\n"
    )
    return task_dir


@pytest.mark.parametrize(
    "score, expected_keywords, verdict",
    [
        ("8.5", ["shippable", "可发布"], "PASS"),
        ("7.0", ["iteration", "迭代"], "PASS"),
        ("4.0", ["re-planning", "返工"], "PASS"),
    ],
    ids=["SHIP", "ITERATE", "REDO"],
)
def test_gate_output_score_band_all_tiers(
    tmp_path, monkeypatch, score: str, expected_keywords: list[str], verdict: str,
) -> None:
    """Gate output should include correct band text for each tier."""
    _make_gate_task(tmp_path, score, verdict)
    monkeypatch.chdir(tmp_path)

    from harness.core import gates as gates_mod
    monkeypatch.setattr(gates_mod, "get_head_commit_epoch", lambda _: None)

    result = runner.invoke(app, ["gate", "--task", "task-099"])
    assert result.exit_code == 0
    assert f"{score}/10" in result.output
    assert any(kw in result.output.lower() for kw in expected_keywords)


def test_gate_blocked_does_not_show_score_band(tmp_path, monkeypatch) -> None:
    """When gate is blocked, score band should NOT appear even if score exists."""
    _make_gate_task(tmp_path, "8.5", "ITERATE")
    monkeypatch.chdir(tmp_path)

    from harness.core import gates as gates_mod
    monkeypatch.setattr(gates_mod, "get_head_commit_epoch", lambda _: None)

    result = runner.invoke(app, ["gate", "--task", "task-099"])
    assert result.exit_code == 1
    assert "shippable" not in result.output.lower()
    assert "可发布" not in result.output
