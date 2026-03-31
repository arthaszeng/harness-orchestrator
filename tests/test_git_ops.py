"""Tests for harness.integrations.git_ops branch lifecycle functions."""

import subprocess
from pathlib import Path

import pytest

from harness.integrations.git_ops import (
    DirtyWorktreeError,
    current_branch,
    ensure_clean,
    has_changes,
    rebase_and_merge,
    safe_cleanup,
)

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "t@t.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "t@t.com",
    "HOME": str(Path.home()),
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=_GIT_ENV,
    )


def _init_repo(tmp_path: Path) -> Path:
    """Create a git repo with one commit on main."""
    _git(["init"], tmp_path)
    _git(["checkout", "-b", "main"], tmp_path)
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "initial commit"], tmp_path)
    return tmp_path


# ── ensure_clean ─────────────────────────────────────────────────


class TestEnsureClean:
    def test_clean_repo(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        ensure_clean(repo)

    def test_dirty_repo_raises(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        (repo / "dirty.txt").write_text("uncommitted", encoding="utf-8")
        with pytest.raises(DirtyWorktreeError):
            ensure_clean(repo)

    def test_staged_changes_raise(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        (repo / "staged.txt").write_text("staged", encoding="utf-8")
        _git(["add", "staged.txt"], repo)
        with pytest.raises(DirtyWorktreeError):
            ensure_clean(repo)


# ── rebase_and_merge ─────────────────────────────────────────────


class TestRebaseAndMerge:
    def test_simple_rebase(self, tmp_path: Path):
        repo = _init_repo(tmp_path)

        _git(["checkout", "-b", "feature"], repo)
        (repo / "feature.txt").write_text("new feature", encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-m", "add feature"], repo)

        ok = rebase_and_merge("feature", "main", repo)

        assert ok is True
        assert current_branch(repo) == "main"
        assert (repo / "feature.txt").exists()
        branches = _git(["branch"], repo).stdout
        assert "feature" not in branches

    def test_rebase_with_diverged_main(self, tmp_path: Path):
        """Rebase works when main has advanced since the branch point."""
        repo = _init_repo(tmp_path)

        _git(["checkout", "-b", "feature"], repo)
        (repo / "feature.txt").write_text("feature work", encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-m", "feature commit"], repo)

        _git(["checkout", "main"], repo)
        (repo / "main_update.txt").write_text("main advance", encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-m", "main advance"], repo)

        ok = rebase_and_merge("feature", "main", repo)

        assert ok is True
        assert current_branch(repo) == "main"
        assert (repo / "feature.txt").exists()
        assert (repo / "main_update.txt").exists()

    def test_rebase_conflict_returns_false(self, tmp_path: Path):
        """Conflicting rebase aborts and returns False."""
        repo = _init_repo(tmp_path)

        _git(["checkout", "-b", "feature"], repo)
        (repo / "README.md").write_text("feature version", encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-m", "feature change"], repo)

        _git(["checkout", "main"], repo)
        (repo / "README.md").write_text("main version", encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-m", "main conflicting change"], repo)

        ok = rebase_and_merge("feature", "main", repo)

        assert ok is False
        assert current_branch(repo) == "main"
        branches = _git(["branch"], repo).stdout
        assert "feature" in branches

    def test_nonexistent_source_returns_false(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        ok = rebase_and_merge("nonexistent", "main", repo)
        assert ok is False


# ── safe_cleanup ─────────────────────────────────────────────────


class TestSafeCleanup:
    def test_clean_repo_switches_branch(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        _git(["checkout", "-b", "task-branch"], repo)

        safe_cleanup("main", repo)

        assert current_branch(repo) == "main"

    def test_dirty_repo_stashes_and_switches(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        _git(["checkout", "-b", "task-branch"], repo)
        (repo / "wip.txt").write_text("work in progress", encoding="utf-8")

        safe_cleanup("main", repo)

        assert current_branch(repo) == "main"
        assert not has_changes(repo)
        stash_list = _git(["stash", "list"], repo).stdout
        assert "harness-autosave" in stash_list

    def test_already_on_target_branch(self, tmp_path: Path):
        repo = _init_repo(tmp_path)
        safe_cleanup("main", repo)
        assert current_branch(repo) == "main"

    def test_never_raises(self, tmp_path: Path):
        """safe_cleanup should never raise, even with an invalid target."""
        repo = _init_repo(tmp_path)
        safe_cleanup("nonexistent-branch", repo)
