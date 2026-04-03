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
    def test_help_lists_core_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "gate" in result.output
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


class TestGateCommand:
    def test_gate_pass(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Plan\n\n## Deliverables\n", encoding="utf-8")
        (task_dir / "evaluation-r1.md").write_text(
            "# Eval\n\n## Verdict: PASS\n", encoding="utf-8",
        )

        from unittest.mock import patch as mock_patch
        with mock_patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            result = runner.invoke(app, ["gate", "--task", "task-001"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "PASS" in clean

    def test_gate_blocked_missing_eval(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")

        from unittest.mock import patch as mock_patch
        with mock_patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            result = runner.invoke(app, ["gate", "--task", "task-001"])
        assert result.exit_code == 1
        clean = _ANSI_RE.sub("", result.output)
        assert "BLOCKED" in clean

    def test_gate_no_task_dir(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        result = runner.invoke(app, ["gate"])
        assert result.exit_code == 1

    def test_gate_invalid_task_id_exits_with_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        result = runner.invoke(app, ["gate", "--task", "task-999"])
        assert result.exit_code == 1
        clean = _ANSI_RE.sub("", result.output)
        assert "task-999" in clean

    def test_gate_auto_detects_latest_task(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for i in [1, 2]:
            td = tmp_path / ".harness-flow" / "tasks" / f"task-00{i}"
            td.mkdir(parents=True)
            (td / "plan.md").write_text("# Plan\n\n## Deliverables\n", encoding="utf-8")
        (tmp_path / ".harness-flow" / "tasks" / "task-002" / "evaluation-r1.md").write_text(
            "# Eval\n\n## Verdict: PASS\n", encoding="utf-8",
        )

        from unittest.mock import patch as mock_patch
        with mock_patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            result = runner.invoke(app, ["gate"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "task-002" in clean

    def test_gate_invalid_workflow_state_exits_cleanly(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Plan\n\n## Deliverables\n", encoding="utf-8")
        (task_dir / "evaluation-r1.md").write_text(
            "# Eval\n\n## Verdict: PASS\n", encoding="utf-8",
        )
        (task_dir / "workflow-state.json").write_text("{broken", encoding="utf-8")

        from unittest.mock import patch as mock_patch
        with mock_patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            result = runner.invoke(app, ["gate", "--task", "task-001"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 1
        assert "existing workflow-state.json is invalid" in clean


class TestStatusCommand:
    def test_status_reads_canonical_workflow_state(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
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


class TestSaveFeedbackLedgerCommand:
    def test_save_feedback_ledger_writes_file_and_updates_state(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-021"
        task_dir.mkdir(parents=True)
        WorkflowState(task_id="task-021").save(task_dir)

        body = (
            '{"id":"fb-1","task_id":"task-021","source_phase":"eval","source_role":"qa",'
            '"severity":"warn","category":"test","summary":"learning","status":"open",'
            '"decision":"none"}'
        )
        result = runner.invoke(
            app,
            ["save-feedback-ledger", "--task", "task-021", "--body", body],
        )
        assert result.exit_code == 0
        assert (task_dir / "feedback-ledger.jsonl").exists()
        state = WorkflowState.model_validate_json((task_dir / "workflow-state.json").read_text(encoding="utf-8"))
        assert state.artifacts.feedback_ledger == ".harness-flow/tasks/task-021/feedback-ledger.jsonl"

    def test_save_feedback_ledger_rejects_invalid_jsonl(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["save-feedback-ledger", "--task", "task-022", "--body", '{"id":"broken"'],
        )
        assert result.exit_code != 0
