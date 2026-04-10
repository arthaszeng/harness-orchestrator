"""Tests for review calibration: data model, aggregation engine, and prediction sidecar."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.review_calibration import (
    ReviewActualOutcome,
    ReviewOutcome,
    ReviewPrediction,
    collect_outcomes,
    generate_calibration_report,
    load_review_outcome,
    save_review_outcome,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_outcome(
    task_id: str = "task-001",
    aggregate: float | None = 8.0,
    verdict: str = "PASS",
    ci_passed: bool | None = True,
    has_revert: bool | None = False,
    dimension_scores: dict[str, float] | None = None,
    finding_count: int = 2,
) -> ReviewOutcome:
    return ReviewOutcome(
        task_id=task_id,
        prediction=ReviewPrediction(
            eval_aggregate=aggregate,
            dimension_scores=dimension_scores or {},
            verdict=verdict,
            finding_count=finding_count,
        ),
        outcome=ReviewActualOutcome(
            ci_passed=ci_passed,
            has_revert=has_revert,
            recorded_at="2026-04-10T12:00:00+00:00",
        ),
    )


def _make_agents_dir(tmp_path: Path, task_ids: list[str]) -> Path:
    agents_dir = tmp_path / ".harness-flow"
    for tid in task_ids:
        (agents_dir / "tasks" / tid).mkdir(parents=True)
    return agents_dir


# ---------------------------------------------------------------------------
# D1: ReviewOutcome Data Model
# ---------------------------------------------------------------------------

class TestReviewOutcomeModel:
    def test_round_trip_serialization(self, tmp_path: Path):
        outcome = _make_outcome(
            task_id="task-042",
            aggregate=7.5,
            verdict="PASS",
            ci_passed=True,
            has_revert=False,
            dimension_scores={"Architecture": 8.0, "Engineering": 7.0},
        )
        path = save_review_outcome(tmp_path, outcome)
        assert path.exists()

        loaded = load_review_outcome(tmp_path)
        assert loaded is not None
        assert loaded.task_id == "task-042"
        assert loaded.prediction.eval_aggregate == 7.5
        assert loaded.prediction.verdict == "PASS"
        assert loaded.prediction.dimension_scores["Architecture"] == 8.0
        assert loaded.outcome.ci_passed is True
        assert loaded.outcome.has_revert is False

    def test_default_fields(self):
        outcome = ReviewOutcome(task_id="task-001")
        assert outcome.prediction.eval_aggregate is None
        assert outcome.prediction.dimension_scores == {}
        assert outcome.prediction.verdict == ""
        assert outcome.outcome.ci_passed is None
        assert outcome.outcome.has_revert is None

    def test_partial_prediction_serialization(self, tmp_path: Path):
        outcome = ReviewOutcome(
            task_id="task-003",
            prediction=ReviewPrediction(eval_aggregate=6.5),
        )
        save_review_outcome(tmp_path, outcome)
        loaded = load_review_outcome(tmp_path)
        assert loaded is not None
        assert loaded.prediction.eval_aggregate == 6.5
        assert loaded.prediction.verdict == ""
        assert loaded.outcome.ci_passed is None

    def test_idempotent_update(self, tmp_path: Path):
        outcome1 = _make_outcome(task_id="task-010", aggregate=7.0, ci_passed=None)
        save_review_outcome(tmp_path, outcome1)

        outcome2 = _make_outcome(task_id="task-010", aggregate=8.0, ci_passed=True)
        save_review_outcome(tmp_path, outcome2)

        loaded = load_review_outcome(tmp_path)
        assert loaded is not None
        assert loaded.prediction.eval_aggregate == 8.0
        assert loaded.outcome.ci_passed is True

    def test_load_missing_file(self, tmp_path: Path):
        assert load_review_outcome(tmp_path) is None

    def test_load_corrupt_json(self, tmp_path: Path):
        (tmp_path / "review-outcome.json").write_text("not json", encoding="utf-8")
        with pytest.warns(UserWarning, match="Corrupt"):
            result = load_review_outcome(tmp_path)
        assert result is None

    def test_load_invalid_schema(self, tmp_path: Path):
        (tmp_path / "review-outcome.json").write_text('{"task_id": 123}', encoding="utf-8")
        with pytest.warns(UserWarning, match="Invalid"):
            result = load_review_outcome(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# D2: Aggregation Engine
# ---------------------------------------------------------------------------

class TestCalibrationReport:
    def test_empty_outcomes(self):
        report = generate_calibration_report([])
        assert report.sample_count == 0
        assert report.prediction_accuracy is None
        assert report.has_sufficient_data is False
        assert report.dimension_biases == []

    def test_below_threshold_4_outcomes(self):
        outcomes = [
            _make_outcome(task_id=f"task-{i:03d}", aggregate=7.0 + i * 0.5, ci_passed=True)
            for i in range(4)
        ]
        report = generate_calibration_report(outcomes)
        assert report.sample_count == 4
        assert report.has_sufficient_data is False
        assert report.prediction_accuracy is not None

    def test_exactly_5_outcomes_sufficient(self):
        outcomes = [
            _make_outcome(task_id=f"task-{i:03d}", aggregate=7.0 + i * 0.5, ci_passed=True)
            for i in range(5)
        ]
        report = generate_calibration_report(outcomes)
        assert report.sample_count == 5
        assert report.has_sufficient_data is True
        assert report.prediction_accuracy is not None
        assert report.mean_aggregate_score is not None

    def test_prediction_accuracy_all_correct(self):
        outcomes = [
            _make_outcome(task_id=f"task-{i:03d}", aggregate=8.0, verdict="PASS", ci_passed=True)
            for i in range(5)
        ]
        report = generate_calibration_report(outcomes)
        assert report.prediction_accuracy == 1.0

    def test_prediction_accuracy_all_wrong(self):
        outcomes = [
            _make_outcome(task_id=f"task-{i:03d}", aggregate=8.0, verdict="PASS", ci_passed=False)
            for i in range(5)
        ]
        report = generate_calibration_report(outcomes)
        assert report.prediction_accuracy == 0.0

    def test_prediction_accuracy_mixed(self):
        outcomes = [
            _make_outcome(task_id="task-001", verdict="PASS", ci_passed=True),
            _make_outcome(task_id="task-002", verdict="PASS", ci_passed=False),
            _make_outcome(task_id="task-003", verdict="ITERATE", ci_passed=False),
            _make_outcome(task_id="task-004", verdict="PASS", ci_passed=True),
            _make_outcome(task_id="task-005", verdict="ITERATE", ci_passed=True),
        ]
        report = generate_calibration_report(outcomes)
        assert report.prediction_accuracy == pytest.approx(3 / 5)

    def test_dimension_biases(self):
        dims = {"Architecture": 9.0, "Engineering": 7.0, "QA": 8.0}
        outcomes = [
            _make_outcome(
                task_id=f"task-{i:03d}",
                aggregate=8.0,
                ci_passed=True,
                dimension_scores=dims,
            )
            for i in range(6)
        ]
        report = generate_calibration_report(outcomes)
        assert len(report.dimension_biases) == 3

        arch_bias = next(b for b in report.dimension_biases if b.dimension == "Architecture")
        assert arch_bias.mean_delta_from_aggregate == pytest.approx(1.0)

        eng_bias = next(b for b in report.dimension_biases if b.dimension == "Engineering")
        assert eng_bias.mean_delta_from_aggregate == pytest.approx(-1.0)

    def test_all_same_labels_no_crash(self):
        outcomes = [
            _make_outcome(task_id=f"task-{i:03d}", aggregate=8.0, verdict="PASS", ci_passed=True)
            for i in range(6)
        ]
        report = generate_calibration_report(outcomes)
        assert report.score_outcome_correlation is None

    def test_nan_aggregate_handled(self):
        outcomes = [
            _make_outcome(task_id=f"task-{i:03d}", aggregate=float("nan"), ci_passed=True)
            for i in range(6)
        ]
        report = generate_calibration_report(outcomes)
        assert report.mean_aggregate_score is None

    def test_missing_outcome_not_paired(self):
        outcomes = [
            _make_outcome(task_id=f"task-{i:03d}", aggregate=8.0, ci_passed=None)
            for i in range(6)
        ]
        report = generate_calibration_report(outcomes)
        assert report.has_sufficient_data is False
        assert report.outcomes_with_result == 0

    def test_10_outcomes_full_report(self):
        outcomes = []
        for i in range(10):
            ci = i % 3 != 0
            verdict = "PASS" if ci else "ITERATE"
            outcomes.append(_make_outcome(
                task_id=f"task-{i:03d}",
                aggregate=6.0 + i * 0.4,
                verdict=verdict,
                ci_passed=ci,
                dimension_scores={"Arch": 7.0 + i * 0.2, "Eng": 6.5 + i * 0.3},
            ))
        report = generate_calibration_report(outcomes)
        assert report.has_sufficient_data is True
        assert report.score_outcome_correlation is not None
        assert report.score_stddev is not None
        assert len(report.dimension_biases) == 2


# ---------------------------------------------------------------------------
# D2: collect_outcomes
# ---------------------------------------------------------------------------

class TestCollectOutcomes:
    def test_collect_from_task_dirs(self, tmp_path: Path):
        agents_dir = _make_agents_dir(tmp_path, ["task-001", "task-002", "task-003"])
        save_review_outcome(agents_dir / "tasks" / "task-001", _make_outcome(task_id="task-001"))
        save_review_outcome(agents_dir / "tasks" / "task-003", _make_outcome(task_id="task-003"))

        results = collect_outcomes(agents_dir)
        assert len(results) == 2
        ids = {r.task_id for r in results}
        assert ids == {"task-001", "task-003"}

    def test_collect_empty_dir(self, tmp_path: Path):
        agents_dir = _make_agents_dir(tmp_path, [])
        results = collect_outcomes(agents_dir)
        assert results == []


# ---------------------------------------------------------------------------
# D3: Prediction Sidecar (artifacts.py integration)
# ---------------------------------------------------------------------------

class TestPredictionSidecar:
    def test_save_evaluation_creates_sidecar(self, tmp_path: Path):
        from harness.core.artifacts import save_evaluation

        save_evaluation(
            tmp_path,
            kind="code",
            scores={
                "Architecture": {"role": "architect", "score": 8},
                "Engineering": {"role": "engineer", "score": 7},
            },
            findings=["Finding 1", "Finding 2"],
            verdict="PASS",
        )
        outcome = load_review_outcome(tmp_path)
        assert outcome is not None
        assert outcome.prediction.eval_aggregate == pytest.approx(7.5)
        assert outcome.prediction.verdict == "PASS"
        assert outcome.prediction.finding_count == 2
        assert "Architecture" in outcome.prediction.dimension_scores

    def test_plan_eval_no_sidecar(self, tmp_path: Path):
        from harness.core.artifacts import save_evaluation

        save_evaluation(tmp_path, kind="plan", verdict="PASS")
        assert load_review_outcome(tmp_path) is None

    def test_raw_body_sidecar(self, tmp_path: Path):
        from harness.core.artifacts import save_evaluation

        raw = (
            "# Code Evaluation — Round 1\n\n"
            "## Dimension Scores\n"
            "| Dimension | Role | Score |\n"
            "|-----------|------|-------|\n"
            "| Architecture | architect | 8.5/10 |\n"
            "| Engineering | engineer | 7.0/10 |\n"
            "| **Average** | | **7.8/10** |\n\n"
            "## Findings\n"
            "- [WARN] finding one\n"
            "- [INFO] finding two\n"
            "- [CRITICAL] finding three\n\n"
            "## Verdict: PASS\n"
        )
        save_evaluation(tmp_path, kind="code", raw_body=raw)
        outcome = load_review_outcome(tmp_path)
        assert outcome is not None
        assert outcome.prediction.eval_aggregate == pytest.approx(7.8)
        assert outcome.prediction.verdict == "PASS"
        assert outcome.prediction.finding_count == 3

    def test_raw_body_unparseable_degrades_gracefully(self, tmp_path: Path):
        from harness.core.artifacts import save_evaluation

        raw = "# Some random content with no structure\nNo verdict here\n"
        save_evaluation(tmp_path, kind="code", raw_body=raw)
        outcome = load_review_outcome(tmp_path)
        assert outcome is not None
        assert outcome.prediction.eval_aggregate is None
        assert outcome.prediction.verdict == ""

    def test_raw_body_variant_weighted_avg(self, tmp_path: Path):
        from harness.core.artifacts import save_evaluation

        raw = (
            "# Code Evaluation — Round 2\n\n"
            "Weighted avg: 8.1/10\n\n"
            "## Verdict: PASS\n"
        )
        save_evaluation(tmp_path, kind="code", raw_body=raw)
        outcome = load_review_outcome(tmp_path)
        assert outcome is not None
        assert outcome.prediction.eval_aggregate == pytest.approx(8.1)

    def test_multiple_rounds_update_prediction(self, tmp_path: Path):
        from harness.core.artifacts import save_evaluation

        save_evaluation(
            tmp_path, kind="code",
            scores={"Arch": {"score": 6}}, verdict="ITERATE",
        )
        first = load_review_outcome(tmp_path)
        assert first is not None
        assert first.prediction.eval_aggregate == pytest.approx(6.0)

        save_evaluation(
            tmp_path, kind="code",
            scores={"Arch": {"score": 8}}, verdict="PASS",
        )
        second = load_review_outcome(tmp_path)
        assert second is not None
        assert second.prediction.eval_aggregate == pytest.approx(8.0)
        assert second.prediction.verdict == "PASS"

    def test_raw_body_2col_dimension_scores(self, tmp_path: Path):
        """Score in column 2: | Role | X/10 | Verdict |."""
        from harness.core.artifacts import save_evaluation

        raw = (
            "# Code Evaluation\n\n"
            "| Role | Score | Verdict |\n"
            "|------|-------|---------|\n"
            "| Architect | 8/10 | ITERATE |\n"
            "| Product Owner | 8.5/10 | PASS |\n"
            "| Engineer | 5/10 | ITERATE |\n"
            "| QA | 8/10 | PASS |\n"
            "| **Average** | | **7.4/10** |\n\n"
            "## Verdict: PASS\n"
        )
        save_evaluation(tmp_path, kind="code", raw_body=raw)
        outcome = load_review_outcome(tmp_path)
        assert outcome is not None
        assert outcome.prediction.dimension_scores == {
            "Architect": 8.0,
            "Product Owner": 8.5,
            "Engineer": 5.0,
            "QA": 8.0,
        }

    def test_raw_body_3col_dimension_scores(self, tmp_path: Path):
        """Score in column 3: | Dim | PASS | X/10 |."""
        from harness.core.artifacts import save_evaluation

        raw = (
            "# Code Evaluation\n\n"
            "| Dimension | Verdict | Score |\n"
            "|-----------|---------|-------|\n"
            "| Architecture | PASS | 9/10 |\n"
            "| Engineering | ITERATE | 6.5/10 |\n"
            "| **Average** | | **7.8/10** |\n\n"
            "## Verdict: PASS\n"
        )
        save_evaluation(tmp_path, kind="code", raw_body=raw)
        outcome = load_review_outcome(tmp_path)
        assert outcome is not None
        assert outcome.prediction.dimension_scores == {
            "Architecture": 9.0,
            "Engineering": 6.5,
        }

    def test_raw_body_mixed_format_no_double_count(self, tmp_path: Path):
        """Both regexes match but setdefault prevents overwrite."""
        from harness.core.artifacts import save_evaluation

        raw = (
            "# Code Evaluation\n\n"
            "| Role | Score | Verdict |\n"
            "|------|-------|---------|\n"
            "| Architect | 8/10 | PASS |\n"
            "| **Average** | | **8.0/10** |\n\n"
            "## Verdict: PASS\n"
        )
        save_evaluation(tmp_path, kind="code", raw_body=raw)
        outcome = load_review_outcome(tmp_path)
        assert outcome is not None
        assert outcome.prediction.dimension_scores["Architect"] == 8.0
