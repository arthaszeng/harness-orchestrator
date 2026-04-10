"""harness trust — display progressive trust profile."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from harness.core.ui import get_ui


def run_trust(
    *,
    as_json: bool = False,
) -> None:
    """Compute and display the current trust profile."""
    from pydantic import ValidationError

    from harness.core.config import HarnessConfig
    from harness.core.review_calibration import (
        collect_outcomes,
        generate_calibration_report,
    )
    from harness.core.trust_engine import TrustConfig, compute_trust_profile

    ui = get_ui()

    try:
        cfg = HarnessConfig.load()
        trust_cfg = cfg.workflow.trust
    except (OSError, ValueError, KeyError, ValidationError):
        trust_cfg = TrustConfig()

    agents_dir = Path.cwd() / ".harness-flow"
    outcomes = collect_outcomes(agents_dir)

    if not outcomes:
        profile = compute_trust_profile(
            report=generate_calibration_report([]),
            outcomes=[],
            config=trust_cfg,
        )
        if as_json:
            json.dump(
                {"level": profile.level.value, "reason": "insufficient data"},
                sys.stdout,
            )
            sys.stdout.write("\n")
        else:
            from rich.console import Console

            console = Console()
            console.print(
                f"\nTrust: [cyan]{profile.level.value}[/] — insufficient data. "
                "Run evaluations and record outcomes to build trust history.\n"
            )
        return

    report = generate_calibration_report(outcomes)
    profile = compute_trust_profile(
        report=report,
        outcomes=outcomes,
        config=trust_cfg,
    )

    if as_json:
        _print_json(profile, report)
    else:
        _print_rich(profile, report, ui)


def _print_json(profile, report) -> None:
    data = {
        "level": profile.level.value,
        "escalation_adjustment": profile.escalation_adjustment,
        "threshold_adjustment": profile.threshold_adjustment,
        "reason": profile.reason,
        "prediction_accuracy": profile.prediction_accuracy,
        "paired_samples": profile.paired_samples,
        "recent_revert_count": profile.recent_revert_count,
        "calibration": {
            "sample_count": report.sample_count,
            "has_sufficient_data": report.has_sufficient_data,
        },
    }
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _print_rich(profile, report, ui) -> None:
    from rich.console import Console

    from harness.core.trust_engine import TrustLevel

    console = Console()

    level_colors = {
        TrustLevel.HIGH: "green",
        TrustLevel.MEDIUM: "yellow",
        TrustLevel.LOW: "cyan",
        TrustLevel.PROBATION: "red",
    }
    color = level_colors.get(profile.level, "white")

    console.print()
    console.print("TRUST PROFILE")
    console.print("═" * 50)
    console.print(f"  Level:                [{color}]{profile.level.value}[/]")
    console.print(f"  Reason:               {profile.reason}")
    console.print()
    console.print("ADJUSTMENTS (advisory)")
    console.print("─" * 50)
    esc_sign = "+" if profile.escalation_adjustment >= 0 else ""
    thr_sign = "+" if profile.threshold_adjustment >= 0 else ""
    console.print(f"  Escalation:           {esc_sign}{profile.escalation_adjustment}")
    console.print(f"  Threshold:            {thr_sign}{profile.threshold_adjustment:.1f}")
    console.print()
    console.print("SUPPORTING DATA")
    console.print("─" * 50)
    if profile.prediction_accuracy is not None:
        console.print(f"  Prediction accuracy:  {profile.prediction_accuracy:.1%}")
    else:
        console.print("  Prediction accuracy:  —")
    console.print(f"  Paired samples:       {profile.paired_samples}")
    console.print(f"  Recent reverts:       {profile.recent_revert_count}")
    console.print(f"  Total outcomes:       {report.sample_count}")
    console.print()
