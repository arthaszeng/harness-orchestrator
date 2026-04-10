"""Tests for harness.core.trust_engine — progressive trust computation."""

from __future__ import annotations

from harness.core.review_calibration import (
    CalibrationReport,
    ReviewActualOutcome,
    ReviewOutcome,
    ReviewPrediction,
    generate_calibration_report,
)
from harness.core.trust_engine import (
    TrustConfig,
    TrustLevel,
    TrustProfile,
    compute_trust_profile,
    _count_paired,
)


def _make_outcome(
    task_id: str = "task-001",
    accuracy_score: float | None = 8.0,
    ci_passed: bool | None = True,
    has_revert: bool | None = False,
    verdict: str = "PASS",
    updated_at: str = "",
) -> ReviewOutcome:
    return ReviewOutcome(
        task_id=task_id,
        prediction=ReviewPrediction(
            eval_aggregate=accuracy_score,
            verdict=verdict,
        ),
        outcome=ReviewActualOutcome(
            ci_passed=ci_passed,
            has_revert=has_revert,
        ),
        updated_at=updated_at or f"2026-04-{10:02d}T00:00:00Z",
    )


def _make_outcomes_for_level(
    count: int,
    accuracy_score: float = 8.5,
    ci_passed: bool = True,
    has_revert: bool = False,
) -> list[ReviewOutcome]:
    return [
        _make_outcome(
            task_id=f"task-{i:03d}",
            accuracy_score=accuracy_score,
            ci_passed=ci_passed,
            has_revert=has_revert,
            verdict="PASS" if ci_passed else "ITERATE",
            updated_at=f"2026-04-{i + 1:02d}T00:00:00Z",
        )
        for i in range(count)
    ]


# ── TrustLevel enum ───────────────────────────────────────

def test_trust_level_values():
    assert TrustLevel.HIGH == "HIGH"
    assert TrustLevel.MEDIUM == "MEDIUM"
    assert TrustLevel.LOW == "LOW"
    assert TrustLevel.PROBATION == "PROBATION"


# ── TrustConfig defaults and validation ──────────────────

def test_trust_config_defaults():
    cfg = TrustConfig()
    assert cfg.accuracy_high == 0.85
    assert cfg.accuracy_medium == 0.70
    assert cfg.min_samples_high == 10
    assert cfg.min_samples_medium == 5
    assert cfg.probation_revert_window == 3


def test_trust_config_custom():
    cfg = TrustConfig(
        accuracy_high=0.90,
        accuracy_medium=0.80,
        min_samples_high=20,
        min_samples_medium=10,
        probation_revert_window=5,
    )
    assert cfg.accuracy_high == 0.90
    assert cfg.min_samples_high == 20


def test_trust_config_extra_fields_ignored():
    cfg = TrustConfig.model_validate({"accuracy_high": 0.9, "unknown_field": 42})
    assert cfg.accuracy_high == 0.9


# ── HIGH trust level ──────────────────────────────────────

def test_high_trust_basic():
    outcomes = _make_outcomes_for_level(12, accuracy_score=8.5, ci_passed=True)
    report = generate_calibration_report(outcomes)
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.HIGH
    assert profile.escalation_adjustment == -2
    assert profile.threshold_adjustment == -0.5


