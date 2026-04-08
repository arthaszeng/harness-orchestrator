"""worktree-init command tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.commands.worktree_init import _SYMLINK_TARGETS, run_worktree_init
from harness.core.worktree import WorktreeInfo

runner = CliRunner()


@pytest.fixture()
def linked_worktree(tmp_path: Path):
    """Set up a fake main worktree + linked worktree directory pair."""
    main_root = tmp_path / "main"
    main_root.mkdir()
    harness = main_root / ".harness-flow"
    harness.mkdir()
    (harness / "config.toml").write_text('[project]\nname="test"\n')
    skills = main_root / ".cursor" / "skills" / "harness"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("# skill")
    agents = main_root / ".cursor" / "agents"
    agents.mkdir(parents=True)
    (agents / "agent.md").write_text("# agent")
    rules = main_root / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "rule.mdc").write_text("# rule")

    linked_root = tmp_path / "linked"
    linked_root.mkdir()

    wt_info = WorktreeInfo(
        common_dir=main_root / ".git",
        git_dir=linked_root / ".git" / "worktrees" / "linked",
        branch="agent/task-099-test",
    )
    return main_root, linked_root, wt_info


class TestWorktreeInitCreatesSymlinks:
    def test_creates_all_symlinks(self, linked_worktree, monkeypatch):
        main_root, linked_root, wt_info = linked_worktree
        monkeypatch.chdir(linked_root)

        with patch("harness.commands.worktree_init.resolve_main_worktree_root", return_value=main_root):
            run_worktree_init(force=False)

        for rel in _SYMLINK_TARGETS:
            target = linked_root / rel
            assert target.is_symlink(), f"{rel} should be a symlink"
            assert target.resolve() == (main_root / rel).resolve()

    def test_skips_existing_correct_symlinks(self, linked_worktree, monkeypatch):
        main_root, linked_root, wt_info = linked_worktree
        monkeypatch.chdir(linked_root)

        for rel in _SYMLINK_TARGETS:
            target = linked_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(main_root / rel)

        with patch("harness.commands.worktree_init.resolve_main_worktree_root", return_value=main_root):
            run_worktree_init(force=False)

        for rel in _SYMLINK_TARGETS:
            target = linked_root / rel
            assert target.is_symlink()
            assert target.resolve() == (main_root / rel).resolve()

    def test_skips_missing_source(self, linked_worktree, monkeypatch):
        main_root, linked_root, wt_info = linked_worktree
        monkeypatch.chdir(linked_root)
        import shutil
        shutil.rmtree(main_root / ".cursor" / "agents")

        with patch("harness.commands.worktree_init.resolve_main_worktree_root", return_value=main_root):
            run_worktree_init(force=False)

        assert not (linked_root / ".cursor" / "agents").exists()
        assert (linked_root / ".harness-flow").is_symlink()

    def test_force_overwrites_existing_dir(self, linked_worktree, monkeypatch):
        main_root, linked_root, wt_info = linked_worktree
        monkeypatch.chdir(linked_root)
        existing = linked_root / ".harness-flow"
        existing.mkdir(parents=True, exist_ok=True)
        (existing / "old-file.txt").write_text("old")

        with patch("harness.commands.worktree_init.resolve_main_worktree_root", return_value=main_root):
            run_worktree_init(force=True)

        assert (linked_root / ".harness-flow").is_symlink()

    def test_refuses_without_force_when_dir_exists(self, linked_worktree, monkeypatch):
        from click.exceptions import Exit

        main_root, linked_root, wt_info = linked_worktree
        monkeypatch.chdir(linked_root)
        existing = linked_root / ".harness-flow"
        existing.mkdir(parents=True, exist_ok=True)

        with patch("harness.commands.worktree_init.resolve_main_worktree_root", return_value=main_root):
            with pytest.raises(Exit):
                run_worktree_init(force=False)

        assert not (linked_root / ".harness-flow").is_symlink()


class TestWorktreeInitErrors:
    def test_not_worktree_exits(self, tmp_path, monkeypatch):
        from click.exceptions import Exit

        monkeypatch.chdir(tmp_path)
        with patch("harness.commands.worktree_init.resolve_main_worktree_root", return_value=None):
            with pytest.raises(Exit):
                run_worktree_init(force=False)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_windows_exits(self, tmp_path, monkeypatch):
        from click.exceptions import Exit

        monkeypatch.chdir(tmp_path)
        with pytest.raises(Exit):
            run_worktree_init(force=False)


class TestWorktreeInitCLI:
    def test_cli_command_registered(self):
        result = runner.invoke(app, ["worktree-init", "--help"])
        assert result.exit_code == 0
        assert "symlinks" in result.output.lower() or "worktree" in result.output.lower()
