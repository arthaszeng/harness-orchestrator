"""Tests for branch lifecycle orchestration."""

from __future__ import annotations

from pathlib import Path

from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.core.config import HarnessConfig
from harness.core.task_identity import TaskIdentityResolver
from harness.core.worktree import WorktreeInfo
from harness.integrations.git_ops import GitOperationResult


def _manager(tmp_path: Path) -> BranchLifecycleManager:
    cfg = HarnessConfig()
    return BranchLifecycleManager(
        project_root=tmp_path,
        config=cfg,
        resolver=TaskIdentityResolver.from_config(cfg),
    )


def test_preflight_detects_dirty_worktree(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr("harness.core.branch_lifecycle.ensure_clean_result", lambda _cwd: GitOperationResult(
        ok=False, code="DIRTY_WORKTREE", message="dirty",
    ))
    result = manager.preflight_repo_state()
    assert result.ok is False
    assert result.code == "DIRTY_WORKTREE"


def test_preflight_detects_detached_head(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK", message="clean"),
    )
    monkeypatch.setattr("harness.core.branch_lifecycle.current_branch", lambda _cwd: "")
    result = manager.preflight_repo_state()
    assert result.ok is False
    assert result.code == "DETACHED_HEAD"


def test_prepare_task_branch_rejects_invalid_key(tmp_path: Path):
    manager = _manager(tmp_path)
    result = manager.prepare_task_branch("invalid-key", "demo")
    assert result.ok is False
    assert result.code == "INVALID_TASK_KEY"


def test_prepare_task_branch_rejects_dirty_repo(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=False, code="DIRTY_WORKTREE", message="dirty"),
    )
    result = manager.prepare_task_branch("task-001", "demo")
    assert result.ok is False
    assert result.code == "DIRTY_WORKTREE"


def test_sync_feature_with_trunk_reports_rebase_conflict(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    responses = iter(
        [
            GitOperationResult(ok=True, code="OK", message="fetch ok"),
            GitOperationResult(ok=False, code="REBASE_CONFLICT", message="rebase failed"),
            GitOperationResult(ok=True, code="OK", message="abort ok"),
        ]
    )

    monkeypatch.setattr(
        "harness.core.branch_lifecycle.run_git_result",
        lambda *args, **kwargs: next(responses),
    )
    result = manager.sync_feature_with_trunk()
    assert result.ok is False
    assert result.code == "REBASE_CONFLICT"


def test_prepare_task_branch_skips_when_worktree(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.detect_worktree",
        lambda _cwd: WorktreeInfo(common_dir=tmp_path / ".git", git_dir=tmp_path / ".git/worktrees/x", branch="agent/task-001"),
    )
    result = manager.prepare_task_branch("task-001", "demo")
    assert result.ok is True
    assert result.code == "WORKTREE_SKIP"


def test_sync_feature_with_trunk_reports_abort_failure(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    responses = iter(
        [
            GitOperationResult(ok=True, code="OK", message="fetch ok"),
            GitOperationResult(ok=False, code="REBASE_CONFLICT", message="rebase failed"),
            GitOperationResult(ok=False, code="REBASE_ABORT_FAILED", message="abort failed"),
        ]
    )
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.run_git_result",
        lambda *args, **kwargs: next(responses),
    )
    result = manager.sync_feature_with_trunk()
    assert result.ok is False
    assert result.code == "REBASE_ABORT_FAILED"


def test_prepare_task_branch_resumes_existing_branch(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK"),
    )
    monkeypatch.setattr("harness.core.branch_lifecycle.detect_worktree", lambda _cwd: None)
    responses = iter(
        [
            GitOperationResult(ok=True, code="OK", message="checkout trunk"),
            GitOperationResult(ok=True, code="OK", message="pull trunk"),
            GitOperationResult(ok=False, code="BRANCH_CREATE_FAILED", message="exists"),
            GitOperationResult(ok=True, code="OK", message="resume branch"),
        ]
    )
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.run_git_result",
        lambda *args, **kwargs: next(responses),
    )
    result = manager.prepare_task_branch("task-001", "demo")
    assert result.ok is True
    assert result.context.get("created") == "false"

