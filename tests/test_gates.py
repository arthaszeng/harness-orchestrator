"""Tests for ship-readiness gate validation (core/gates.py)."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from unittest.mock import patch

from harness.core.gates import (
    CheckStatus,
    GateVerdict,
    check_ship_readiness,
    write_gate_snapshot,
)
from harness.core.workflow_state import (
    GateSnapshot,
    GateStatus,
    WorkflowState,
    load_workflow_state,
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _write_plan(task_dir: Path, content: str = "# Plan\n\n## Deliverables\n- [x] D1\n") -> None:
    (task_dir / "plan.md").write_text(content, encoding="utf-8")


def _write_build(task_dir: Path, *, round_num: int = 1) -> None:
    (task_dir / f"build-r{round_num}.log").write_text("# Build Log\n", encoding="utf-8")


def _write_eval(
    task_dir: Path,
    *,
    round_num: int = 1,
    verdict: str = "PASS",
    content: str | None = None,
) -> Path:
    path = task_dir / f"evaluation-r{round_num}.md"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(
            f"# Code Evaluation — Round {round_num}\n\n## Verdict: {verdict}\n",
            encoding="utf-8",
        )
    return path


def _write_workflow_state(task_dir: Path, **overrides) -> WorkflowState:
    defaults = dict(task_id=task_dir.name, phase="evaluating", iteration=1)
    defaults.update(overrides)
    ws = WorkflowState(**defaults)
    ws.save(task_dir)
    return ws


class TestCheckShipReadinessHappyPath:
    def test_all_pass(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_build(task_dir)
        _write_eval(task_dir, verdict="PASS")
        ws = _write_workflow_state(task_dir)
        ws.gates.evaluation = GateSnapshot(status=GateStatus.PASS, reason="eval passed")
        ws.save(task_dir)

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir, review_gate_mode="eng")

        assert verdict.passed is True
        assert len(verdict.hard_blocked) == 0
        names = [c.name for c in verdict.checks]
        assert "plan_exists" in names
        assert "eval_exists" in names
        assert "eval_verdict_parseable" in names
        assert "eval_ship_eligible" in names


class TestPlanChecks:
    def test_missing_plan_blocks(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_eval(task_dir, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "plan_exists" in blocked_names

    def test_empty_plan_blocks(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        (task_dir / "plan.md").write_text("", encoding="utf-8")
        _write_eval(task_dir, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "plan_exists" in blocked_names

    def test_whitespace_only_plan_blocks(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        (task_dir / "plan.md").write_text("   \n\n  \n", encoding="utf-8")
        _write_eval(task_dir, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "plan_exists" in blocked_names


class TestBuildChecks:
    def test_missing_build_is_warning_not_block(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        assert verdict.passed is True
        warning_names = [c.name for c in verdict.warnings]
        assert "build_exists" in warning_names


class TestEvalChecks:
    def test_missing_eval_blocks(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "eval_exists" in blocked_names

    def test_empty_eval_blocks(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        (task_dir / "evaluation-r1.md").write_text("", encoding="utf-8")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "eval_exists" in blocked_names

    def test_eval_without_verdict_line_blocks(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, content="# Eval\n\nSome findings but no verdict line.\n")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "eval_verdict_parseable" in blocked_names


class TestVerdictEligibility:
    def test_iterate_blocks_in_eng_mode(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="ITERATE")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir, review_gate_mode="eng")

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "eval_ship_eligible" in blocked_names

    def test_iterate_passes_in_advisory_mode(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="ITERATE")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir, review_gate_mode="advisory")

        assert verdict.passed is True
        warning_names = [c.name for c in verdict.warnings]
        assert "eval_ship_eligible" in warning_names

    def test_pass_verdict_passes_in_eng_mode(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir, review_gate_mode="eng")

        assert verdict.passed is True
        check_map = {c.name: c for c in verdict.checks}
        assert check_map["eval_ship_eligible"].status == CheckStatus.PASS


class TestVerdictRegexPrecision:
    def test_pass_prefix_does_not_match(self, tmp_path: Path):
        """Regression: '## Verdict: PASSWORD' must NOT parse as PASS."""
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, content="# Eval\n\n## Verdict: PASSWORD\n")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir, review_gate_mode="eng")

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "eval_verdict_parseable" in blocked_names

    def test_iterate_prefix_does_not_match(self, tmp_path: Path):
        """Regression: '## Verdict: ITERATING' must NOT parse as ITERATE."""
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, content="# Eval\n\n## Verdict: ITERATING\n")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir, review_gate_mode="eng")

        assert verdict.passed is False
        blocked_names = [c.name for c in verdict.hard_blocked]
        assert "eval_verdict_parseable" in blocked_names


class TestMultiEvalSorting:
    def test_picks_highest_round_number(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, round_num=2, verdict="ITERATE")
        _write_eval(task_dir, round_num=10, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir, review_gate_mode="eng")

        assert verdict.passed is True
        check_map = {c.name: c for c in verdict.checks}
        assert check_map["eval_ship_eligible"].status == CheckStatus.PASS

    def test_multiple_verdict_lines_first_match_wins(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        content = "# Eval\n\n## Verdict: PASS\n\nSome text.\n\n## Verdict: ITERATE\n"
        _write_eval(task_dir, content=content)

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir, review_gate_mode="eng")

        assert verdict.passed is True


class TestFreshnessCheck:
    def test_fresh_eval_passes(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        check_map = {c.name: c for c in verdict.checks}
        assert check_map["eval_fresh"].status == CheckStatus.PASS

    def test_stale_eval_is_warning(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        eval_path = _write_eval(task_dir, verdict="PASS")
        old_time = time.time() - 3600
        os.utime(eval_path, (old_time, old_time))

        future = time.time() + 3600
        with patch("harness.core.gates.get_head_commit_epoch", return_value=future):
            verdict = check_ship_readiness(task_dir)

        check_map = {c.name: c for c in verdict.checks}
        assert check_map["eval_fresh"].status == CheckStatus.WARNING
        assert verdict.passed is True

    def test_git_unavailable_warns_freshness(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=None):
            verdict = check_ship_readiness(task_dir)

        check_map = {c.name: c for c in verdict.checks}
        assert check_map["eval_fresh"].status == CheckStatus.WARNING
        assert verdict.passed is True


class TestWorkflowStateGate:
    def test_no_workflow_state_is_warning(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="PASS")

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        check_map = {c.name: c for c in verdict.checks}
        assert check_map["workflow_state_gate"].status == CheckStatus.WARNING
        assert verdict.passed is True

    def test_workflow_state_with_unknown_eval_gate_warns(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="PASS")
        _write_workflow_state(task_dir)

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        check_map = {c.name: c for c in verdict.checks}
        assert check_map["workflow_state_gate"].status == CheckStatus.WARNING

    def test_workflow_state_with_filled_gate_passes(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_plan(task_dir)
        _write_eval(task_dir, verdict="PASS")
        ws = _write_workflow_state(task_dir)
        ws.gates.evaluation = GateSnapshot(status=GateStatus.PASS, reason="passed")
        ws.save(task_dir)

        with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            verdict = check_ship_readiness(task_dir)

        check_map = {c.name: c for c in verdict.checks}
        assert check_map["workflow_state_gate"].status == CheckStatus.PASS


class TestWriteGateSnapshot:
    def test_writes_pass_snapshot(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_workflow_state(task_dir)

        verdict = GateVerdict(passed=True, checks=[], summary="all checks passed")
        result = write_gate_snapshot(task_dir, verdict)

        assert result is True
        ws = load_workflow_state(task_dir)
        assert ws is not None
        assert ws.gates.ship_readiness.status == GateStatus.PASS

    def test_writes_blocked_snapshot(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        _write_workflow_state(task_dir)

        verdict = GateVerdict(passed=False, checks=[], summary="blocked: missing eval")
        result = write_gate_snapshot(task_dir, verdict)

        assert result is True
        ws = load_workflow_state(task_dir)
        assert ws is not None
        assert ws.gates.ship_readiness.status == GateStatus.BLOCKED
        assert "missing eval" in ws.gates.ship_readiness.reason

    def test_skips_when_no_workflow_state(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()

        verdict = GateVerdict(passed=True, checks=[], summary="ok")
        result = write_gate_snapshot(task_dir, verdict)

        assert result is False

    def test_preserves_other_fields(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        ws = _write_workflow_state(task_dir)
        ws.active_plan.title = "Test Plan"
        ws.artifacts.plan = "plan.md"
        ws.save(task_dir)

        verdict = GateVerdict(passed=True, checks=[], summary="ok")
        write_gate_snapshot(task_dir, verdict)

        reloaded = load_workflow_state(task_dir)
        assert reloaded is not None
        assert reloaded.active_plan.title == "Test Plan"
        assert reloaded.artifacts.plan == "plan.md"
        assert reloaded.gates.ship_readiness.status == GateStatus.PASS


class TestPermissionFailGraceful:
    def test_unreadable_plan_blocks_without_crash(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        plan = task_dir / "plan.md"
        plan.write_text("content", encoding="utf-8")
        plan.chmod(0o000)

        try:
            _write_eval(task_dir, verdict="PASS")
            with patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
                verdict = check_ship_readiness(task_dir)
            assert isinstance(verdict, GateVerdict)
        finally:
            plan.chmod(0o644)
