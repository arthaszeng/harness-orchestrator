"""Tests for harness CLI entry point."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.state import TaskState
from harness.core.workflow_state import WorkflowState

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

runner = CliRunner()


class TestVersionOutput:
    def test_version_flag_contains_harness_flow(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "harness-flow" in result.output
        assert "harness-orchestrator" not in result.output

    def test_version_flag_short(self):
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "harness-flow" in result.output
        assert "harness-orchestrator" not in result.output


class TestHelpOutput:
    def test_help_lists_three_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "status" in result.output
        assert "update" in result.output

    def test_help_does_not_list_install(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        lines = result.output.lower().splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("install") and "completion" not in stripped:
                pytest.fail(f"'install' command found in help: {line}")

    def test_init_help_has_force_option(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        clean = _ANSI_RE.sub("", result.output)
        assert "--force" in clean


class TestStatusCommand:
    def test_status_reads_canonical_workflow_state(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".agents" / "tasks" / "task-001"
        workflow_state = WorkflowState(
            task_id="task-001",
            phase=TaskState.EVALUATING,
            iteration=2,
            branch="agent/task-001-workflow-intelligence",
        )
        workflow_state.active_plan.title = "Canonical Workflow State Artifact"
        workflow_state.blocker.reason = "awaiting ship readiness"
        workflow_state.save(task_dir)

        result = runner.invoke(app, ["status"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "task-001" in clean
        assert "evaluating" in clean
        assert "Canonical Workflow State Artifact" in clean
        assert "awaiting ship readiness" in clean
