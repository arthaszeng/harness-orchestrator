"""Tests for harness.core.worktree_lifecycle — worktree lifecycle management."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.core.worktree_lifecycle import (
    REGISTRY_VERSION,
    WorktreeLifecycleManager,
)
from harness.integrations.git_ops import GitOperationResult


def _make_config(tmp_path: Path) -> None:
    hf = tmp_path / ".harness-flow"
    hf.mkdir(parents=True, exist_ok=True)
    (hf / "config.toml").write_text(
        "[project]\nname = 'test-proj'\nlang = 'en'\n\n"
        "[workflow]\nbranch_prefix = 'agent'\ntrunk_branch = 'main'\n\n"
        "[ci]\ncommand = 'echo ok'\n",
        encoding="utf-8",
    )


def _ok_result(**kw) -> GitOperationResult:
    return GitOperationResult(ok=True, code="OK", message="ok", **kw)


def _fail_result(code: str = "FAIL", msg: str = "failed") -> GitOperationResult:
    return GitOperationResult(ok=False, code=code, message=msg)


class TestCreateWorktree:
    def test_create_happy_path(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        wt_expected = tmp_path.parent / f"{tmp_path.name}-wt-task-034"

        with patch(
            "harness.core.worktree_lifecycle.run_git_result"
        ) as mock_git:
            mock_git.return_value = _ok_result()

            with patch.object(mgr, "_copy_artifacts"):
                result = mgr.create_worktree("task-034", short_desc="new feature")

        assert result.ok
        assert result.task_key == "task-034"
        assert "task-034" in result.branch
        assert "new-feature" in result.branch
        assert str(wt_expected) in result.path

        reg = json.loads(mgr._registry_path.read_text(encoding="utf-8"))
        assert reg["version"] == REGISTRY_VERSION
        assert len(reg["worktrees"]) == 1
        assert reg["worktrees"][0]["task_key"] == "task-034"

    def test_create_invalid_task_key(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        result = mgr.create_worktree("not-a-valid-key!!!")
        assert not result.ok
        assert "invalid" in result.message.lower()

    def test_create_duplicate_task_key(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        mgr._write_registry([{
            "task_key": "task-034",
            "branch": "agent/task-034",
            "path": "/tmp/existing",
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
        }])

        result = mgr.create_worktree("task-034")
        assert not result.ok
        assert "already" in result.message.lower()

    def test_create_path_exists(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        wt_path = tmp_path.parent / f"{tmp_path.name}-wt-task-034"
        wt_path.mkdir(parents=True)

        result = mgr.create_worktree("task-034")
        assert not result.ok
        assert "exists" in result.message.lower()

    def test_create_fetch_fails(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            return_value=_fail_result("FETCH_FAILED", "network error"),
        ):
            result = mgr.create_worktree("task-034")

        assert not result.ok
        assert "network" in result.message.lower() or "failed" in result.message.lower()

    def test_create_worktree_add_fails(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        call_count = 0

        def mock_git(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _ok_result()
            return _fail_result("WORKTREE_ADD_FAILED", "branch exists")

        with patch("harness.core.worktree_lifecycle.run_git_result", side_effect=mock_git):
            result = mgr.create_worktree("task-034")

        assert not result.ok

    def test_create_no_desc(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            return_value=_ok_result(),
        ):
            with patch.object(mgr, "_copy_artifacts"):
                result = mgr.create_worktree("task-034")

        assert result.ok
        assert result.branch == "agent/task-034"


class TestListWorktrees:
    def test_list_empty(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        with patch.object(mgr, "_git_worktree_paths", return_value=set()):
            entries = mgr.list_worktrees()

        assert entries == []

    def test_list_active(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        wt_path = str((tmp_path.parent / "proj-wt-task-034").resolve())
        mgr._write_registry([{
            "task_key": "task-034",
            "branch": "agent/task-034",
            "path": wt_path,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
        }])

        with patch.object(
            mgr, "_git_worktree_paths",
            return_value={wt_path, str(tmp_path.resolve())},
        ):
            entries = mgr.list_worktrees()

        assert len(entries) == 1
        assert entries[0].status == "active"
        assert entries[0].task_key == "task-034"

    def test_list_stale(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        mgr._write_registry([{
            "task_key": "task-034",
            "branch": "agent/task-034",
            "path": "/gone/path",
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
        }])

        with patch.object(mgr, "_git_worktree_paths", return_value=set()):
            entries = mgr.list_worktrees()

        assert len(entries) == 1
        assert entries[0].status == "stale"

    def test_list_unmanaged(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        extra_path = str((tmp_path.parent / "manual-wt").resolve())
        with patch.object(
            mgr, "_git_worktree_paths",
            return_value={str(tmp_path.resolve()), extra_path},
        ):
            entries = mgr.list_worktrees()

        assert len(entries) == 1
        assert entries[0].status == "unmanaged"
        assert entries[0].path == extra_path


class TestRemoveWorktree:
    def test_remove_by_task_key(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        wt_path = str(tmp_path.parent / "proj-wt-task-034")
        mgr._write_registry([{
            "task_key": "task-034",
            "branch": "agent/task-034",
            "path": wt_path,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
        }])

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            return_value=_ok_result(),
        ):
            result = mgr.remove_worktree("task-034")

        assert result.ok
        reg = mgr._read_registry()
        assert len(reg) == 0

    def test_remove_by_path(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        wt_path = str(tmp_path.parent / "proj-wt-task-035")
        mgr._write_registry([{
            "task_key": "task-035",
            "branch": "agent/task-035",
            "path": wt_path,
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
        }])

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            return_value=_ok_result(),
        ):
            result = mgr.remove_worktree(wt_path)

        assert result.ok

    def test_remove_not_found(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        result = mgr.remove_worktree("task-999")
        assert not result.ok
        assert "not found" in result.message.lower() or "no worktree" in result.message.lower()

    def test_remove_git_fails(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        mgr._write_registry([{
            "task_key": "task-034",
            "branch": "agent/task-034",
            "path": "/some/path",
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
        }])

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            return_value=_fail_result("WORKTREE_REMOVE_FAILED", "locked"),
        ):
            result = mgr.remove_worktree("task-034")

        assert not result.ok
        reg = mgr._read_registry()
        assert len(reg) == 1

    def test_remove_with_prune_branch(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        mgr._write_registry([{
            "task_key": "task-034",
            "branch": "agent/task-034",
            "path": "/some/path",
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
        }])

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            return_value=_ok_result(),
        ):
            result = mgr.remove_worktree("task-034", prune_branch=True)

        assert result.ok
        assert result.branch_pruned

    def test_remove_with_force(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        mgr._write_registry([{
            "task_key": "task-034",
            "branch": "agent/task-034",
            "path": "/some/path",
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active",
        }])

        calls: list[list[str]] = []

        def capture_git(args, cwd, **kwargs):
            calls.append(args)
            return _ok_result()

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            side_effect=capture_git,
        ):
            result = mgr.remove_worktree("task-034", force=True)

        assert result.ok
        assert "--force" in calls[0]


class TestRegistry:
    def test_read_empty(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)
        assert mgr._read_registry() == []

    def test_read_corrupt(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)
        mgr._registry_path.write_text("NOT JSON!!!", encoding="utf-8")
        assert mgr._read_registry() == []

    def test_write_read_roundtrip(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        entries = [
            {"task_key": "task-001", "branch": "agent/task-001", "path": "/a"},
            {"task_key": "task-002", "branch": "agent/task-002", "path": "/b"},
        ]
        mgr._write_registry(entries)

        read_back = mgr._read_registry()
        assert len(read_back) == 2
        assert read_back[0]["task_key"] == "task-001"
        assert read_back[1]["task_key"] == "task-002"

        raw = json.loads(mgr._registry_path.read_text(encoding="utf-8"))
        assert raw["version"] == REGISTRY_VERSION

    def test_atomic_write_no_partial(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        mgr._write_registry([{"task_key": "task-001"}])

        with patch("harness.core.worktree_lifecycle.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                mgr._write_registry([{"task_key": "task-002"}])

        data = mgr._read_registry()
        assert len(data) == 1
        assert data[0]["task_key"] == "task-001"


class TestCopyArtifacts:
    def test_copies_whitelisted_dirs_and_files(self, tmp_path: Path):
        _make_config(tmp_path)
        (tmp_path / ".cursor" / "skills" / "harness").mkdir(parents=True)
        (tmp_path / ".cursor" / "skills" / "harness" / "SKILL.md").write_text("skill")
        (tmp_path / ".cursor" / "agents").mkdir(parents=True)
        (tmp_path / ".cursor" / "agents" / "architect.md").write_text("arch")
        (tmp_path / ".cursor" / "rules").mkdir(parents=True)
        (tmp_path / ".cursor" / "rules" / "workflow.mdc").write_text("rule")
        (tmp_path / ".cursor" / "worktrees.json").write_text("{}")
        (tmp_path / ".harness-flow" / "vision.md").write_text("vision")

        mgr = WorktreeLifecycleManager(tmp_path)
        target = tmp_path / "target-wt"
        target.mkdir()

        mgr._copy_artifacts(target)

        assert (target / ".cursor" / "skills" / "harness" / "SKILL.md").read_text() == "skill"
        assert (target / ".cursor" / "agents" / "architect.md").read_text() == "arch"
        assert (target / ".cursor" / "rules" / "workflow.mdc").read_text() == "rule"
        assert (target / ".cursor" / "worktrees.json").read_text() == "{}"
        assert (target / ".harness-flow" / "config.toml").is_file()
        assert (target / ".harness-flow" / "vision.md").read_text() == "vision"

    def test_skips_missing_files(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)
        target = tmp_path / "target-wt"
        target.mkdir()

        mgr._copy_artifacts(target)

        assert (target / ".harness-flow" / "config.toml").is_file()
        assert not (target / ".cursor" / "skills").exists()
        assert not (target / ".harness-flow" / "vision.md").exists()


class TestGitWorktreePaths:
    def test_porcelain_parsing(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        porcelain = (
            f"worktree {tmp_path}\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            f"worktree {tmp_path.parent / 'wt-1'}\n"
            "HEAD def456\n"
            "branch refs/heads/agent/task-001\n"
        )

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            return_value=_ok_result(stdout=porcelain),
        ):
            paths = mgr._git_worktree_paths()

        assert str(tmp_path.resolve()) in paths
        assert str((tmp_path.parent / "wt-1").resolve()) in paths

    def test_fallback_on_porcelain_failure(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        call_count = 0

        def mock_git(args, cwd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fail_result("WORKTREE_LIST_FAILED")
            plain = (
                f"{tmp_path}  abc123 [main]\n"
                f"{tmp_path.parent / 'wt-1'}  def456 [agent/task-001]\n"
            )
            return _ok_result(stdout=plain)

        with patch(
            "harness.core.worktree_lifecycle.run_git_result",
            side_effect=mock_git,
        ):
            paths = mgr._git_worktree_paths()

        assert str(tmp_path.resolve()) in paths
