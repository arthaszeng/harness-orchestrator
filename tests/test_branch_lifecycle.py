"""Tests for branch lifecycle orchestration."""

from __future__ import annotations

from pathlib import Path

from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.core.config import HarnessConfig
from harness.core.task_identity import TaskIdentityResolver
from harness.integrations.git_ops import GitOperationResult


def _manager(tmp_path: Path) -> BranchLifecycleManager:
    cfg = HarnessConfig()
    return BranchLifecycleManager(
        project_root=tmp_path,
        config=cfg,
        resolver=TaskIdentityResolver.from_config(cfg),
    )


def test_preflight_detects_dirty_working_tree(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr("harness.core.branch_lifecycle.ensure_clean_result", lambda _cwd: GitOperationResult(
        ok=False, code="DIRTY_WORKING_TREE", message="dirty",
    ))
    result = manager.preflight_repo_state()
    assert result.ok is False
    assert result.code == "DIRTY_WORKING_TREE"


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
        lambda _cwd: GitOperationResult(ok=False, code="DIRTY_WORKING_TREE", message="dirty"),
    )
    result = manager.prepare_task_branch("task-001", "demo")
    assert result.ok is False
    assert result.code == "DIRTY_WORKING_TREE"


def test_sync_feature_with_trunk_reports_rebase_conflict(tmp_path: Path, monkeypatch):
    """Rebase conflict on non-auto-resolvable file → abort with conflict file list."""
    manager = _manager(tmp_path)

    def _mock_git(args, *_a, **_kw):
        cmd = args[0] if args else ""
        if cmd == "fetch":
            return GitOperationResult(ok=True, code="OK", message="fetch ok")
        if args == ["rebase", "origin/main"]:
            return GitOperationResult(ok=False, code="REBASE_CONFLICT", message="rebase failed")
        if args == ["diff", "--name-only", "--diff-filter=U"]:
            return GitOperationResult(ok=True, code="OK", stdout="src/main.py\n")
        if args[:2] == ["rebase", "--abort"]:
            return GitOperationResult(ok=True, code="OK", message="abort ok")
        return GitOperationResult(ok=True, code="OK")

    monkeypatch.setattr("harness.core.branch_lifecycle.run_git_result", _mock_git)
    result = manager.sync_feature_with_trunk()
    assert result.ok is False
    assert result.code == "REBASE_CONFLICT"
    assert "src/main.py" in result.context.get("manual_conflict_files", "")


def test_sync_feature_with_trunk_auto_resolves_lock_files(tmp_path: Path, monkeypatch):
    """Lock file conflict → auto-resolve with --ours, rebase --continue succeeds."""
    manager = _manager(tmp_path)

    def _mock_git(args, *_a, **_kw):
        cmd = args[0] if args else ""
        if cmd == "fetch":
            return GitOperationResult(ok=True, code="OK", message="fetch ok")
        if args == ["rebase", "origin/main"]:
            return GitOperationResult(ok=False, code="REBASE_CONFLICT", message="rebase failed")
        if args == ["diff", "--name-only", "--diff-filter=U"]:
            return GitOperationResult(ok=True, code="OK", stdout="poetry.lock\n")
        if args == ["checkout", "--ours", "poetry.lock"]:
            return GitOperationResult(ok=True, code="OK")
        if args == ["add", "-f", "poetry.lock"]:
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "--continue"]:
            return GitOperationResult(ok=True, code="OK", message="continue ok")
        return GitOperationResult(ok=True, code="OK")

    monkeypatch.setattr("harness.core.branch_lifecycle.run_git_result", _mock_git)
    result = manager.sync_feature_with_trunk()
    assert result.ok is True
    assert result.code == "REBASE_AUTO_RESOLVED"
    assert "poetry.lock" in result.context.get("auto_resolved_files", "")


def test_sync_feature_with_trunk_auto_resolves_cursor_files(tmp_path: Path, monkeypatch):
    """Files under .cursor/ → auto-resolve."""
    manager = _manager(tmp_path)

    def _mock_git(args, *_a, **_kw):
        if args == ["fetch", "origin", "main"]:
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "origin/main"]:
            return GitOperationResult(ok=False, code="REBASE_CONFLICT", message="conflict")
        if args == ["diff", "--name-only", "--diff-filter=U"]:
            return GitOperationResult(ok=True, code="OK", stdout=".cursor/rules/foo.mdc\n")
        if args[:2] == ["checkout", "--ours"]:
            return GitOperationResult(ok=True, code="OK")
        if args[:2] == ["add", "-f"]:
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "--continue"]:
            return GitOperationResult(ok=True, code="OK")
        return GitOperationResult(ok=True, code="OK")

    monkeypatch.setattr("harness.core.branch_lifecycle.run_git_result", _mock_git)
    result = manager.sync_feature_with_trunk()
    assert result.ok is True
    assert result.code == "REBASE_AUTO_RESOLVED"


