"""Tests for harness init command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import jinja2
import pytest
import typer

from harness.commands.init import (
    _load_template,
    _prompt_choice,
    _step_ci_command,
    _step_language,
    _step_memverse,
    _update_gitignore,
    run_init,
)
from harness.core.scanner import ProjectScan
from harness.i18n import set_lang


class TestLoadTemplate:
    def test_loads_known_template(self):
        tmpl = _load_template("config.toml.j2")
        assert isinstance(tmpl, jinja2.Template)
        src = tmpl.render(project_name="x", description="", lang="en", ci_command="make test")
        assert "name = \"x\"" in src
        assert "make test" in src

    def test_nonexistent_template_raises(self):
        with pytest.raises(FileNotFoundError):
            _load_template("does-not-exist-xyz.j2")


class TestPromptChoice:
    def test_valid_input_returns_one_based_index(self):
        with patch("harness.commands.init.typer.prompt", return_value="2"):
            with patch("harness.commands.init.typer.echo"):
                assert _prompt_choice("pick", 5, default=1) == 2

    def test_invalid_input_loops_until_valid(self):
        with patch(
            "harness.commands.init.typer.prompt",
            side_effect=["99", "0", "nan", "3"],
        ):
            mock_echo = MagicMock()
            with patch("harness.commands.init.typer.echo", mock_echo):
                assert _prompt_choice("pick", 3, default=1) == 3
        assert mock_echo.call_count == 3


class TestStepLanguage:
    def test_choice_1_returns_en(self):
        with patch("harness.commands.init.typer.echo"):
            with patch("harness.commands.init.typer.prompt", return_value="1"):
                assert _step_language() == "en"

    def test_choice_2_returns_zh(self):
        with patch("harness.commands.init.typer.echo"):
            with patch("harness.commands.init.typer.prompt", return_value="2"):
                assert _step_language() == "zh"


class TestStepCiCommand:
    def test_ci_override_returns_directly(self, tmp_path):
        assert _step_ci_command(tmp_path, ci_override="npm test") == "npm test"

    def test_with_suggestions_selects_command(self, tmp_path):
        scan = ProjectScan(
            suggested_commands=[
                ("pytest -q", "pytest"),
                ("make ci", "makefile"),
            ],
        )
        with patch("harness.commands.init.scan_project", return_value=scan):
            with patch("harness.commands.init.format_scan_report", return_value=[]):
                with patch("harness.commands.init.typer.echo"):
                    with patch(
                        "harness.commands.init.typer.prompt",
                        return_value="1",
                    ):
                        assert _step_ci_command(tmp_path) == "pytest -q"

    def test_with_suggestions_custom_index_prompts(self, tmp_path):
        scan = ProjectScan(suggested_commands=[("a", "d")])
        with patch("harness.commands.init.scan_project", return_value=scan):
            with patch("harness.commands.init.format_scan_report", return_value=[]):
                with patch("harness.commands.init.typer.echo"):
                    with patch(
                        "harness.commands.init.typer.prompt",
                        side_effect=["2", "my custom ci"],
                    ):
                        assert _step_ci_command(tmp_path) == "my custom ci"

    def test_no_suggestions_custom_flow(self, tmp_path):
        scan = ProjectScan(suggested_commands=[])
        with patch("harness.commands.init.scan_project", return_value=scan):
            with patch("harness.commands.init.format_scan_report", return_value=[]):
                with patch("harness.commands.init.typer.echo"):
                    with patch(
                        "harness.commands.init.typer.prompt",
                        side_effect=["1", "cargo test"],
                    ):
                        assert _step_ci_command(tmp_path) == "cargo test"

    def test_no_suggestions_skip_returns_empty(self, tmp_path):
        scan = ProjectScan(suggested_commands=[])
        with patch("harness.commands.init.scan_project", return_value=scan):
            with patch("harness.commands.init.format_scan_report", return_value=[]):
                with patch("harness.commands.init.typer.echo"):
                    with patch(
                        "harness.commands.init.typer.prompt",
                        return_value="2",
                    ):
                        assert _step_ci_command(tmp_path) == ""


class TestStepMemverse:
    def test_disable_returns_disabled(self, tmp_path):
        with patch("harness.commands.init.typer.echo"):
            with patch("harness.commands.init.typer.prompt", return_value="2"):
                assert _step_memverse(tmp_path) == (False, "")

    def test_enable_returns_domain(self, tmp_path):
        with patch("harness.commands.init.typer.echo"):
            with patch(
                "harness.commands.init.typer.prompt",
                side_effect=["1", "my-domain"],
            ):
                assert _step_memverse(tmp_path) == (True, "my-domain")


class TestUpdateGitignore:
    def test_creates_new_gitignore_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        _update_gitignore(tmp_path)
        gi = tmp_path / ".gitignore"
        assert gi.exists()
        text = gi.read_text(encoding="utf-8")
        assert ".agents/state.json" in text
        assert ".agents/.stop" in text
        assert "# harness — do not track runtime state" in text

    def test_appends_to_existing_gitignore(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        _update_gitignore(tmp_path)
        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert "node_modules/" in text
        assert ".agents/state.json" in text

    def test_skips_when_marker_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        original = "foo\n.agents/state.json\nbar\n"
        (tmp_path / ".gitignore").write_text(original, encoding="utf-8")
        _update_gitignore(tmp_path)
        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == original


class TestRunInitNonInteractive:
    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_creates_agents_layout_and_config(self, mock_gen, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        run_init(
            name="alpha-project",
            ci_command="pytest -q",
            non_interactive=True,
        )
        agents = tmp_path / ".agents"
        assert agents.is_dir()
        assert (agents / "tasks").is_dir()
        assert (agents / "archive").is_dir()
        cfg = agents / "config.toml"
        assert cfg.exists()
        body = cfg.read_text(encoding="utf-8")
        assert 'name = "alpha-project"' in body
        assert 'command = "pytest -q"' in body
        vision = agents / "vision.md"
        assert vision.exists()
        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs.get("lang") == "en"

    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_updates_gitignore(self, _mock_gen, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        run_init(non_interactive=True)
        gi = tmp_path / ".gitignore"
        assert gi.exists()
        assert ".agents/state.json" in gi.read_text(encoding="utf-8")


class TestRunInitDeclineOverwrite:
    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_raises_exit_zero_when_user_declines(
        self, mock_gen, monkeypatch, tmp_path,
    ):
        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".agents"
        agents.mkdir(parents=True)
        (agents / "config.toml").write_text("[project]\nname = old\n", encoding="utf-8")

        with patch("harness.commands.init.typer.confirm", return_value=False):
            with patch("harness.commands.init.typer.echo"):
                with pytest.raises(typer.Exit) as excinfo:
                    run_init(non_interactive=True)

        assert excinfo.value.exit_code == 0
        mock_gen.assert_not_called()

