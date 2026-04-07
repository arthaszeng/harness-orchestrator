"""Tests for harness worktree CLI sub-commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from harness.cli import app
from harness.core.worktree_lifecycle import (
    WorktreeCreateResult,
    WorktreeEntry,
    WorktreeRemoveResult,
)

runner = CliRunner()


def _make_config(tmp_path: Path) -> None:
    hf = tmp_path / ".harness-flow"
    hf.mkdir(parents=True, exist_ok=True)
    (hf / "config.toml").write_text(
        "[project]\nname = 'test-proj'\nlang = 'en'\n\n"
        "[workflow]\nbranch_prefix = 'agent'\ntrunk_branch = 'main'\n\n"
        "[ci]\ncommand = 'echo ok'\n",
        encoding="utf-8",
    )


class TestWorktreeCreate:
    def test_create_success(self, tmp_path: Path):
        _make_config(tmp_path)

        mock_result = WorktreeCreateResult(
            ok=True,
            path=str(tmp_path / "wt"),
            branch="agent/task-034-feat",
            task_key="task-034",
            message="created",
        )

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.create_worktree",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["worktree", "create", "task-034", "--desc", "feat"])

        assert result.exit_code == 0
        assert "task-034" in result.output or "created" in result.output.lower()

    def test_create_failure(self, tmp_path: Path):
        _make_config(tmp_path)

        mock_result = WorktreeCreateResult(ok=False, message="path exists")

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.create_worktree",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["worktree", "create", "task-034"])

        assert result.exit_code == 1

    def test_create_json_output(self, tmp_path: Path):
        _make_config(tmp_path)

        mock_result = WorktreeCreateResult(
            ok=True,
            path="/some/path",
            branch="agent/task-034",
            task_key="task-034",
            message="created",
        )

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.create_worktree",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["worktree", "create", "task-034", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["task_key"] == "task-034"


class TestWorktreeList:
    def test_list_empty(self, tmp_path: Path):
        _make_config(tmp_path)

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.list_worktrees",
                return_value=[],
            ),
        ):
            result = runner.invoke(app, ["worktree", "list"])

        assert result.exit_code == 0
        assert "no worktrees" in result.output.lower()

    def test_list_with_entries(self, tmp_path: Path):
        _make_config(tmp_path)

        entries = [
            WorktreeEntry(
                task_key="task-034",
                branch="agent/task-034",
                path="/some/path",
                created_at="2026-01-01T00:00:00Z",
                status="active",
            ),
        ]

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.list_worktrees",
                return_value=entries,
            ),
        ):
            result = runner.invoke(app, ["worktree", "list"])

        assert result.exit_code == 0
        assert "task-034" in result.output

    def test_list_json(self, tmp_path: Path):
        _make_config(tmp_path)

        entries = [
            WorktreeEntry(
                task_key="task-034",
                branch="agent/task-034",
                path="/some/path",
                created_at="2026-01-01T00:00:00Z",
                status="active",
            ),
        ]

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.list_worktrees",
                return_value=entries,
            ),
        ):
            result = runner.invoke(app, ["worktree", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["task_key"] == "task-034"
        assert data[0]["status"] == "active"


class TestWorktreeRemove:
    def test_remove_success(self, tmp_path: Path):
        _make_config(tmp_path)

        mock_result = WorktreeRemoveResult(ok=True, message="removed")

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.remove_worktree",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["worktree", "remove", "task-034"])

        assert result.exit_code == 0

    def test_remove_failure(self, tmp_path: Path):
        _make_config(tmp_path)

        mock_result = WorktreeRemoveResult(ok=False, message="not found")

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.remove_worktree",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["worktree", "remove", "task-999"])

        assert result.exit_code == 1

    def test_remove_json_output(self, tmp_path: Path):
        _make_config(tmp_path)

        mock_result = WorktreeRemoveResult(ok=True, message="removed", branch_pruned=True)

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.remove_worktree",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["worktree", "remove", "task-034", "--prune-branch", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["branch_pruned"] is True

    def test_remove_with_force_flag(self, tmp_path: Path):
        _make_config(tmp_path)

        mock_result = WorktreeRemoveResult(ok=True, message="force removed")

        with (
            patch("harness.commands.worktree._resolve_project_root", return_value=tmp_path),
            patch(
                "harness.core.worktree_lifecycle.WorktreeLifecycleManager.remove_worktree",
                return_value=mock_result,
            ) as mock_remove,
        ):
            result = runner.invoke(app, ["worktree", "remove", "task-034", "--force"])

        assert result.exit_code == 0
        mock_remove.assert_called_once_with("task-034", prune_branch=False, force=True)


class TestWorktreeHelp:
    def test_help_available(self):
        result = runner.invoke(app, ["worktree", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output.lower()
        assert "list" in result.output.lower()
        assert "remove" in result.output.lower()

    def test_parent_help_shows_worktree(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "worktree" in result.output.lower()
