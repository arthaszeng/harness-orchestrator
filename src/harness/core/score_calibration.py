"""Scoring calibration helpers for review signal quality.

These helpers are deterministic and test-friendly. They do not change gate
threshold semantics directly; instead they provide stable math utilities that
templates/workflows can reference when calibrating score behavior.
"""

from __future__ import annotations

import math
import re
import statistics
from enum import Enum
from typing import Iterable

SHIP_THRESHOLD: float = 8.0
ITERATE_THRESHOLD: float = 6.0


class ScoreBand(str, Enum):
    """Advisory score band — maps aggregate review score to decision guidance.

    Not a hard gate; coexists with EvalVerdict (PASS/ITERATE) as supplementary
    signal for human decision-makers.
    """

    SHIP = "ship"
    ITERATE = "iterate"
    REDO = "redo"


def classify_score(score: float) -> ScoreBand | None:
    """Classify a review aggregate score into an advisory band.

    Intervals (half-open): [8.0, 10.0] → SHIP, [6.0, 8.0) → ITERATE, [0.0, 6.0) → REDO.
    Returns None for non-finite inputs (NaN, inf, -inf).
    Finite values are clamped to [0, 10] before classification.
    """
    try:
        val = float(score)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    val = max(0.0, min(10.0, val))
    if val >= SHIP_THRESHOLD:
        return ScoreBand.SHIP
    if val >= ITERATE_THRESHOLD:
        return ScoreBand.ITERATE
    return ScoreBand.REDO

_TAG_RE = re.compile(r"\[[A-Z0-9_\- ]+\]")
_SPACE_RE = re.compile(r"\s+")


def normalize_finding_signature(text: str) -> str:
    """Normalize a finding sentence into a comparable signature."""
    value = _TAG_RE.sub(" ", text.upper())
    value = re.sub(r"[^A-Z0-9 ]+", " ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    return value


def _flatten_signatures(groups: Iterable[Iterable[str]]) -> list[str]:
    signatures: list[str] = []
    for group in groups:
        for item in group:
            sig = normalize_finding_signature(item)
            if sig:
                signatures.append(sig)
    return signatures


def apply_repeat_penalty(
    *,
    base_score: float,
    current_findings: list[str],
    prior_round_findings: list[list[str]] | None = None,
) -> float:
    """Apply deterministic score penalties for repeated findings.

    Rules:
    - Each repeated finding signature deducts 0.30 (cap 1.50 total)
    - A repeated finding containing HIGH CONFIDENCE deducts extra 0.50
    - Score is clamped to [0.0, 10.0]
    """
    prior_round_findings = prior_round_findings or []
    prior = set(_flatten_signatures(prior_round_findings))
    if not prior:
        return max(0.0, min(10.0, float(base_score)))

    penalty = 0.0
    seen: set[str] = set()
    for finding in current_findings:
        sig = normalize_finding_signature(finding)
        if not sig or sig in seen:
            continue
        seen.add(sig)
        if sig in prior:
            penalty += 0.30
            if "HIGH CONFIDENCE" in finding.upper():
                penalty += 0.50
    penalty = min(1.50, penalty)
    value = float(base_score) - penalty
    return max(0.0, min(10.0, value))


def score_dispersion(values: list[float]) -> float:
    """Return IQR-like dispersion for score distribution."""
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) < 4:
        return max(ordered) - min(ordered)
    q1 = statistics.quantiles(ordered, n=4, method="inclusive")[0]
    q3 = statistics.quantiles(ordered, n=4, method="inclusive")[2]
    return max(0.0, q3 - q1)


def dispersion_improvement_pct(*, baseline: list[float], current: list[float]) -> float:
    """Compute percentage improvement from baseline dispersion to current."""
    base = score_dispersion(baseline)
    now = score_dispersion(current)
    if base <= 0:
        return 0.0
    return ((now - base) / base) * 100.0