def test_sync_auto_resolve_uses_force_add_for_gitignored_files(tmp_path: Path, monkeypatch):
    """git add -f is used so gitignored-but-tracked files (e.g. .cursor/) can be staged."""
    manager = _manager(tmp_path)
    add_calls: list[list[str]] = []

    def _mock_git(args, *_a, **_kw):
        if args[0] == "fetch":
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "origin/main"]:
            return GitOperationResult(ok=False, code="REBASE_CONFLICT", message="conflict")
        if args == ["diff", "--name-only", "--diff-filter=U"]:
            return GitOperationResult(ok=True, code="OK", stdout=".cursor/rules/foo.mdc\n")
        if args[:2] == ["checkout", "--ours"]:
            return GitOperationResult(ok=True, code="OK")
        if args[:2] == ["add", "-f"]:
            add_calls.append(list(args))
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "--continue"]:
            return GitOperationResult(ok=True, code="OK")
        return GitOperationResult(ok=True, code="OK")

    monkeypatch.setattr("harness.core.branch_lifecycle.run_git_result", _mock_git)
    result = manager.sync_feature_with_trunk()
    assert result.ok is True
    assert result.code == "REBASE_AUTO_RESOLVED"
    assert len(add_calls) == 1
    assert add_calls[0] == ["add", "-f", ".cursor/rules/foo.mdc"]


def test_sync_feature_with_trunk_mixed_conflict_aborts(tmp_path: Path, monkeypatch):
    """Mix of auto-resolvable and manual files → abort with context."""
    manager = _manager(tmp_path)

    def _mock_git(args, *_a, **_kw):
        if args[0] == "fetch":
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "origin/main"]:
            return GitOperationResult(ok=False, code="REBASE_CONFLICT", message="conflict")
        if args == ["diff", "--name-only", "--diff-filter=U"]:
            return GitOperationResult(ok=True, code="OK", stdout="poetry.lock\nsrc/app.py\n")
        if args[:2] == ["rebase", "--abort"]:
            return GitOperationResult(ok=True, code="OK")
        return GitOperationResult(ok=True, code="OK")

    monkeypatch.setattr("harness.core.branch_lifecycle.run_git_result", _mock_git)
    result = manager.sync_feature_with_trunk()
    assert result.ok is False
    assert result.code == "REBASE_CONFLICT"
    assert "src/app.py" in result.context.get("manual_conflict_files", "")


def test_sync_feature_with_trunk_multi_commit_auto_resolve(tmp_path: Path, monkeypatch):
    """Multi-commit rebase: first continue triggers new conflict, second resolves."""
    manager = _manager(tmp_path)
    continue_count = {"n": 0}

    def _mock_git(args, *_a, **_kw):
        if args[0] == "fetch":
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "origin/main"]:
            return GitOperationResult(ok=False, code="REBASE_CONFLICT", message="conflict")
        if args == ["diff", "--name-only", "--diff-filter=U"]:
            return GitOperationResult(ok=True, code="OK", stdout="poetry.lock\n")
        if args[:2] == ["checkout", "--ours"]:
            return GitOperationResult(ok=True, code="OK")
        if args[:2] == ["add", "-f"]:
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "--continue"]:
            continue_count["n"] += 1
            if continue_count["n"] == 1:
                return GitOperationResult(ok=False, code="REBASE_CONTINUE_FAILED", message="next commit conflict")
            return GitOperationResult(ok=True, code="OK")
        if args == ["status", "--porcelain"]:
            if continue_count["n"] == 1:
                return GitOperationResult(ok=True, code="OK", stdout="UU poetry.lock\n")
            return GitOperationResult(ok=True, code="OK", stdout="")
        return GitOperationResult(ok=True, code="OK")

    monkeypatch.setattr("harness.core.branch_lifecycle.run_git_result", _mock_git)
    result = manager.sync_feature_with_trunk()
    assert result.ok is True
    assert result.code == "REBASE_AUTO_RESOLVED"
    assert continue_count["n"] == 2


