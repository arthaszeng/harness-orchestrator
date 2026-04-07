"""Ship-readiness gate validation for task-level workflow.

Provides structured checks that determine whether a task is ready to ship.
Checks are split into **hard** (block shipping) and **soft** (warning only).
Results are written back to the canonical ``workflow-state.json`` gate snapshot
via a load-merge-save pattern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from harness.core.workflow_state import (
    GateStatus,
    load_workflow_state,
)
from harness.core.score_calibration import ScoreBand, classify_score
from harness.integrations.git_ops import get_head_commit_epoch


class CheckStatus(str, Enum):
    PASS = "pass"
    BLOCKED = "blocked"
    WARNING = "warning"
    SKIPPED = "skipped"


class EvalVerdict(str, Enum):
    """Recognized eval verdict values (case-insensitive on parse)."""
    PASS = "PASS"
    ITERATE = "ITERATE"

    @classmethod
    def parse(cls, value: str) -> "EvalVerdict | None":
        """Parse a verdict string, case-insensitively. Returns None if unknown."""
        try:
            return cls(value.upper())
        except ValueError:
            return None


@dataclass
class CheckItem:
    name: str
    status: CheckStatus
    reason: str = ""


@dataclass
class GateVerdict:
    passed: bool
    checks: list[CheckItem] = field(default_factory=list)
    summary: str = ""
    aggregate_score: float | None = None
    score_band: "ScoreBand | None" = None

    @property
    def hard_blocked(self) -> list[CheckItem]:
        return [c for c in self.checks if c.status == CheckStatus.BLOCKED]

    @property
    def warnings(self) -> list[CheckItem]:
        return [c for c in self.checks if c.status == CheckStatus.WARNING]


def parse_eval_aggregate_score(content: str) -> float | None:
    """Extract the aggregate review score from eval markdown content.

    Supports formats: ``Weighted avg: X.X/10``, ``Weighted Average: X.X/10``,
    ``**Average** | **X.X/10**``.  Returns None when no match is found or the
    parsed value is not finite.
    """
    import math as _math

    m = _AGGREGATE_SCORE_RE.search(content)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except (ValueError, TypeError):
        return None
    if not _math.isfinite(val):
        return None
    return val


_AGGREGATE_SCORE_RE = re.compile(
    r"(?:Weighted\s+avg|Weighted\s+Average|\*\*Average\*\*)\s*[:|]\s*\**(\d+(?:\.\d+)?)\**\s*/\s*10",
    re.IGNORECASE,
)

_CODE_EVAL_ROUND_RE = re.compile(r"code-eval-r(\d+)\.md$")
_LEGACY_EVAL_ROUND_RE = re.compile(r"evaluation-r(\d+)\.md$")
_BUILD_ROUND_RE = re.compile(r"build-r(\d+)\.md$")
_LEGACY_BUILD_ROUND_RE = re.compile(r"build-r(\d+)\.log$")
_VERDICT_LINE_RE = re.compile(r"^##\s+Verdict:\s+(\S+)\s*$", re.MULTILINE | re.IGNORECASE)


def _latest_numbered_file_from_patterns(task_dir: Path, patterns: tuple[re.Pattern[str], ...]) -> Path | None:
    """Return the file with the highest numeric round across patterns, or None."""
    best: tuple[int, Path] | None = None
    try:
        entries = list(task_dir.iterdir())
    except OSError:
        return None
    for p in entries:
        for pattern in patterns:
            m = pattern.search(p.name)
            if not m:
                continue
            num = int(m.group(1))
            if best is None or num > best[0]:
                best = (num, p)
            break
    return best[1] if best else None


def _file_exists_and_nonempty(path: Path) -> bool:
    resolved = path.resolve()
    if not resolved.exists():
        return False
    try:
        size = resolved.stat().st_size
        if size == 0:
            return False
        with open(resolved, "r", encoding="utf-8") as f:
            head = f.read(64)
        return bool(head.strip())
    except (OSError, UnicodeDecodeError):
        return False


def check_ship_readiness(
    task_dir: Path,
    *,
    review_gate_mode: str = "eng",
) -> GateVerdict:
    """Run all ship-readiness checks against *task_dir*.

    Returns a :class:`GateVerdict` with per-item results.
    """
    checks: list[CheckItem] = []

    # --- Hard checks ---

    plan_path = task_dir / "plan.md"
    if _file_exists_and_nonempty(plan_path):
        checks.append(CheckItem("plan_exists", CheckStatus.PASS))
    else:
        checks.append(CheckItem(
            "plan_exists", CheckStatus.BLOCKED,
            "plan.md is missing or empty",
        ))

    latest_eval = _latest_numbered_file_from_patterns(
        task_dir,
        (_CODE_EVAL_ROUND_RE, _LEGACY_EVAL_ROUND_RE),
    )
    if latest_eval and _file_exists_and_nonempty(latest_eval):
        checks.append(CheckItem("eval_exists", CheckStatus.PASS))
    else:
        checks.append(CheckItem(
            "eval_exists", CheckStatus.BLOCKED,
            "no non-empty code-eval-rN.md found",
        ))

    verdict_value: str | None = None
    eval_content: str = ""
    if latest_eval and latest_eval.exists():
        try:
            eval_content = latest_eval.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            eval_content = ""
        content = eval_content
        m = _VERDICT_LINE_RE.search(content)
        if m:
            parsed = EvalVerdict.parse(m.group(1))
            if parsed is not None:
                verdict_value = parsed.value
                checks.append(CheckItem("eval_verdict_parseable", CheckStatus.PASS))
            else:
                checks.append(CheckItem(
                    "eval_verdict_parseable", CheckStatus.BLOCKED,
                    f"unknown verdict '{m.group(1)}' — expected PASS or ITERATE",
                ))
        else:
            checks.append(CheckItem(
                "eval_verdict_parseable", CheckStatus.BLOCKED,
                "latest eval does not contain a '## Verdict: PASS|ITERATE' line",
            ))
    else:
        checks.append(CheckItem(
            "eval_verdict_parseable", CheckStatus.SKIPPED,
            "no eval file to parse",
        ))

    if verdict_value is not None:
        if verdict_value == "PASS":
            checks.append(CheckItem("eval_ship_eligible", CheckStatus.PASS))
        elif review_gate_mode == "advisory":
            checks.append(CheckItem(
                "eval_ship_eligible", CheckStatus.WARNING,
                "eval verdict is ITERATE (advisory mode — warning only)",
            ))
        else:
            checks.append(CheckItem(
                "eval_ship_eligible", CheckStatus.BLOCKED,
                "eval verdict is ITERATE — complete the fix loop and re-evaluate",
            ))
    else:
        checks.append(CheckItem(
            "eval_ship_eligible", CheckStatus.SKIPPED,
            "no verdict parsed",
        ))

    # --- Soft checks ---

    latest_build = _latest_numbered_file_from_patterns(
        task_dir,
        (_BUILD_ROUND_RE, _LEGACY_BUILD_ROUND_RE),
    )
    if latest_build and latest_build.exists():
        checks.append(CheckItem("build_exists", CheckStatus.PASS))
    else:
        checks.append(CheckItem(
            "build_exists", CheckStatus.WARNING,
            "no build-rN.md found (may be expected for hotfixes)",
        ))

    if latest_eval and latest_eval.exists():
        try:
            eval_mtime = latest_eval.stat().st_mtime
        except OSError:
            eval_mtime = None

        head_epoch = get_head_commit_epoch(task_dir)
        if eval_mtime is not None and head_epoch is not None:
            if eval_mtime >= head_epoch:
                checks.append(CheckItem("eval_fresh", CheckStatus.PASS))
            else:
                checks.append(CheckItem(
                    "eval_fresh", CheckStatus.WARNING,
                    "eval file is older than the latest commit — consider re-evaluating",
                ))
        else:
            checks.append(CheckItem(
                "eval_fresh", CheckStatus.WARNING,
                "could not determine freshness (git unavailable or file error)",
            ))
    else:
        checks.append(CheckItem(
            "eval_fresh", CheckStatus.SKIPPED,
            "no eval file",
        ))

    ws = load_workflow_state(task_dir)
    if ws is not None:
        eval_gate = ws.gates.evaluation
        if eval_gate.status != GateStatus.UNKNOWN:
            checks.append(CheckItem("workflow_state_gate", CheckStatus.PASS))
        else:
            checks.append(CheckItem(
                "workflow_state_gate", CheckStatus.WARNING,
                "workflow-state evaluation gate is UNKNOWN — has eval updated the state?",
            ))
    else:
        checks.append(CheckItem(
            "workflow_state_gate", CheckStatus.WARNING,
            "no workflow-state.json found (legacy task — checks based on files only)",
        ))

    blocked = [c for c in checks if c.status == CheckStatus.BLOCKED]
    passed = len(blocked) == 0
    if passed:
        summary = "all hard checks passed"
    else:
        reasons = "; ".join(c.reason for c in blocked if c.reason)
        summary = f"blocked: {reasons}"

    agg_score = parse_eval_aggregate_score(eval_content) if eval_content else None
    band = classify_score(agg_score) if agg_score is not None else None

    return GateVerdict(
        passed=passed,
        checks=checks,
        summary=summary,
        aggregate_score=agg_score,
        score_band=band,
    )


def write_gate_snapshot(task_dir: Path, verdict: GateVerdict) -> bool:
    """Write the gate verdict back to workflow-state.json via sync helper.

    Returns True if the snapshot was written, False if skipped (no state file).
    """
    state_path = task_dir / "workflow-state.json"
    if not state_path.exists():
        return False

    from datetime import datetime, timezone
    from harness.core.workflow_state import sync_task_state

    status = GateStatus.PASS if verdict.passed else GateStatus.BLOCKED
    sync_task_state(
        task_dir,
        gate_updates={
            "ship_readiness": {
                "status": status.value,
                "reason": verdict.summary,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        },
    )
    return True
