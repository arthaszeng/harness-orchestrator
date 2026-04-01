"""Tests for harness update command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import typer

from harness.commands.update import (
    _get_latest_version,
    _migrate_config,
    run_update,
)


class TestGetLatestVersion:
    def test_parses_version_from_pip_output(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "harness-flow (2.3.0)\n"
        with patch("harness.commands.update.subprocess.run", return_value=mock_result):
            assert _get_latest_version() == "2.3.0"

    def test_returns_none_on_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("harness.commands.update.subprocess.run", return_value=mock_result):
            assert _get_latest_version() is None

    def test_returns_none_on_timeout(self):
        with patch("harness.commands.update.subprocess.run", side_effect=Exception("timeout")):
            assert _get_latest_version() is None


class TestMigrateConfig:
    def test_no_config_returns_zero(self, tmp_path: Path):
        assert _migrate_config(tmp_path) == 0

    def test_valid_config_reports_ok(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = "make test"\n'
            '[workflow]\nmode = "orchestrator"\ntrunk_branch = "main"\n'
        )
        assert _migrate_config(tmp_path) == 0

    def test_workflow_without_legacy_keys_ok(self, tmp_path: Path):
        """Workflow section without removed orchestrator keys is valid."""
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = "make test"\n'
            '[workflow]\nmax_iterations = 3\n'
        )
        assert _migrate_config(tmp_path) == 0

    def test_missing_sections_warns(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text('[drivers]\ndefault = "auto"\n')
        warnings = _migrate_config(tmp_path)
        assert warnings >= 2

    def test_invalid_toml_returns_warning(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text("this is not valid toml [[[")
        assert _migrate_config(tmp_path) == 1


class TestRunUpdate:
    def test_check_mode_up_to_date(self):
        with patch("harness.commands.update._get_latest_version") as mock_latest:
            from harness import __version__
            mock_latest.return_value = __version__
            with pytest.raises(typer.Exit) as exc_info:
                run_update(check=True)
            assert exc_info.value.exit_code == 0

    def test_check_mode_new_version_available(self):
        with patch("harness.commands.update._get_latest_version", return_value="99.0.0"):
            with pytest.raises(typer.Exit) as exc_info:
                run_update(check=True)
            assert exc_info.value.exit_code == 0

    def test_check_mode_pypi_unreachable(self):
        with patch("harness.commands.update._get_latest_version", return_value=None):
            with pytest.raises(typer.Exit) as exc_info:
                run_update(check=True)
            assert exc_info.value.exit_code == 1

    def test_up_to_date_skips_install(self):
        """When already at latest version, run_install should NOT be called."""
        from harness import __version__
        with (
            patch("harness.commands.update._get_latest_version", return_value=__version__),
            patch("harness.commands.update._migrate_config", return_value=0),
            patch("harness.commands.update.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            with patch.dict("sys.modules", {"harness.commands.install": MagicMock()}):
                import harness.commands.install as mock_install_mod
                with patch.object(mock_install_mod, "run_install", create=True) as mock_install:
                    run_update(check=False, force=False)
                    mock_install.assert_not_called()

    def test_upgrade_runs_install(self):
        """After a successful pip upgrade, run_install SHOULD be called."""
        with (
            patch("harness.commands.update._get_latest_version", return_value="99.0.0"),
            patch("harness.commands.update._pip_upgrade", return_value=True),
            patch("harness.commands.update._migrate_config", return_value=0),
            patch("harness.commands.update.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            mock_run_install = MagicMock()
            with patch("harness.commands.install.run_install", mock_run_install, create=True):
                run_update(check=False, force=False)
            mock_run_install.assert_called_once_with(force=True, lang=None)

    def test_force_runs_install_when_up_to_date(self):
        """With --force, run_install should be called even when already at latest."""
        from harness import __version__
        with (
            patch("harness.commands.update._get_latest_version", return_value=__version__),
            patch("harness.commands.update._migrate_config", return_value=0),
            patch("harness.commands.update.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            mock_run_install = MagicMock()
            with patch("harness.commands.install.run_install", mock_run_install, create=True):
                run_update(check=False, force=True)
            mock_run_install.assert_called_once_with(force=True, lang=None)

    def test_pypi_unreachable_skips_install_runs_migration(self):
        """When PyPI is unreachable (non-check mode), skip install but run config migration."""
        with (
            patch("harness.commands.update._get_latest_version", return_value=None),
            patch("harness.commands.update._migrate_config", return_value=0) as mock_migrate,
            patch("harness.commands.update.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            with patch.dict("sys.modules", {"harness.commands.install": MagicMock()}):
                import harness.commands.install as mock_install_mod
                with patch.object(mock_install_mod, "run_install", create=True) as mock_install:
                    run_update(check=False, force=False)
                    mock_install.assert_not_called()
            mock_migrate.assert_called_once()

    def test_pip_upgrade_failure_does_not_install(self):
        """When pip upgrade fails, run_install should NOT be called and exit with code 1."""
        with (
            patch("harness.commands.update._get_latest_version", return_value="99.0.0"),
            patch("harness.commands.update._pip_upgrade", return_value=False),
        ):
            with patch.dict("sys.modules", {"harness.commands.install": MagicMock()}):
                import harness.commands.install as mock_install_mod
                with patch.object(mock_install_mod, "run_install", create=True) as mock_install:
                    with pytest.raises(typer.Exit) as exc_info:
                        run_update(check=False, force=False)
                    assert exc_info.value.exit_code == 1
                    mock_install.assert_not_called()
