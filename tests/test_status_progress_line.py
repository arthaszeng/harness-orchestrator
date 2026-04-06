"""harness status --progress-line (HARNESS_PROGRESS)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.state import TaskState
from harness.core.workflow_state import WorkflowState


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_min_config(project: Path) -> None:
    agents = project / ".harness-flow"
    agents.mkdir(parents=True)
    (agents / "config.toml").write_text(
        '[project]\nname = "t"\nlang = "en"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )


class TestStatusProgressLine:
    def test_prints_line_when_workflow_state_valid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_min_config(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-001"
        WorkflowState(task_id="task-001", phase=TaskState.CONTRACTED).save(task)
        result = runner.invoke(app, ["status", "--progress-line"])
        assert result.exit_code == 0
        out = result.stdout
        assert "HARNESS_PROGRESS step=2/4 phase=build next=" in out
        assert "HARNESS_PROGRESS" in out

    def test_silent_when_no_workflow_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_min_config(tmp_path)
        task = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task.mkdir(parents=True)
        result = runner.invoke(app, ["status", "--progress-line"])
        assert result.exit_code == 0
        assert "HARNESS_PROGRESS" not in result.stdout
