"""Tests for barrier integration in gates.py — check_ship_readiness."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.barriers import BarrierStatus, complete_barrier, register_barrier
from harness.core.gates import CheckStatus, _check_barrier_readiness

runner = CliRunner()


@pytest.fixture
def task_dir(tmp_path):
    d = tmp_path / "task-099"
    d.mkdir()
    (d / "plan.md").write_text("# Spec\n## Verdict: PASS")
    return d


class TestBarrierGateIntegration:
    def test_no_barriers_dir_returns_none(self, task_dir):
        result = _check_barrier_readiness(task_dir)
        assert result is None

    def test_empty_barriers_dir_returns_none(self, task_dir):
        (task_dir / "barriers").mkdir()
        result = _check_barrier_readiness(task_dir)
        assert result is None

    def test_all_required_done_passes(self, task_dir):
        register_barrier(task_dir, barrier_id="a", phase="ship", required=True)
        complete_barrier(task_dir, barrier_id="a", status=BarrierStatus.DONE)
        result = _check_barrier_readiness(task_dir)
        assert result is not None
        assert result.status == CheckStatus.PASS

    def test_required_not_done_blocks(self, task_dir):
        register_barrier(task_dir, barrier_id="a", phase="ship", required=True)
        result = _check_barrier_readiness(task_dir)
        assert result is not None
        assert result.status == CheckStatus.BLOCKED
        assert "a" in result.reason

    def test_non_required_not_counted(self, task_dir):
        register_barrier(task_dir, barrier_id="optional", phase="ship", required=False)
        result = _check_barrier_readiness(task_dir)
        assert result is None

    def test_required_failed_blocks(self, task_dir):
        """Test matrix scenario 3: required barrier has failed → gate FAIL."""
        register_barrier(task_dir, barrier_id="ci-run", phase="ship", required=True)
        complete_barrier(task_dir, barrier_id="ci-run", status=BarrierStatus.FAILED)
        result = _check_barrier_readiness(task_dir)
        assert result is not None
        assert result.status == CheckStatus.BLOCKED

    def test_corrupted_json_blocks(self, task_dir):
        """Test matrix scenario 5: corrupted JSON → gate returns BLOCKED (fail-closed)."""
        barriers_dir = task_dir / "barriers"
        barriers_dir.mkdir(exist_ok=True)
        (barriers_dir / "bad.json").write_text("NOT VALID JSON {{{")
        register_barrier(task_dir, barrier_id="good", phase="ship", required=True)
        complete_barrier(task_dir, barrier_id="good", status=BarrierStatus.DONE)
        result = _check_barrier_readiness(task_dir)
        assert result is not None
        assert result.status == CheckStatus.BLOCKED


class TestBarrierCLIUnknownTask:
    """Test matrix scenario 6: unknown task dir → exit 1 + error JSON."""

    def test_register_unknown_task(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow").mkdir()
        result = runner.invoke(app, [
            "barrier", "register",
            "--task", "task-nonexistent",
            "--id", "test",
            "--phase", "ship",
        ])
        assert result.exit_code == 1
        import json
        err_data = json.loads(result.output)
        assert "error" in err_data

    def test_check_unknown_task(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow").mkdir()
        result = runner.invoke(app, [
            "barrier", "check",
            "--task", "task-nonexistent",
            "--json",
        ])
        assert result.exit_code == 1
        import json
        err_data = json.loads(result.output)
        assert "error" in err_data
