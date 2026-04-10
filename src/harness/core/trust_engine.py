"""Progressive trust engine — compute trust level from calibration history.

Pure-function module: no I/O, no side effects. All inputs (CalibrationReport,
ReviewOutcome list, TrustConfig) are provided by the caller.

Trust levels influence escalation score *advisory* only — they never change
hard gate pass/block semantics.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from harness.core.review_calibration import CalibrationReport, ReviewOutcome


class TrustLevel(str, Enum):
    """Discrete trust levels ordered from most to least trusted."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    PROBATION = "PROBATION"


_LEVEL_META: dict[TrustLevel, dict] = {
    TrustLevel.HIGH: {
        "escalation_adjustment": -2,
        "threshold_adjustment": -0.5,
        "description": "High historical accuracy — suggest lighter review",
    },
    TrustLevel.MEDIUM: {
        "escalation_adjustment": -1,
        "threshold_adjustment": 0.0,
        "description": "Moderate accuracy — standard review intensity",
    },
    TrustLevel.LOW: {
        "escalation_adjustment": 0,
        "threshold_adjustment": 0.0,
        "description": "Insufficient data — conservative review",
    },
    TrustLevel.PROBATION: {
        "escalation_adjustment": 3,
        "threshold_adjustment": 1.0,
        "description": "Recent revert detected — intensified review",
    },
}


class TrustProfile(BaseModel):
    """Computed trust profile for a project."""

    model_config = ConfigDict(extra="ignore")

    level: TrustLevel = TrustLevel.LOW
    escalation_adjustment: int = 0
    threshold_adjustment: float = 0.0
    reason: str = ""
    prediction_accuracy: float | None = None
    paired_samples: int = 0
    recent_revert_count: int = 0


class TrustConfig(BaseModel):
    """Configuration for trust level thresholds.

    Embedded under ``[workflow.trust]`` in config.toml.
    """

    model_config = ConfigDict(extra="ignore")

    accuracy_high: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum prediction accuracy for HIGH trust.",
    )
    accuracy_medium: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum prediction accuracy for MEDIUM trust.",
    )
    min_samples_high: int = Field(
        default=10,
        ge=1,
        description="Minimum paired samples for HIGH trust.",
    )
    min_samples_medium: int = Field(
        default=5,
        ge=1,
        description="Minimum paired samples for MEDIUM trust.",
    )
    probation_revert_window: int = Field(
        default=3,
        ge=1,
        description="Number of most recent tasks to scan for reverts.",
    )


def compute_trust_profile(
    report: CalibrationReport,
    outcomes: list[ReviewOutcome],
    config: TrustConfig | None = None,
) -> TrustProfile:
    """Compute the trust profile from calibration data (pure function).

    Priority: PROBATION (if recent revert) > HIGH > MEDIUM > LOW.
    """
    cfg = config or TrustConfig()

    sorted_outcomes = sorted(
        outcomes,
        key=lambda o: o.updated_at or o.created_at or "",
        reverse=True,
    )

    window = sorted_outcomes[: cfg.probation_revert_window]
    recent_revert_count = sum(
        1 for o in window if o.outcome.has_revert is True
    )

    paired = _count_paired(outcomes)
    accuracy = report.prediction_accuracy

    if recent_revert_count > 0:
        level = TrustLevel.PROBATION
        reason = (
            f"{recent_revert_count} revert(s) in last "
            f"{cfg.probation_revert_window} tasks"
        )
    elif (
        accuracy is not None
        and accuracy >= cfg.accuracy_high
        and paired >= cfg.min_samples_high
    ):
        level = TrustLevel.HIGH
        reason = (
            f"accuracy {accuracy:.2%} >= {cfg.accuracy_high:.0%}, "
            f"{paired} paired >= {cfg.min_samples_high}"
        )
    elif (
        accuracy is not None
        and accuracy >= cfg.accuracy_medium
        and paired >= cfg.min_samples_medium
    ):
        level = TrustLevel.MEDIUM
        reason = (
            f"accuracy {accuracy:.2%} >= {cfg.accuracy_medium:.0%}, "
            f"{paired} paired >= {cfg.min_samples_medium}"
        )
    else:
        level = TrustLevel.LOW
        if paired < cfg.min_samples_medium:
            reason = f"insufficient data ({paired} paired < {cfg.min_samples_medium})"
        elif accuracy is not None:
            reason = f"accuracy {accuracy:.2%} below {cfg.accuracy_medium:.0%} threshold"
        else:
            reason = "no prediction accuracy available"

    meta = _LEVEL_META[level]
    return TrustProfile(
        level=level,
        escalation_adjustment=meta["escalation_adjustment"],
        threshold_adjustment=meta["threshold_adjustment"],
        reason=reason,
        prediction_accuracy=accuracy,
        paired_samples=paired,
        recent_revert_count=recent_revert_count,
    )


def _count_paired(outcomes: list[ReviewOutcome]) -> int:
    """Count outcomes that have both prediction aggregate and CI result."""
    return sum(
        1
        for o in outcomes
        if o.prediction.eval_aggregate is not None
        and o.outcome.ci_passed is not None
    )