def test_sync_feature_with_trunk_no_conflict(tmp_path: Path, monkeypatch):
    """No conflict → normal success."""
    manager = _manager(tmp_path)

    def _mock_git(args, *_a, **_kw):
        if args[0] == "fetch":
            return GitOperationResult(ok=True, code="OK")
        if args[:1] == ["rebase"]:
            return GitOperationResult(ok=True, code="OK", message="rebase ok")
        return GitOperationResult(ok=True, code="OK")

    monkeypatch.setattr("harness.core.branch_lifecycle.run_git_result", _mock_git)
    result = manager.sync_feature_with_trunk()
    assert result.ok is True
    assert result.code == "OK"


def test_sync_feature_with_trunk_continue_fails_non_conflict(tmp_path: Path, monkeypatch):
    """Auto-resolve succeeds but rebase --continue fails for non-conflict reason → abort."""
    manager = _manager(tmp_path)

    def _mock_git(args, *_a, **_kw):
        if args[0] == "fetch":
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "origin/main"]:
            return GitOperationResult(ok=False, code="REBASE_CONFLICT", message="conflict")
        if args == ["diff", "--name-only", "--diff-filter=U"]:
            return GitOperationResult(ok=True, code="OK", stdout="poetry.lock\n")
        if args[:2] == ["checkout", "--ours"]:
            return GitOperationResult(ok=True, code="OK")
        if args[:2] == ["add", "-f"]:
            return GitOperationResult(ok=True, code="OK")
        if args == ["rebase", "--continue"]:
            return GitOperationResult(ok=False, code="REBASE_CONTINUE_FAILED", message="hook failed")
        if args == ["status", "--porcelain"]:
            return GitOperationResult(ok=True, code="OK", stdout="M src/foo.py\n")
        if args[:2] == ["rebase", "--abort"]:
            return GitOperationResult(ok=True, code="OK")
        return GitOperationResult(ok=True, code="OK")

    monkeypatch.setattr("harness.core.branch_lifecycle.run_git_result", _mock_git)
    result = manager.sync_feature_with_trunk()
    assert result.ok is False
    assert result.code == "REBASE_CONTINUE_FAILED"


def test_preflight_returns_branch_task_key_for_agent_branch(tmp_path: Path, monkeypatch):
    """preflight context includes branch_task_key extracted from agent branch."""
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK", message="clean"),
    )
    monkeypatch.setattr("harness.core.branch_lifecycle.current_branch", lambda _cwd: "agent/task-036-worktree-bug-bash")
    extract_calls: list[dict] = []

    def _spy_extract(branch, **kwargs):
        extract_calls.append({"branch": branch, "kwargs": kwargs})
        return "task-036"

    monkeypatch.setattr(
        "harness.core.branch_lifecycle.extract_task_key_from_branch",
        _spy_extract,
    )
    result = manager.preflight_repo_state()
    assert result.ok is True
    assert result.context["branch_task_key"] == "task-036"
    assert len(extract_calls) == 1
    assert extract_calls[0]["branch"] == "agent/task-036-worktree-bug-bash"
    assert extract_calls[0]["kwargs"].get("cwd") == tmp_path


def test_preflight_returns_empty_task_key_for_non_agent_branch(tmp_path: Path, monkeypatch):
    """preflight context returns empty branch_task_key for non-agent branches."""
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK", message="clean"),
    )
    monkeypatch.setattr("harness.core.branch_lifecycle.current_branch", lambda _cwd: "main")
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.extract_task_key_from_branch",
        lambda branch, **_kw: None,
    )
    result = manager.preflight_repo_state()
    assert result.ok is True
    assert result.context["branch_task_key"] == ""


def test_preflight_returns_empty_task_key_for_nonstandard_agent_branch(tmp_path: Path, monkeypatch):
    """Agent branch without task key pattern returns empty branch_task_key."""
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK", message="clean"),
    )
    monkeypatch.setattr("harness.core.branch_lifecycle.current_branch", lambda _cwd: "agent/foo-bar")
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.extract_task_key_from_branch",
        lambda branch, **_kw: None,
    )
    result = manager.preflight_repo_state()
    assert result.ok is True
    assert result.context["branch_task_key"] == ""


def test_prepare_task_branch_resumes_existing_branch(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.branch_lifecycle.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK"),
    )
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

