"""Tests for harness workflow next."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.state import TaskState
from harness.core.workflow_state import WorkflowState


def _write_state(task_dir: Path, *, phase: TaskState) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    ws = WorkflowState(task_id=task_dir.name, phase=phase)
    ws.save(task_dir)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestWorkflowNext:
    def test_no_tasks_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow").mkdir()
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "HARNESS_NEXT" in result.output
        assert "task=none" in result.output
        assert "skill=/harness-plan" in result.output
        assert "What happened" in result.output

    def test_missing_workflow_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner):
        monkeypatch.chdir(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task.mkdir(parents=True)
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "task=task-001" in result.output
        assert "phase=unknown" in result.output
        assert "skill=/harness-plan" in result.output
        assert "What happened" in result.output

    def test_corrupt_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner):
        monkeypatch.chdir(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task.mkdir(parents=True)
        (task / "workflow-state.json").write_text("{not json", encoding="utf-8")
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "phase=corrupt" in result.output
        assert "skill=/harness-plan" in result.output
        assert "What happened" in result.output

    def test_phase_contracted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner):
        monkeypatch.chdir(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-001"
        _write_state(task, phase=TaskState.CONTRACTED)
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "phase=contracted" in result.output
        assert "skill=/harness-build" in result.output

    def test_phase_building(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner):
        monkeypatch.chdir(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-001"
        _write_state(task, phase=TaskState.BUILDING)
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "phase=building" in result.output
        assert "skill=/harness-ship" in result.output

    def test_phase_evaluating(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner):
        monkeypatch.chdir(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-001"
        _write_state(task, phase=TaskState.EVALUATING)
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "phase=evaluating" in result.output
        assert "skill=/harness-ship" in result.output

    def test_explicit_task(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner):
        monkeypatch.chdir(tmp_path)
        for name in ("task-001", "task-002"):
            t = tmp_path / ".harness-flow" / "tasks" / name
            _write_state(t, phase=TaskState.CONTRACTED if name == "task-001" else TaskState.BUILDING)
        result = runner.invoke(app, ["workflow", "next", "--task", "task-002"])
        assert result.exit_code == 0
        assert "task=task-002" in result.output
        assert "phase=building" in result.output

    def test_unknown_phase_string(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner):
        monkeypatch.chdir(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task.mkdir(parents=True)
        (task / "workflow-state.json").write_text(
            '{"schema_version": 1, "task_id": "task-001", "phase": "not_a_real_phase"}',
            encoding="utf-8",
        )
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "phase=unknown" in result.output
        assert "What happened" in result.output

    @pytest.mark.parametrize(
        ("phase", "expected_skill"),
        [
            (TaskState.IDLE, "/harness-plan"),
            (TaskState.PLANNING, "/harness-plan"),
            (TaskState.SHIPPING, "/harness-ship"),
            (TaskState.DONE, "/harness-plan"),
            (TaskState.BLOCKED, "/harness-plan"),
        ],
    )
    def test_remaining_phases_map_to_expected_skill(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        phase: TaskState,
        expected_skill: str,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-042"
        _write_state(task, phase=phase)
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "task=task-042" in result.output
        assert f"phase={phase.value}" in result.output
        assert f"skill={expected_skill}" in result.output

    def test_harness_task_id_env_matches_gate_resolution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        for name, phase in (
            ("task-001", TaskState.CONTRACTED),
            ("task-002", TaskState.BUILDING),
        ):
            t = tmp_path / ".harness-flow" / "tasks" / name
            _write_state(t, phase=phase)
        monkeypatch.setenv("HARNESS_TASK_ID", "task-001")
        result = runner.invoke(app, ["workflow", "next"])
        assert result.exit_code == 0
        assert "task=task-001" in result.output
        assert "phase=contracted" in result.output
        assert "skill=/harness-build" in result.output
