"""Tests for deterministic review score calibration helpers."""

from __future__ import annotations

from harness.core.score_calibration import (
    apply_repeat_penalty,
    dispersion_improvement_pct,
    normalize_finding_signature,
    score_dispersion,
)


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
    # Raw penalty would be 8 * 0.30 = 2.4, but capped at 1.5.
    assert adjusted == 7.5
