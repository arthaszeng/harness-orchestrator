"""Tests for harness update command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import typer

from harness.commands.update import (
    _get_latest_version,
    _migrate_config,
    _pip_upgrade,
    run_update,
)


class TestGetLatestVersion:
    def test_http_preferred(self):
        with patch("harness.commands.update._get_latest_version_http", return_value="5.0.0"):
            assert _get_latest_version() == "5.0.0"

    def test_fallback_to_pip_when_http_fails(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "harness-flow (2.3.0)\n"
        with (
            patch("harness.commands.update._get_latest_version_http", return_value=None),
            patch("harness.commands.update.subprocess.run", return_value=mock_result),
        ):
            assert _get_latest_version() == "2.3.0"

    def test_returns_none_when_both_fail(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with (
            patch("harness.commands.update._get_latest_version_http", return_value=None),
            patch("harness.commands.update.subprocess.run", return_value=mock_result),
        ):
            assert _get_latest_version() is None

    def test_returns_none_on_timeout(self):
        with (
            patch("harness.commands.update._get_latest_version_http", return_value=None),
            patch("harness.commands.update.subprocess.run", side_effect=Exception("timeout")),
        ):
            assert _get_latest_version() is None


class TestMigrateConfig:
    def test_no_config_returns_zero(self, tmp_path: Path):
        assert _migrate_config(tmp_path) == 0

    def test_valid_config_reports_ok(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = "make test"\n'
            '[workflow]\nmode = "orchestrator"\ntrunk_branch = "main"\n'
        )
        assert _migrate_config(tmp_path) == 0

    def test_workflow_without_legacy_keys_ok(self, tmp_path: Path):
        """Workflow section without removed orchestrator keys is valid."""
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = "make test"\n'
            '[workflow]\nmax_iterations = 3\n'
        )
        assert _migrate_config(tmp_path) == 0

    def test_missing_sections_warns(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text('[drivers]\ndefault = "auto"\n')
        warnings = _migrate_config(tmp_path)
        assert warnings >= 2

    def test_invalid_toml_returns_warning(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text("this is not valid toml [[[")
        assert _migrate_config(tmp_path) == 1

    def test_deprecated_adversarial_model_warns(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text(
            '[project]\nname = "t"\n[ci]\ncommand = "t"\n'
            '[workflow]\ntrunk_branch = "main"\n'
            '[native]\nadversarial_model = "gpt-4.1"\n'
        )
        warnings = _migrate_config(tmp_path)
        assert warnings >= 1


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

    def test_up_to_date_skips_artifact_generation(self):
        """When already at latest version, generate_native_artifacts should NOT be called."""
        from harness import __version__
        mock_gen = MagicMock(return_value=10)
        with (
            patch("harness.commands.update._get_latest_version", return_value=__version__),
            patch("harness.commands.update._migrate_config", return_value=0),
            patch("harness.commands.update.Path") as mock_path_cls,
            patch("harness.native.skill_gen.generate_native_artifacts", mock_gen),
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            run_update(check=False, force=False)
        mock_gen.assert_not_called()

    def test_upgrade_does_not_generate_artifacts_and_shows_easter_egg(self, capsys):
        """After a successful pip upgrade, update should not write project artifacts."""
        mock_gen = MagicMock(return_value=10)
        with (
            patch("harness.commands.update._get_latest_version", return_value="99.0.0"),
            patch("harness.commands.update._pip_upgrade", return_value=True),
            patch("harness.commands.update._migrate_config", return_value=0),
            patch("harness.commands.update.Path") as mock_path_cls,
            patch("harness.native.skill_gen.generate_native_artifacts", mock_gen),
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            run_update(check=False, force=False)
        mock_gen.assert_not_called()
        logs = capsys.readouterr()
        rendered = f"{logs.out}\n{logs.err}"
        assert "init --force" in rendered

    def test_force_no_longer_runs_artifact_generation_when_up_to_date(self, capsys):
        """With --force, update still should not write project artifacts."""
        from harness import __version__
        mock_gen = MagicMock(return_value=10)
        with (
            patch("harness.commands.update._get_latest_version", return_value=__version__),
            patch("harness.commands.update._migrate_config", return_value=0),
            patch("harness.commands.update.Path") as mock_path_cls,
            patch("harness.native.skill_gen.generate_native_artifacts", mock_gen),
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            run_update(check=False, force=True)
        mock_gen.assert_not_called()
        logs = capsys.readouterr()
        rendered = f"{logs.out}\n{logs.err}"
        assert "init --force" in rendered

    def test_pypi_unreachable_skips_generation_runs_migration(self):
        """When PyPI is unreachable (non-check mode), skip generation but run config migration."""
        with (
            patch("harness.commands.update._get_latest_version", return_value=None),
            patch("harness.commands.update._migrate_config", return_value=0) as mock_migrate,
            patch("harness.commands.update.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            run_update(check=False, force=False)
            mock_migrate.assert_called_once()

    def test_force_takes_priority_over_unreachable_notice(self, capsys):
        """When --force is set, reminder message takes priority over unreachable notice."""
        with (
            patch("harness.commands.update._get_latest_version", return_value=None),
            patch("harness.commands.update._migrate_config", return_value=0),
            patch("harness.commands.update.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value = Path("/fake")
            run_update(check=False, force=True)
        logs = capsys.readouterr()
        rendered = f"{logs.out}\n{logs.err}"
        assert "init --force" in rendered

    def test_pip_upgrade_failure_does_not_generate(self):
        """When pip upgrade fails, artifacts should NOT be generated and exit with code 1."""
        with (
            patch("harness.commands.update._get_latest_version", return_value="99.0.0"),
            patch("harness.commands.update._pip_upgrade", return_value=False),
        ):
            with pytest.raises(typer.Exit) as exc_info:
                run_update(check=False, force=False)
            assert exc_info.value.exit_code == 1


class TestPipUpgradeVerification:
    def test_retries_with_force_reinstall_when_version_not_updated(self):
        pip_ok = MagicMock(returncode=0, stdout="", stderr="")
        version_old = MagicMock(returncode=0, stdout="4.1.33\n", stderr="")
        force_ok = MagicMock(returncode=0, stdout="", stderr="")
        version_new = MagicMock(returncode=0, stdout="4.1.34\n", stderr="")
        with patch(
            "harness.commands.update.subprocess.run",
            side_effect=[pip_ok, version_old, force_ok, version_new],
        ):
            assert _pip_upgrade("4.1.34") is True

    def test_fails_when_version_still_mismatch_after_retry(self):
        pip_ok = MagicMock(returncode=0, stdout="", stderr="")
        version_old_1 = MagicMock(returncode=0, stdout="4.1.33\n", stderr="")
        force_ok = MagicMock(returncode=0, stdout="", stderr="")
        version_old_2 = MagicMock(returncode=0, stdout="4.1.33\n", stderr="")
        with patch(
            "harness.commands.update.subprocess.run",
            side_effect=[pip_ok, version_old_1, force_ok, version_old_2],
        ):
            assert _pip_upgrade("4.1.34") is False