def test_high_trust_boundary_accuracy():
    outcomes = _make_outcomes_for_level(10, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.85,
        has_sufficient_data=True,
        outcomes_with_prediction=10,
        outcomes_with_result=10,
        sample_count=10,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.HIGH


def test_high_trust_boundary_accuracy_below():
    outcomes = _make_outcomes_for_level(10, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.85 - 1e-9,
        has_sufficient_data=True,
        outcomes_with_prediction=10,
        outcomes_with_result=10,
        sample_count=10,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.MEDIUM


def test_high_trust_boundary_samples_exact():
    outcomes = _make_outcomes_for_level(10, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.90,
        has_sufficient_data=True,
        outcomes_with_prediction=10,
        outcomes_with_result=10,
        sample_count=10,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.HIGH


def test_high_trust_boundary_samples_below():
    outcomes = _make_outcomes_for_level(9, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.90,
        has_sufficient_data=True,
        outcomes_with_prediction=9,
        outcomes_with_result=9,
        sample_count=9,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.MEDIUM


# ── MEDIUM trust level ────────────────────────────────────

def test_medium_trust_basic():
    outcomes = _make_outcomes_for_level(6, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.75,
        has_sufficient_data=True,
        outcomes_with_prediction=6,
        outcomes_with_result=6,
        sample_count=6,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.MEDIUM
    assert profile.escalation_adjustment == -1
    assert profile.threshold_adjustment == 0.0


def test_medium_trust_boundary_accuracy():
    outcomes = _make_outcomes_for_level(5, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.70,
        has_sufficient_data=True,
        outcomes_with_prediction=5,
        outcomes_with_result=5,
        sample_count=5,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.MEDIUM


def test_medium_trust_boundary_samples_below():
    outcomes = _make_outcomes_for_level(4, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.90,
        has_sufficient_data=False,
        outcomes_with_prediction=4,
        outcomes_with_result=4,
        sample_count=4,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.LOW


def test_medium_trust_boundary_accuracy_below():
    outcomes = _make_outcomes_for_level(5, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.70 - 1e-9,
        has_sufficient_data=True,
        outcomes_with_prediction=5,
        outcomes_with_result=5,
        sample_count=5,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.LOW


# ── LOW trust level ───────────────────────────────────────

def test_low_trust_insufficient_data():
    outcomes = _make_outcomes_for_level(3, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.90,
        has_sufficient_data=False,
        outcomes_with_prediction=3,
        outcomes_with_result=3,
        sample_count=3,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.LOW
    assert profile.escalation_adjustment == 0
    assert "insufficient" in profile.reason.lower()


def test_low_trust_no_data():
    report = CalibrationReport()
    profile = compute_trust_profile(report, [])
    assert profile.level == TrustLevel.LOW
    assert profile.paired_samples == 0


def test_low_trust_accuracy_below_medium():
    outcomes = _make_outcomes_for_level(6, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.50,
        has_sufficient_data=True,
        outcomes_with_prediction=6,
        outcomes_with_result=6,
        sample_count=6,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.LOW
    assert "below" in profile.reason.lower()


def test_low_trust_no_accuracy():
    outcomes = _make_outcomes_for_level(6, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=None,
        has_sufficient_data=False,
        outcomes_with_prediction=6,
        outcomes_with_result=6,
        sample_count=6,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.LOW


# ── PROBATION trust level ─────────────────────────────────

def test_probation_overrides_high():
    outcomes = _make_outcomes_for_level(15, ci_passed=True, has_revert=False)
    outcomes[0] = _make_outcome(
        task_id="task-revert",
        ci_passed=True,
        has_revert=True,
        updated_at="2026-04-30T00:00:00Z",
    )
    report = CalibrationReport(
        prediction_accuracy=0.95,
        has_sufficient_data=True,
        outcomes_with_prediction=15,
        outcomes_with_result=15,
        sample_count=15,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.PROBATION
    assert profile.escalation_adjustment == 3
    assert profile.threshold_adjustment == 1.0
    assert profile.recent_revert_count == 1


def test_probation_revert_outside_window():
    outcomes = [
        _make_outcome(
            task_id=f"task-{i:03d}",
            ci_passed=True,
            has_revert=(i == 0),
            updated_at=f"2026-04-{i + 1:02d}T00:00:00Z",
        )
        for i in range(10)
    ]
    report = CalibrationReport(
        prediction_accuracy=0.90,
        has_sufficient_data=True,
        outcomes_with_prediction=10,
        outcomes_with_result=10,
        sample_count=10,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.HIGH


def test_probation_multiple_reverts():
    outcomes = _make_outcomes_for_level(5, ci_passed=True, has_revert=True)
    for i, o in enumerate(outcomes):
        o.updated_at = f"2026-04-{20 + i:02d}T00:00:00Z"
    report = CalibrationReport(
        prediction_accuracy=0.90,
        has_sufficient_data=True,
        outcomes_with_prediction=5,
        outcomes_with_result=5,
        sample_count=5,
    )
    profile = compute_trust_profile(report, outcomes)
    assert profile.level == TrustLevel.PROBATION
    assert profile.recent_revert_count == 3


def test_probation_custom_window():
    outcomes = _make_outcomes_for_level(10, ci_passed=True, has_revert=False)
    outcomes[0] = _make_outcome(
        task_id="task-old-revert",
        ci_passed=True,
        has_revert=True,
        updated_at="2026-04-01T00:00:00Z",
    )
    report = CalibrationReport(
        prediction_accuracy=0.90,
        has_sufficient_data=True,
        outcomes_with_prediction=10,
        outcomes_with_result=10,
        sample_count=10,
    )
    cfg_wide = TrustConfig(probation_revert_window=10)
    profile = compute_trust_profile(report, outcomes, config=cfg_wide)
    assert profile.level == TrustLevel.PROBATION

    cfg_narrow = TrustConfig(probation_revert_window=2)
    profile_narrow = compute_trust_profile(report, outcomes, config=cfg_narrow)
    assert profile_narrow.level == TrustLevel.HIGH


# ── TrustProfile model ────────────────────────────────────

def test_trust_profile_fields():
    profile = TrustProfile()
    assert profile.level == TrustLevel.LOW
    assert profile.escalation_adjustment == 0
    assert profile.threshold_adjustment == 0.0
    assert profile.reason == ""
    assert profile.prediction_accuracy is None
    assert profile.paired_samples == 0
    assert profile.recent_revert_count == 0


# ── _count_paired ─────────────────────────────────────────

def test_count_paired_all_paired():
    outcomes = _make_outcomes_for_level(5)
    assert _count_paired(outcomes) == 5


def test_count_paired_none_paired():
    outcomes = [
        _make_outcome(accuracy_score=None, ci_passed=None)
        for _ in range(3)
    ]
    assert _count_paired(outcomes) == 0


def test_count_paired_partial():
    outcomes = [
        _make_outcome(accuracy_score=8.0, ci_passed=True),
        _make_outcome(accuracy_score=None, ci_passed=True),
        _make_outcome(accuracy_score=7.0, ci_passed=None),
    ]
    assert _count_paired(outcomes) == 1


# ── Config integration ────────────────────────────────────

def test_config_custom_thresholds_affect_level():
    outcomes = _make_outcomes_for_level(8, ci_passed=True)
    report = CalibrationReport(
        prediction_accuracy=0.80,
        has_sufficient_data=True,
        outcomes_with_prediction=8,
        outcomes_with_result=8,
        sample_count=8,
    )
    profile_default = compute_trust_profile(report, outcomes)
    assert profile_default.level == TrustLevel.MEDIUM

    cfg_easy = TrustConfig(accuracy_high=0.75, min_samples_high=5)
    profile_easy = compute_trust_profile(report, outcomes, config=cfg_easy)
    assert profile_easy.level == TrustLevel.HIGH


# ── GateVerdict backward compatibility ────────────────────

def test_gate_verdict_default_trust_none():
    from harness.core.gates import GateVerdict

    verdict = GateVerdict(passed=True, checks=[])
    assert verdict.trust_level is None


def test_gate_verdict_with_trust_level():
    from harness.core.gates import GateVerdict

    verdict = GateVerdict(
        passed=True, checks=[], trust_level=TrustLevel.HIGH,
    )
    assert verdict.trust_level == TrustLevel.HIGH
