"""CLI-layer tests for D4 composite commands: ship-prepare, preflight-bundle, plan-completion-audit."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from harness.cli import app

runner = CliRunner()


class TestShipPrepare:
    def test_no_task_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        result = runner.invoke(app, ["ship-prepare", "--json"])
        assert result.exit_code == 1

    def test_json_output_schema(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Spec\n# Contract\n")
        (task_dir / "workflow-state.json").write_text(
            json.dumps({"task_id": "task-001", "phase": "shipping"})
        )
        mock_result = type("R", (), {"returncode": 0, "stdout": "file1.py\nfile2.py\n", "stderr": ""})()
        stat_result = type("R", (), {"returncode": 0, "stdout": " 2 files changed, 10 insertions(+), 5 deletions(-)\n", "stderr": ""})()
        log_result = type("R", (), {"returncode": 0, "stdout": "3\n", "stderr": ""})()

        def mock_run(cmd, *a, **kw):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "--name-only" in cmd_str:
                return mock_result
            if "--shortstat" in cmd_str:
                return stat_result
            if "rev-list" in cmd_str:
                return log_result
            return mock_result

        with patch("harness.integrations.git_ops.run_git", side_effect=mock_run):
            result = runner.invoke(app, ["ship-prepare", "--task", "task-001", "--json"])
        assert result.exit_code == 0, f"ship-prepare failed: {result.stdout}"
        data = json.loads(result.stdout)
        assert "diff_stat" in data
        assert "escalation" in data
        assert "review_dispatch" in data


class TestPreflightBundle:
    def test_no_task_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow").mkdir()
        result = runner.invoke(app, ["preflight-bundle", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["ok"] is False

    def test_with_task_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Spec")
        (task_dir / "workflow-state.json").write_text(
            json.dumps({"task_id": "task-001", "phase": "building"})
        )
        (tmp_path / ".harness-flow" / "config.toml").write_text(
            '[project]\nname = "t"\n\n[ci]\ncommand = "pytest"\n\n[workflow]\ntrunk_branch = "main"\n'
        )
        result = runner.invoke(app, ["preflight-bundle", "--task", "task-001", "--phase", "build", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert "task_dir" in data
        assert "context_budget_ok" in data
        assert "file_count_ok" in data

    def test_budget_exceeded_is_warning_not_error(self, tmp_path, monkeypatch):
        """Token budget exceeded should produce a warning but ok remains True."""
        monkeypatch.chdir(tmp_path)
        harness = tmp_path / ".harness-flow"
        harness.mkdir()
        (harness / "config.toml").write_text(
            '[project]\nname = "t"\n\n[ci]\ncommand = "pytest"\n\n'
            "[workflow]\ntrunk_branch = \"main\"\ncontext_budget_tokens = 1000\n"
        )
        task_dir = harness / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("x" * 200_000)
        result = runner.invoke(app, ["preflight-bundle", "--task", "task-001", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["context_budget_ok"] is False
        assert data["ok"] is True
        assert any("context budget" in w for w in data.get("warnings", []))

    def test_file_count_exceeded_is_hard_error(self, tmp_path, monkeypatch):
        """50+ files in task dir should fail preflight."""
        monkeypatch.chdir(tmp_path)
        harness = tmp_path / ".harness-flow"
        harness.mkdir()
        (harness / "config.toml").write_text(
            '[project]\nname = "t"\n\n[ci]\ncommand = "pytest"\n\n[workflow]\ntrunk_branch = "main"\n'
        )
        task_dir = harness / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        for i in range(55):
            (task_dir / f"artifact-{i:03d}.txt").write_text("x")
        result = runner.invoke(app, ["preflight-bundle", "--task", "task-001", "--json"])
        data = json.loads(result.stdout)
        assert data["file_count_ok"] is False
        assert data["ok"] is False


class TestPlanCompletionAudit:
    def test_no_task_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow").mkdir()
        result = runner.invoke(app, ["plan-completion-audit", "--json"])
        assert result.exit_code == 1

    def test_no_plan(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "workflow-state.json").write_text(
            json.dumps({"task_id": "task-001", "phase": "building"})
        )
        result = runner.invoke(app, ["plan-completion-audit", "--task", "task-001", "--json"])
        assert result.exit_code == 1

    def test_with_plan_and_mock_diff(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text(
            "# Spec\n# Contract\n## Deliverables\n"
            "- [x] **D1: Create `src/foo.py`**\n"
            "- [ ] **D2: Create `src/bar.py`**\n"
        )
        (task_dir / "workflow-state.json").write_text(
            json.dumps({"task_id": "task-001", "phase": "building"})
        )
        mock_result = type("R", (), {"returncode": 0, "stdout": "src/foo.py\n", "stderr": ""})()
        with patch("harness.integrations.git_ops.run_git", return_value=mock_result):
            result = runner.invoke(app, ["plan-completion-audit", "--task", "task-001", "--json"])
        assert result.exit_code == 0, f"plan-audit failed: {result.stdout}"
        data = json.loads(result.stdout)
        assert "deliverables" in data
