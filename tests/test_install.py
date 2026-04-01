"""Tests for harness install — reinstall/force flow, skip hints, and probe_ides_force."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness.commands.install import (
    _install_cursor_agents,
    _install_codex_agents,
    run_install,
)


@pytest.fixture()
def agents_source(tmp_path: Path) -> Path:
    """Create a minimal agents source directory tree."""
    cursor = tmp_path / "agents" / "cursor"
    cursor.mkdir(parents=True)
    (cursor / "builder.md").write_text("# builder")
    (cursor / "reflector.md").write_text("# reflector")
    codex = tmp_path / "agents" / "codex"
    codex.mkdir(parents=True)
    (codex / "planner.toml").write_text("[planner]")
    return tmp_path / "agents"


class TestCursorAgentsForce:
    """_install_cursor_agents should overwrite when force=True, skip when False."""

    def test_skip_existing_without_force(self, agents_source: Path, tmp_path: Path):
        target_dir = tmp_path / ".cursor" / "agents"
        target_dir.mkdir(parents=True)
        (target_dir / "harness-builder.md").write_text("old")

        with patch("harness.commands.install.Path.home", return_value=tmp_path):
            count = _install_cursor_agents(agents_source, force=False, lang="en")

        assert count == 1  # only reflector installed, builder skipped
        assert (target_dir / "harness-builder.md").read_text() == "old"

    def test_overwrite_existing_with_force(self, agents_source: Path, tmp_path: Path):
        target_dir = tmp_path / ".cursor" / "agents"
        target_dir.mkdir(parents=True)
        (target_dir / "harness-builder.md").write_text("old")

        with patch("harness.commands.install.Path.home", return_value=tmp_path):
            count = _install_cursor_agents(agents_source, force=True, lang="en")

        assert count == 2  # both overwritten
        assert (target_dir / "harness-builder.md").read_text() == "# builder"


class TestRunInstallForceCallsForceProbes:
    """run_install should dispatch to _probe_ides_force when force=True."""

    @patch("harness.commands.install._install_native_mode", return_value=0)
    @patch("harness.commands.install._agents_pkg_dir")
    @patch("harness.commands.install._detect_ide", return_value={"cursor": True, "codex": False})
    @patch("harness.commands.install._probe_ides")
    @patch("harness.commands.install._probe_ides_force")
    def test_force_uses_force_probes(
        self, mock_force, mock_normal, mock_detect, mock_pkg, mock_native, tmp_path: Path
    ):
        mock_force.return_value = {"cursor": True, "codex": False}
        mock_normal.return_value = {"cursor": True, "codex": False}
        pkg = tmp_path / "agents"
        pkg.mkdir()
        (pkg / "cursor").mkdir()
        mock_pkg.return_value = pkg

        with patch("harness.commands.install._install_cursor_agents", return_value=2):
            run_install(force=True, lang="en")

        mock_force.assert_called_once()
        mock_normal.assert_not_called()

    @patch("harness.commands.install._install_native_mode", return_value=0)
    @patch("harness.commands.install._agents_pkg_dir")
    @patch("harness.commands.install._detect_ide", return_value={"cursor": True, "codex": False})
    @patch("harness.commands.install._probe_ides")
    @patch("harness.commands.install._probe_ides_force")
    def test_normal_uses_normal_probes(
        self, mock_force, mock_normal, mock_detect, mock_pkg, mock_native, tmp_path: Path
    ):
        mock_normal.return_value = {"cursor": True, "codex": False}
        pkg = tmp_path / "agents"
        pkg.mkdir()
        (pkg / "cursor").mkdir()
        mock_pkg.return_value = pkg

        with patch("harness.commands.install._install_cursor_agents", return_value=2):
            run_install(force=False, lang="en")

        mock_normal.assert_called_once()
        mock_force.assert_not_called()


class TestForceHintShown:
    """When files are skipped (no force), show the --force hint."""

    @patch("harness.commands.install._install_native_mode", return_value=0)
    @patch("harness.commands.install._agents_pkg_dir")
    @patch("harness.commands.install._detect_ide", return_value={"cursor": True, "codex": False})
    @patch("harness.commands.install._probe_ides", return_value={"cursor": True, "codex": False})
    def test_hint_shown_on_skip(self, mock_probe, mock_detect, mock_pkg, mock_native, tmp_path, capsys):
        pkg = tmp_path / "agents"
        pkg.mkdir()
        (pkg / "cursor").mkdir()
        mock_pkg.return_value = pkg

        with patch("harness.commands.install._install_cursor_agents", return_value=0):
            run_install(force=False, lang="en")

        captured = capsys.readouterr()
        assert "--force" in captured.out


class TestProbeIdesForce:
    """_probe_ides_force should auto-retry without confirmation prompts."""

    @patch("harness.commands.install._run_cli_install", return_value=True)
    @patch("harness.commands.install._ensure_path", return_value=False)
    def test_cursor_retry_on_probe_fail(self, mock_path, mock_cli):
        mock_probe_fail = MagicMock()
        mock_probe_fail.available = False
        mock_probe_ok = MagicMock()
        mock_probe_ok.available = True

        def which_side_effect(name):
            if name == "curl":
                return "/usr/bin/curl"
            return None

        with patch("harness.drivers.cursor.CursorDriver") as MockDriver, \
             patch("harness.commands.install.shutil.which", side_effect=which_side_effect):
            instance = MockDriver.return_value
            instance.probe.side_effect = [mock_probe_fail, mock_probe_ok]

            from harness.commands.install import _probe_ides_force
            result = _probe_ides_force({"cursor": True, "codex": False})

        assert result["cursor"] is True
        mock_cli.assert_called_once()

    @patch("harness.commands.install.shutil.which", return_value=None)
    def test_cursor_missing_skipped(self, mock_which):
        from harness.commands.install import _probe_ides_force
        result = _probe_ides_force({"cursor": False, "codex": False})
        assert result["cursor"] is False


class TestI18nForceKeys:
    """Ensure force-related i18n keys exist in both catalogs."""

    def test_en_has_force_keys(self):
        from harness.i18n.en import MESSAGES
        assert "install.force_retry" in MESSAGES
        assert "install.force_hint" in MESSAGES

    def test_zh_has_force_keys(self):
        from harness.i18n.zh import MESSAGES
        assert "install.force_retry" in MESSAGES
        assert "install.force_hint" in MESSAGES
