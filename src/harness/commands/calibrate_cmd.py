"""harness calibrate — review calibration report across tasks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from harness.core.ui import get_ui


def run_calibrate(
    *,
    task: str | None = None,
    as_json: bool = False,
) -> None:
    """Generate or display review calibration data."""
    from harness.core.review_calibration import (
        collect_outcomes,
        generate_calibration_report,
    )

    agents_dir = Path.cwd() / ".harness-flow"
    ui = get_ui()

    if task:
        _show_single_task(
            agents_dir=agents_dir, task=task, as_json=as_json, ui=ui,
        )
        return

    outcomes = collect_outcomes(agents_dir)
    if not outcomes:
        if as_json:
            json.dump({"error": "no_data", "message": "No review outcomes found"}, sys.stdout)
            sys.stdout.write("\n")
        else:
            ui.info("No review outcomes found. Run evaluations with 'harness save-eval' to populate data.")
        return

    report = generate_calibration_report(outcomes)

    if as_json:
        _print_json_report(report, outcomes)
    else:
        _print_rich_report(report, outcomes, ui)


def _show_single_task(
    *,
    agents_dir: Path,
    task: str,
    as_json: bool,
    ui: object,
) -> None:
    from harness.core.review_calibration import load_review_outcome

    task_dir = agents_dir / "tasks" / task
    if not task_dir.is_dir():
        archive_dir = agents_dir / "archive" / task
        if archive_dir.is_dir():
            task_dir = archive_dir
        else:
            if as_json:
                json.dump({"error": "not_found", "task": task}, sys.stdout)
                sys.stdout.write("\n")
            else:
                ui.warn(f"Task directory not found: {task}")  # type: ignore[attr-defined]
            raise SystemExit(1)

    outcome = load_review_outcome(task_dir)
    if outcome is None:
        if as_json:
            json.dump({"error": "no_outcome", "task": task}, sys.stdout)
            sys.stdout.write("\n")
        else:
            ui.info(f"No review outcome for {task}")  # type: ignore[attr-defined]
        return

    if as_json:
        sys.stdout.write(outcome.model_dump_json(indent=2) + "\n")
    else:
        ui.info(f"Review outcome for {task}:")  # type: ignore[attr-defined]
        _print_outcome_summary(outcome, ui)


def _print_outcome_summary(outcome: "ReviewOutcome", ui: object) -> None:  # noqa: F821
    from rich.console import Console

    console = Console()
    pred = outcome.prediction
    act = outcome.outcome

    if pred.eval_aggregate is not None:
        console.print(f"  Prediction:  {pred.eval_aggregate:.1f}/10 ({pred.verdict})")
    else:
        console.print("  Prediction:  (not recorded)")

    if pred.dimension_scores:
        dims = ", ".join(f"{k}: {v:.1f}" for k, v in pred.dimension_scores.items())
        console.print(f"  Dimensions:  {dims}")

    if act.ci_passed is not None:
        ci_str = "PASSED" if act.ci_passed else "FAILED"
        console.print(f"  CI result:   {ci_str}")
    else:
        console.print("  CI result:   (not recorded)")

    if act.has_revert is not None:
        revert_str = "Yes" if act.has_revert else "No"
        console.print(f"  Has revert:  {revert_str}")


def _print_json_report(
    report: "CalibrationReport",  # noqa: F821
    outcomes: list,
) -> None:
    data = {
        "report": json.loads(report.model_dump_json()),
        "outcomes": [json.loads(o.model_dump_json()) for o in outcomes],
    }
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _print_rich_report(
    report: "CalibrationReport",  # noqa: F821
    outcomes: list,
    ui: object,
) -> None:
    from rich.console import Console

    from harness.core.review_calibration import MIN_SAMPLES_FOR_AGGREGATION

    console = Console()

    console.print()
    console.print("REVIEW CALIBRATION REPORT")
    console.print("═" * 50)
    console.print(f"  Total outcomes:       {report.sample_count}")
    console.print(f"  With prediction:      {report.outcomes_with_prediction}")
    console.print(f"  With actual result:   {report.outcomes_with_result}")
    paired_count = min(report.outcomes_with_prediction, report.outcomes_with_result)
    console.print(f"  Paired (pred+result): {paired_count}")
    console.print()

    if report.has_sufficient_data:
        console.print("AGGREGATED STATISTICS")
        console.print("─" * 50)
        if report.prediction_accuracy is not None:
            console.print(f"  Prediction accuracy:  {report.prediction_accuracy:.1%}")
        if report.mean_aggregate_score is not None:
            std_str = f" (σ={report.score_stddev:.2f})" if report.score_stddev is not None else ""
            console.print(f"  Mean aggregate score: {report.mean_aggregate_score:.2f}/10{std_str}")
        if report.score_outcome_correlation is not None:
            console.print(f"  Score-outcome corr:   {report.score_outcome_correlation:.3f}")
        console.print()

        if report.dimension_biases:
            console.print("DIMENSION BIASES (delta from aggregate)")
            console.print("─" * 50)
            for bias in report.dimension_biases:
                sign = "+" if bias.mean_delta_from_aggregate >= 0 else ""
                console.print(
                    f"  {bias.dimension:20s}  "
                    f"mean={bias.mean_score:.1f}  "
                    f"delta={sign}{bias.mean_delta_from_aggregate:.2f}  "
                    f"(n={bias.sample_count})"
                )
            console.print()
    else:
        console.print(
            f"  Insufficient data for aggregation "
            f"(need {MIN_SAMPLES_FOR_AGGREGATION}, have {paired_count} paired outcomes)"
        )
        if report.mean_aggregate_score is not None:
            console.print(f"  Mean prediction score: {report.mean_aggregate_score:.2f}/10")
        if report.prediction_accuracy is not None:
            console.print(f"  Preliminary accuracy: {report.prediction_accuracy:.1%}")
        console.print()

    if outcomes:
        console.print("INDIVIDUAL OUTCOMES")
        console.print("─" * 50)
        for o in outcomes:
            pred_str = f"{o.prediction.eval_aggregate:.1f}" if o.prediction.eval_aggregate is not None else "—"
            verdict_str = o.prediction.verdict or "—"
            if o.outcome.ci_passed is True:
                ci_str = "✓"
            elif o.outcome.ci_passed is False:
                ci_str = "✗"
            else:
                ci_str = "—"
            console.print(f"  {o.task_id:16s}  score={pred_str:>5s}/10  verdict={verdict_str:7s}  ci={ci_str}")
        console.print()
