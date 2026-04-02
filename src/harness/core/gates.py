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
from typing import List

from harness.core.workflow_state import (
    GateSnapshot,
    GateStatus,
    load_workflow_state,
)
from harness.integrations.git_ops import get_head_commit_epoch


class CheckStatus(str, Enum):
    PASS = "pass"
    BLOCKED = "blocked"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class CheckItem:
    name: str
    status: CheckStatus
    reason: str = ""


@dataclass
class GateVerdict:
    passed: bool
    checks: List[CheckItem] = field(default_factory=list)
    summary: str = ""

    @property
    def hard_blocked(self) -> list[CheckItem]:
        return [c for c in self.checks if c.status == CheckStatus.BLOCKED]

    @property
    def warnings(self) -> list[CheckItem]:
        return [c for c in self.checks if c.status == CheckStatus.WARNING]


_EVAL_ROUND_RE = re.compile(r"evaluation-r(\d+)\.md$")
_BUILD_ROUND_RE = re.compile(r"build-r(\d+)\.log$")
_VERDICT_LINE_RE = re.compile(r"^##\s+Verdict:\s+(PASS|ITERATE)\s*$", re.MULTILINE)


def _latest_numbered_file(task_dir: Path, pattern: re.Pattern[str]) -> Path | None:
    """Return the file with the highest numeric round, or None."""
    best: tuple[int, Path] | None = None
    try:
        entries = list(task_dir.iterdir())
    except OSError:
        return None
    for p in entries:
        m = pattern.search(p.name)
        if m:
            num = int(m.group(1))
            if best is None or num > best[0]:
                best = (num, p)
    return best[1] if best else None


def _file_exists_and_nonempty(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return path.stat().st_size > 0 and bool(path.read_text(encoding="utf-8").strip())
    except OSError:
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

    latest_eval = _latest_numbered_file(task_dir, _EVAL_ROUND_RE)
    if latest_eval and _file_exists_and_nonempty(latest_eval):
        checks.append(CheckItem("eval_exists", CheckStatus.PASS))
    else:
        checks.append(CheckItem(
            "eval_exists", CheckStatus.BLOCKED,
            "no non-empty evaluation-rN.md found",
        ))

    verdict_value: str | None = None
    if latest_eval and latest_eval.exists():
        try:
            content = latest_eval.read_text(encoding="utf-8")
        except OSError:
            content = ""
        m = _VERDICT_LINE_RE.search(content)
        if m:
            verdict_value = m.group(1)
            checks.append(CheckItem("eval_verdict_parseable", CheckStatus.PASS))
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

    latest_build = _latest_numbered_file(task_dir, _BUILD_ROUND_RE)
    if latest_build and latest_build.exists():
        checks.append(CheckItem("build_exists", CheckStatus.PASS))
    else:
        checks.append(CheckItem(
            "build_exists", CheckStatus.WARNING,
            "no build-rN.log found (may be expected for hotfixes)",
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

    return GateVerdict(passed=passed, checks=checks, summary=summary)


def write_gate_snapshot(task_dir: Path, verdict: GateVerdict) -> bool:
    """Write the gate verdict back to workflow-state.json (load-merge-save).

    Returns True if the snapshot was written, False if skipped (no state file).
    """
    ws = load_workflow_state(task_dir)
    if ws is None:
        return False

    from datetime import datetime, timezone

    status = GateStatus.PASS if verdict.passed else GateStatus.BLOCKED
    ws.gates.ship_readiness = GateSnapshot(
        status=status,
        reason=verdict.summary,
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    ws.save(task_dir)
    return True
