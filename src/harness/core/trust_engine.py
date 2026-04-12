"""Progressive trust engine — compute trust level from calibration history.

Pure-function module: no I/O, no side effects. All inputs (CalibrationReport,
ReviewOutcome list, TrustConfig) are provided by the caller.

Trust levels influence two dimensions of the review pipeline:
1. **Escalation score** (always active) — ``escalation_adjustment`` shifts
   the review intensity (FAST / LITE / FULL).
2. **Pass threshold** (opt-in via ``WorkflowConfig.apply_trust_threshold``) —
   ``threshold_adjustment`` shifts the effective score threshold for the ship
   gate.  When disabled (default), the threshold is the fixed
   ``pass_threshold`` from config.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from harness.core.review_calibration import CalibrationReport, ReviewOutcome


class TrustLevel(str, Enum):
    """Discrete trust levels ordered from most to least trusted."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    PROBATION = "PROBATION"


class TrustLevelMeta(BaseModel):
    """Metadata for a trust level — public API for display consumers."""

    model_config = ConfigDict(frozen=True)

    escalation_adjustment: int = 0
    threshold_adjustment: float = 0.0
    description: str = ""


TRUST_LEVEL_META: dict[TrustLevel, TrustLevelMeta] = {
    TrustLevel.HIGH: TrustLevelMeta(
        escalation_adjustment=-2,
        threshold_adjustment=-0.5,
        description="High historical accuracy — suggest lighter review",
    ),
    TrustLevel.MEDIUM: TrustLevelMeta(
        escalation_adjustment=-1,
        threshold_adjustment=0.0,
        description="Moderate accuracy — standard review intensity",
    ),
    TrustLevel.LOW: TrustLevelMeta(
        escalation_adjustment=0,
        threshold_adjustment=0.0,
        description="Insufficient data — conservative review",
    ),
    TrustLevel.PROBATION: TrustLevelMeta(
        escalation_adjustment=3,
        threshold_adjustment=1.0,
        description="Recent revert detected — intensified review",
    ),
}


def get_trust_level_meta(level: TrustLevel) -> TrustLevelMeta:
    """Public API to retrieve trust level metadata for display."""
    return TRUST_LEVEL_META.get(level, TrustLevelMeta())


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

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "TrustConfig":
        if self.accuracy_high < self.accuracy_medium:
            import warnings

            warnings.warn(
                f"accuracy_high ({self.accuracy_high}) < accuracy_medium "
                f"({self.accuracy_medium}); HIGH trust will be unreachable",
                UserWarning,
                stacklevel=2,
            )
        if self.min_samples_high < self.min_samples_medium:
            import warnings

            warnings.warn(
                f"min_samples_high ({self.min_samples_high}) < min_samples_medium "
                f"({self.min_samples_medium}); HIGH trust will be unreachable",
                UserWarning,
                stacklevel=2,
            )
        return self


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
        key=lambda o: (o.updated_at or o.created_at or "", o.task_id),
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

    meta = TRUST_LEVEL_META[level]
    return TrustProfile(
        level=level,
        escalation_adjustment=meta.escalation_adjustment,
        threshold_adjustment=meta.threshold_adjustment,
        reason=reason,
        prediction_accuracy=accuracy,
        paired_samples=paired,
        recent_revert_count=recent_revert_count,
    )


EFFECTIVE_THRESHOLD_MIN: float = 5.0
EFFECTIVE_THRESHOLD_MAX: float = 10.0


def compute_effective_threshold(
    base_threshold: float,
    trust_profile: TrustProfile | None = None,
    *,
    apply: bool = False,
) -> float:
    """Compute the effective pass threshold after trust adjustment.

    When *apply* is False or *trust_profile* is None, returns *base_threshold*
    unchanged — preserving backward-compatible behavior.

    The result is clamped to [EFFECTIVE_THRESHOLD_MIN, EFFECTIVE_THRESHOLD_MAX].
    """
    if not apply or trust_profile is None:
        return base_threshold
    raw = base_threshold + trust_profile.threshold_adjustment
    return max(EFFECTIVE_THRESHOLD_MIN, min(EFFECTIVE_THRESHOLD_MAX, raw))


def _count_paired(outcomes: list[ReviewOutcome]) -> int:
    """Count outcomes that have both prediction aggregate and CI result."""
    return sum(
        1
        for o in outcomes
        if o.prediction.eval_aggregate is not None
        and o.outcome.ci_passed is not None
    )
