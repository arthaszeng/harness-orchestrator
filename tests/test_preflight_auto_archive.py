"""Integration tests for preflight auto-archive of done tasks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.core.config import HarnessConfig


def _bootstrap(tmp_path: Path, *, auto_archive: bool = True, phase: str = "done") -> tuple[Path, HarnessConfig]:
    """Create a minimal project layout and return (project_root, config)."""
    root = tmp_path / "project"
    agents = root / ".harness-flow"
    (agents / "tasks").mkdir(parents=True)
    (agents / "archive").mkdir(parents=True)

    config_toml = f"""\
[project]
name = "test"

[workflow]
auto_archive = {'true' if auto_archive else 'false'}
"""
    (agents / "config.toml").write_text(config_toml, encoding="utf-8")

    if phase:
        td = agents / "tasks" / "task-042"
        td.mkdir()
        ws = {"schema_version": 1, "task_id": "task-042", "phase": phase, "iteration": 0}
        (td / "workflow-state.json").write_text(json.dumps(ws), encoding="utf-8")
        (td / "plan.md").write_text("# plan", encoding="utf-8")

    cfg = HarnessConfig.load(root)
    return root, cfg


def _make_manager(root: Path, cfg: HarnessConfig) -> BranchLifecycleManager:
    from harness.core.task_identity import TaskIdentityResolver

    return BranchLifecycleManager(project_root=root, config=cfg, resolver=TaskIdentityResolver.from_config(cfg))


def _mock_git(branch: str = "agent/task-042-feature"):
    """Patch git operations to simulate being on *branch* with clean worktree."""

    def _clean(root: Path):
        from harness.integrations.git_ops import GitOperationResult
        return GitOperationResult(ok=True, code="OK", message="clean")

    def _branch(root: Path):
        return branch

    return (
        patch("harness.core.branch_lifecycle.ensure_clean_result", side_effect=_clean),
        patch("harness.core.branch_lifecycle.current_branch", side_effect=_branch),
    )


class TestPreflightAutoArchive:
    def test_auto_archive_done_task(self, tmp_path: Path) -> None:
        root, cfg = _bootstrap(tmp_path, auto_archive=True, phase="done")
        mgr = _make_manager(root, cfg)
        p1, p2 = _mock_git("agent/task-042-feature")
        with p1, p2:
            result = mgr.preflight_repo_state()
        assert result.ok
        assert result.context.get("auto_archived") == "task-042"
        assert not (root / ".harness-flow" / "tasks" / "task-042").exists()
        assert (root / ".harness-flow" / "archive" / "task-042" / "plan.md").exists()

    def test_config_disabled(self, tmp_path: Path) -> None:
        root, cfg = _bootstrap(tmp_path, auto_archive=False, phase="done")
        mgr = _make_manager(root, cfg)
        p1, p2 = _mock_git("agent/task-042-feature")
        with p1, p2:
            result = mgr.preflight_repo_state()
        assert result.ok
        assert "auto_archived" not in result.context
        assert (root / ".harness-flow" / "tasks" / "task-042").exists()

    def test_on_main_no_task_key(self, tmp_path: Path) -> None:
        root, cfg = _bootstrap(tmp_path, auto_archive=True, phase="done")
        mgr = _make_manager(root, cfg)
        p1, p2 = _mock_git("main")
        with p1, p2:
            result = mgr.preflight_repo_state()
        assert result.ok
        assert "auto_archived" not in result.context
        assert (root / ".harness-flow" / "tasks" / "task-042").exists()

    def test_task_not_done_skipped(self, tmp_path: Path) -> None:
        root, cfg = _bootstrap(tmp_path, auto_archive=True, phase="shipping")
        mgr = _make_manager(root, cfg)
        p1, p2 = _mock_git("agent/task-042-feature")
        with p1, p2:
            result = mgr.preflight_repo_state()
        assert result.ok
        assert "auto_archived" not in result.context
        assert (root / ".harness-flow" / "tasks" / "task-042").exists()

    def test_task_dir_missing_skipped(self, tmp_path: Path) -> None:
        root, cfg = _bootstrap(tmp_path, auto_archive=True, phase="")
        mgr = _make_manager(root, cfg)
        p1, p2 = _mock_git("agent/task-099-nonexistent")
        with p1, p2:
            result = mgr.preflight_repo_state()
        assert result.ok
        assert "auto_archived" not in result.context

    def test_corrupt_workflow_state_degrades(self, tmp_path: Path) -> None:
        root, cfg = _bootstrap(tmp_path, auto_archive=True, phase="")
        td = root / ".harness-flow" / "tasks" / "task-042"
        td.mkdir(parents=True, exist_ok=True)
        (td / "workflow-state.json").write_text("NOT JSON", encoding="utf-8")

        mgr = _make_manager(root, cfg)
        p1, p2 = _mock_git("agent/task-042-feature")
        with p1, p2:
            result = mgr.preflight_repo_state()
        assert result.ok
        assert "auto_archived" not in result.context

    def test_archive_target_exists_degrades(self, tmp_path: Path) -> None:
        root, cfg = _bootstrap(tmp_path, auto_archive=True, phase="done")
        (root / ".harness-flow" / "archive" / "task-042").mkdir(parents=True)

        mgr = _make_manager(root, cfg)
        p1, p2 = _mock_git("agent/task-042-feature")
        with p1, p2:
            result = mgr.preflight_repo_state()
        assert result.ok
        assert "auto_archived" not in result.context

    def test_idempotent_already_archived(self, tmp_path: Path) -> None:
        """Re-running preflight after archive does not fail."""
        root, cfg = _bootstrap(tmp_path, auto_archive=True, phase="done")
        mgr = _make_manager(root, cfg)
        p1, p2 = _mock_git("agent/task-042-feature")
        with p1, p2:
            r1 = mgr.preflight_repo_state()
        assert r1.ok and r1.context.get("auto_archived") == "task-042"

        with p1, p2:
            r2 = mgr.preflight_repo_state()
        assert r2.ok
        assert "auto_archived" not in r2.context
