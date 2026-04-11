"""Deterministic escalation score computation for plan and ship phases.

Replaces template-embedded LLM arithmetic with millisecond-level CLI logic.
Integrates with trust_engine.escalation_adjustment for advisory score tuning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


RISK_DIR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|/)(?:auth|security|crypto|secrets?|cred)(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)migrations?/", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:schema|models?)/", re.IGNORECASE),
]

API_SURFACE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|/)(?:api|routes?|endpoints?|views?|handlers?)/", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:cli|commands?)/", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:proto|graphql|openapi)/", re.IGNORECASE),
]


class EscalationLevel(str, Enum):
    FAST = "FAST"
    LITE = "LITE"
    FULL = "FULL"


@dataclass
class EscalationSignal:
    name: str
    triggered: bool
    points: int
    detail: str = ""


@dataclass
class EscalationResult:
    score: int
    level: EscalationLevel
    signals: list[EscalationSignal] = field(default_factory=list)
    trust_adjustment: int = 0
    raw_score: int = 0

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "level": self.level.value,
            "raw_score": self.raw_score,
            "trust_adjustment": self.trust_adjustment,
            "signals": [
                {
                    "name": s.name,
                    "triggered": s.triggered,
                    "points": s.points,
                    "detail": s.detail,
                }
                for s in self.signals
            ],
        }


def _count_risk_dirs(files: list[str]) -> int:
    matched = set()
    for f in files:
        for pat in RISK_DIR_PATTERNS:
            if pat.search(f):
                matched.add(pat.pattern)
    return len(matched)


def _count_api_surface(files: list[str]) -> int:
    matched = set()
    for f in files:
        for pat in API_SURFACE_PATTERNS:
            if pat.search(f):
                matched.add(pat.pattern)
    return len(matched)


def compute_plan_escalation(
    *,
    deliverable_count: int,
    estimated_files: int,
    has_security_change: bool = False,
    has_schema_change: bool = False,
    has_api_change: bool = False,
    plan_review_score: float | None = None,
    is_new_feature: bool = True,
    interaction_depth: Literal["low", "medium", "high"] = "low",
    trust_adjustment: int = 0,
) -> EscalationResult:
    """Compute plan-phase escalation score from plan metadata."""
    signals: list[EscalationSignal] = []
    raw = 0

    sig = EscalationSignal(
        name="deliverable_count",
        triggered=deliverable_count > 5,
        points=2 if deliverable_count > 5 else 0,
        detail=f"{deliverable_count} deliverables",
    )
    raw += sig.points
    signals.append(sig)

    sig = EscalationSignal(
        name="file_count",
        triggered=estimated_files > 10,
        points=2 if estimated_files > 10 else 0,
        detail=f"~{estimated_files} files",
    )
    raw += sig.points
    signals.append(sig)

    sig = EscalationSignal(
        name="security_change",
        triggered=has_security_change,
        points=3 if has_security_change else 0,
    )
    raw += sig.points
    signals.append(sig)

    sig = EscalationSignal(
        name="schema_change",
        triggered=has_schema_change,
        points=3 if has_schema_change else 0,
    )
    raw += sig.points
    signals.append(sig)

    sig = EscalationSignal(
        name="api_surface_change",
        triggered=has_api_change,
        points=2 if has_api_change else 0,
    )
    raw += sig.points
    signals.append(sig)

    low_review = plan_review_score is not None and plan_review_score < 7.0
    sig = EscalationSignal(
        name="low_review_score",
        triggered=low_review,
        points=2 if low_review else 0,
        detail=f"score={plan_review_score}" if plan_review_score is not None else "",
    )
    raw += sig.points
    signals.append(sig)

    sig = EscalationSignal(
        name="new_feature",
        triggered=is_new_feature,
        points=1 if is_new_feature else 0,
    )
    raw += sig.points
    signals.append(sig)

    depth_map = {"high": -2, "medium": -1, "low": 0}
    depth_adj = depth_map.get(interaction_depth, 0)
    sig = EscalationSignal(
        name="interaction_depth",
        triggered=depth_adj != 0,
        points=depth_adj,
        detail=interaction_depth,
    )
    raw += sig.points
    signals.append(sig)

    final = max(0, raw + trust_adjustment)
    level = _score_to_level(final)

    return EscalationResult(
        score=final,
        level=level,
        signals=signals,
        trust_adjustment=trust_adjustment,
        raw_score=raw,
    )


def compute_ship_escalation(
    *,
    changed_files: list[str],
    total_additions: int = 0,
    total_deletions: int = 0,
    commit_count: int = 1,
    trust_adjustment: int = 0,
    gate_full_review_min: int = 5,
    gate_summary_confirm_min: int = 3,
) -> EscalationResult:
    """Compute ship-phase escalation score from git diff/log signals."""
    signals: list[EscalationSignal] = []
    raw = 0

    total_lines = total_additions + total_deletions
    large_diff = total_lines > 500
    sig = EscalationSignal(
        name="diff_size",
        triggered=large_diff,
        points=2 if large_diff else 0,
        detail=f"+{total_additions}/-{total_deletions}",
    )
    raw += sig.points
    signals.append(sig)

    many_files = len(changed_files) > 10
    sig = EscalationSignal(
        name="file_count",
        triggered=many_files,
        points=2 if many_files else 0,
        detail=f"{len(changed_files)} files",
    )
    raw += sig.points
    signals.append(sig)

    risk_count = _count_risk_dirs(changed_files)
    sig = EscalationSignal(
        name="risk_directories",
        triggered=risk_count > 0,
        points=min(3, risk_count * 2),
        detail=f"{risk_count} risk patterns matched",
    )
    raw += sig.points
    signals.append(sig)

    api_count = _count_api_surface(changed_files)
    sig = EscalationSignal(
        name="api_surface",
        triggered=api_count > 0,
        points=min(2, api_count),
        detail=f"{api_count} API patterns matched",
    )
    raw += sig.points
    signals.append(sig)

    many_commits = commit_count > 5
    sig = EscalationSignal(
        name="commit_count",
        triggered=many_commits,
        points=1 if many_commits else 0,
        detail=f"{commit_count} commits",
    )
    raw += sig.points
    signals.append(sig)

    final = max(0, raw + trust_adjustment)
    level = _score_to_level(
        final,
        full_min=gate_full_review_min,
        summary_min=gate_summary_confirm_min,
    )

    return EscalationResult(
        score=final,
        level=level,
        signals=signals,
        trust_adjustment=trust_adjustment,
        raw_score=raw,
    )


def _score_to_level(
    score: int,
    *,
    full_min: int = 5,
    summary_min: int = 3,
) -> EscalationLevel:
    if score >= full_min:
        return EscalationLevel.FULL
    if score >= summary_min:
        return EscalationLevel.LITE
    return EscalationLevel.FAST
