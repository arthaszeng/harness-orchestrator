"""Tests for harness worktree-setup command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.commands.worktree_setup import (
    WORKTREE_SYMLINK_TARGETS,
    _detect_main_worktree_root,
    run_worktree_setup,
)


def _fake_run_git(common_dir: str, git_dir: str):
    """Return a factory that simulates run_git for rev-parse calls."""
    def _run(args, cwd, *, timeout=30, env=None):
        result = MagicMock()
        result.returncode = 0
        if "--git-common-dir" in args:
            result.stdout = common_dir + "\n"
        elif "--git-dir" in args:
            result.stdout = git_dir + "\n"
        else:
            result.returncode = 1
            result.stdout = ""
        return result
    return _run


class TestDetectMainWorktreeRoot:
    def test_linked_worktree_returns_main_root(self, tmp_path, monkeypatch):
        main_root = tmp_path / "main"
        main_root.mkdir()
        common_dir = main_root / ".git"
        common_dir.mkdir()
        wt_git_dir = tmp_path / "wt" / ".git"
        wt_git_dir.mkdir(parents=True)

        monkeypatch.setattr(
            "harness.commands.worktree_setup.run_git",
            _fake_run_git(str(common_dir), str(wt_git_dir)),
        )
        result = _detect_main_worktree_root(tmp_path / "wt")
        assert result == main_root

    def test_main_worktree_returns_none(self, tmp_path, monkeypatch):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        monkeypatch.setattr(
            "harness.commands.worktree_setup.run_git",
            _fake_run_git(str(git_dir), str(git_dir)),
        )
        result = _detect_main_worktree_root(tmp_path)
        assert result is None

    def test_git_failure_returns_none(self, tmp_path, monkeypatch):
        def _fail(*a, **kw):
            raise OSError("no git")

        monkeypatch.setattr("harness.commands.worktree_setup.run_git", _fail)
        result = _detect_main_worktree_root(tmp_path)
        assert result is None

    def test_nonzero_returncode_returns_none(self, tmp_path, monkeypatch):
        def _run(args, cwd, *, timeout=30, env=None):
            r = MagicMock()
            r.returncode = 128
            r.stdout = ""
            return r

        monkeypatch.setattr("harness.commands.worktree_setup.run_git", _run)
        result = _detect_main_worktree_root(tmp_path)
        assert result is None

    def test_null_byte_output_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "harness.commands.worktree_setup.run_git",
            _fake_run_git("/some/\x00path", "/other/path"),
        )
        result = _detect_main_worktree_root(tmp_path)
        assert result is None


class TestRunWorktreeSetup:
    def test_creates_symlinks_in_linked_worktree(self, tmp_path, monkeypatch):
        main_root = tmp_path / "main"
        wt_root = tmp_path / "wt"
        wt_root.mkdir()

        for target in WORKTREE_SYMLINK_TARGETS:
            (main_root / target).mkdir(parents=True, exist_ok=True)

        common_dir = main_root / ".git"
        common_dir.mkdir(parents=True)
        wt_git = wt_root / ".git"
        wt_git.mkdir()

        monkeypatch.setattr(
            "harness.commands.worktree_setup.run_git",
            _fake_run_git(str(common_dir), str(wt_git)),
        )

        run_worktree_setup(cwd=wt_root)

        for target in WORKTREE_SYMLINK_TARGETS:
            link = wt_root / target
            assert link.is_symlink(), f"{target} should be a symlink"
            assert link.resolve() == (main_root / target).resolve()

    def test_skips_existing_correct_symlinks(self, tmp_path, monkeypatch):
        main_root = tmp_path / "main"
        wt_root = tmp_path / "wt"
        wt_root.mkdir()

        for target in WORKTREE_SYMLINK_TARGETS:
            source = main_root / target
            source.mkdir(parents=True, exist_ok=True)
            link = wt_root / target
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(source)

        common_dir = main_root / ".git"
        common_dir.mkdir(parents=True)
        wt_git = wt_root / ".git"
        wt_git.mkdir()

        monkeypatch.setattr(
            "harness.commands.worktree_setup.run_git",
            _fake_run_git(str(common_dir), str(wt_git)),
        )

        run_worktree_setup(cwd=wt_root)

        for target in WORKTREE_SYMLINK_TARGETS:
            link = wt_root / target
            assert link.is_symlink()

    def test_not_worktree_does_nothing(self, tmp_path, monkeypatch):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        monkeypatch.setattr(
            "harness.commands.worktree_setup.run_git",
            _fake_run_git(str(git_dir), str(git_dir)),
        )

        run_worktree_setup(cwd=tmp_path)

    def test_missing_source_skips(self, tmp_path, monkeypatch):
        main_root = tmp_path / "main"
        main_root.mkdir()
        wt_root = tmp_path / "wt"
        wt_root.mkdir()

        common_dir = main_root / ".git"
        common_dir.mkdir()
        wt_git = wt_root / ".git"
        wt_git.mkdir()

        monkeypatch.setattr(
            "harness.commands.worktree_setup.run_git",
            _fake_run_git(str(common_dir), str(wt_git)),
        )

        run_worktree_setup(cwd=wt_root)

        for target in WORKTREE_SYMLINK_TARGETS:
            assert not (wt_root / target).exists()
