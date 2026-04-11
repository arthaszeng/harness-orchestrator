"""Review calibration: prediction-vs-outcome tracking and cross-task aggregation.

Layer 1 — ``ReviewOutcome`` persists per-task prediction snapshots (eval
aggregate, dimension scores, verdict) alongside actual outcomes (CI result,
revert detection).

Layer 2 — ``generate_calibration_report`` aggregates across tasks to surface
systematic biases and prediction accuracy.

The calibration pipeline reads only ``review-outcome.json`` files; it does
**not** consume ``events.jsonl`` to avoid dual truth-source conflicts.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import warnings
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)

REVIEW_OUTCOME_FILENAME = "review-outcome.json"
MIN_SAMPLES_FOR_AGGREGATION = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Layer 1: Data Model ─────────────────────────────────────────


class ReviewPrediction(BaseModel):
    """Snapshot of the eval review prediction at ship time."""

    model_config = ConfigDict(extra="ignore")

    eval_aggregate: float | None = None
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    verdict: str = ""
    finding_count: int = 0


class ReviewActualOutcome(BaseModel):
    """Actual outcome collected after merge."""

    model_config = ConfigDict(extra="ignore")

    ci_passed: bool | None = None
    has_revert: bool | None = None
    recorded_at: str = ""


class ReviewOutcome(BaseModel):
    """Full prediction-vs-outcome record for a single task."""

    model_config = ConfigDict(extra="ignore")

    task_id: str = Field(default="", max_length=120)
    prediction: ReviewPrediction = Field(default_factory=ReviewPrediction)
    outcome: ReviewActualOutcome = Field(default_factory=ReviewActualOutcome)
    created_at: str = Field(default_factory=_now_iso, max_length=64)
    updated_at: str = Field(default_factory=_now_iso, max_length=64)


def save_review_outcome(task_dir: Path, outcome: ReviewOutcome) -> Path:
    """Write ``review-outcome.json`` to *task_dir* (idempotent)."""
    task_dir.mkdir(parents=True, exist_ok=True)
    payload = outcome.model_copy(update={"updated_at": _now_iso()})
    path = task_dir / REVIEW_OUTCOME_FILENAME
    path.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_review_outcome(task_dir: Path) -> ReviewOutcome | None:
    """Load ``review-outcome.json``, returning ``None`` on any failure."""
    path = task_dir / REVIEW_OUTCOME_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        warnings.warn(
            f"Corrupt review outcome at {path} ({type(exc).__name__})",
            stacklevel=2,
        )
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ReviewOutcome.model_validate(raw)
    except Exception as exc:
        warnings.warn(
            f"Invalid review outcome at {path} ({type(exc).__name__})",
            stacklevel=2,
        )
        return None


# ── Layer 2: Cross-task Aggregation Engine ───────────────────────


class DimensionBias(BaseModel):
    """Per-dimension aggregated bias relative to aggregate score."""

    model_config = ConfigDict(extra="ignore")

    dimension: str = ""
    mean_score: float = 0.0
    mean_delta_from_aggregate: float = 0.0
    sample_count: int = 0


class CalibrationReport(BaseModel):
    """Aggregated calibration statistics across tasks."""

    model_config = ConfigDict(extra="ignore")

    sample_count: int = 0
    outcomes_with_prediction: int = 0
    outcomes_with_result: int = 0
    prediction_accuracy: float | None = None
    mean_aggregate_score: float | None = None
    score_stddev: float | None = None
    dimension_biases: list[DimensionBias] = Field(default_factory=list)
    score_outcome_correlation: float | None = None
    has_sufficient_data: bool = False


def collect_outcomes(agents_dir: Path) -> list[ReviewOutcome]:
    """Scan all task and archive directories for ReviewOutcome files."""
    from harness.core.workflow_state import iter_archive_dirs, iter_task_dirs

    results: list[ReviewOutcome] = []
    for task_dir in iter_task_dirs(agents_dir) + iter_archive_dirs(agents_dir):
        outcome = load_review_outcome(task_dir)
        if outcome is not None:
            results.append(outcome)
    return results


def generate_calibration_report(outcomes: list[ReviewOutcome]) -> CalibrationReport:
    """Compute aggregated calibration statistics from *outcomes* (pure function)."""
    report = CalibrationReport(sample_count=len(outcomes))

    with_prediction = [o for o in outcomes if o.prediction.eval_aggregate is not None]
    with_result = [o for o in outcomes if o.outcome.ci_passed is not None]
    paired = [
        o for o in outcomes
        if o.prediction.eval_aggregate is not None and o.outcome.ci_passed is not None
    ]

    report.outcomes_with_prediction = len(with_prediction)
    report.outcomes_with_result = len(with_result)

    if len(with_prediction) >= MIN_SAMPLES_FOR_AGGREGATION:
        scores = [o.prediction.eval_aggregate for o in with_prediction if o.prediction.eval_aggregate is not None]
        finite_scores = [s for s in scores if math.isfinite(s)]
        if finite_scores:
            report.mean_aggregate_score = statistics.mean(finite_scores)
            if len(finite_scores) >= 2:
                report.score_stddev = statistics.stdev(finite_scores)

    if len(paired) >= MIN_SAMPLES_FOR_AGGREGATION:
        report.has_sufficient_data = True
        report.prediction_accuracy = _compute_prediction_accuracy(paired)
        report.score_outcome_correlation = _compute_point_biserial(paired)
        report.dimension_biases = _compute_dimension_biases(with_prediction)
    elif paired:
        report.prediction_accuracy = _compute_prediction_accuracy(paired)

    return report


def _compute_prediction_accuracy(paired: list[ReviewOutcome]) -> float | None:
    """Fraction of tasks where verdict=PASS aligned with ci_passed=True.

    Samples with empty verdict are excluded — they represent incomplete
    predictions that would skew the accuracy calculation.
    """
    with_verdict = [o for o in paired if o.prediction.verdict.strip()]
    if not with_verdict:
        return None
    correct = 0
    for o in with_verdict:
        verdict_positive = o.prediction.verdict.upper() == "PASS"
        outcome_positive = o.outcome.ci_passed is True
        if verdict_positive == outcome_positive:
            correct += 1
    return correct / len(with_verdict)


def _compute_point_biserial(paired: list[ReviewOutcome]) -> float | None:
    """Point-biserial correlation between eval_aggregate and ci_passed.

    Returns None when the computation is degenerate (zero variance, all same
    labels, etc.).
    """
    if len(paired) < 2:
        return None

    group_true = [
        o.prediction.eval_aggregate
        for o in paired
        if o.outcome.ci_passed is True and o.prediction.eval_aggregate is not None
    ]
    group_false = [
        o.prediction.eval_aggregate
        for o in paired
        if o.outcome.ci_passed is False and o.prediction.eval_aggregate is not None
    ]

    if not group_true or not group_false:
        return None

    n = len(group_true) + len(group_false)
    all_scores = group_true + group_false
    if len(all_scores) < 2:
        return None

    try:
        s_total = statistics.stdev(all_scores)
    except statistics.StatisticsError:
        return None
    if s_total == 0:
        return None

    m1 = statistics.mean(group_true)
    m0 = statistics.mean(group_false)
    n1 = len(group_true)
    n0 = len(group_false)

    r = ((m1 - m0) / s_total) * math.sqrt((n1 * n0) / (n * n))
    if not math.isfinite(r):
        return None
    return max(-1.0, min(1.0, r))


def _compute_dimension_biases(with_prediction: list[ReviewOutcome]) -> list[DimensionBias]:
    """Compute per-dimension bias (mean score delta from aggregate)."""
    dim_deltas: dict[str, list[float]] = {}
    dim_scores: dict[str, list[float]] = {}

    for o in with_prediction:
        agg = o.prediction.eval_aggregate
        if agg is None or not math.isfinite(agg):
            continue
        for dim, score in o.prediction.dimension_scores.items():
            if not math.isfinite(score):
                continue
            dim_deltas.setdefault(dim, []).append(score - agg)
            dim_scores.setdefault(dim, []).append(score)

    biases: list[DimensionBias] = []
    for dim in sorted(dim_deltas.keys()):
        deltas = dim_deltas[dim]
        scores = dim_scores[dim]
        if not deltas:
            continue
        biases.append(DimensionBias(
            dimension=dim,
            mean_score=statistics.mean(scores),
            mean_delta_from_aggregate=statistics.mean(deltas),
            sample_count=len(deltas),
        ))
    return biases
