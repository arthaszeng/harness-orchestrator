"""Tests for harness init command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import jinja2
import pytest
import typer

from harness.commands.init import (
    _GITIGNORE_RULES,
    _load_template,
    _prompt_choice,
    _step_ci_command,
    _step_evaluator_model,
    _step_language,
    _step_memverse,
    _update_gitignore,
    run_init,
    validate_model_name,
)
from harness.core.model_selection import detect_cursor_recent_models
from harness.core.scanner import ProjectScan
from harness.i18n import set_lang


class TestLoadTemplate:
    def test_loads_known_template(self):
        tmpl = _load_template("config.toml.j2")
        assert isinstance(tmpl, jinja2.Template)
        src = tmpl.render(project_name="x", description="", lang="en", ci_command="make test")
        assert 'name = "x"' in src
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


class TestValidateModelName:
    def test_inherit_is_valid(self):
        assert validate_model_name("inherit") is True

    def test_simple_model_name(self):
        assert validate_model_name("gpt-4.1") is True

    def test_complex_model_name(self):
        assert validate_model_name("gpt-5.4-high") is True

    def test_claude_model(self):
        assert validate_model_name("claude-4.6-opus") is True

    def test_short_model(self):
        assert validate_model_name("o3") is True

    def test_empty_string_invalid(self):
        assert validate_model_name("") is False

    def test_starts_with_digit_invalid(self):
        assert validate_model_name("4gpt") is False

    def test_spaces_invalid(self):
        assert validate_model_name("gpt 4") is False

    def test_special_chars_invalid(self):
        assert validate_model_name("model@v2") is False

    def test_underscore_valid(self):
        assert validate_model_name("my_model") is True

    def test_slash_invalid(self):
        assert validate_model_name("org/model") is False


class TestDetectCursorRecentModels:
    def test_returns_empty_when_no_db(self):
        with patch("harness.core.model_selection._cursor_state_db_path", return_value=None):
            assert detect_cursor_recent_models() == []

    def test_returns_empty_on_sql_error(self):
        with patch("harness.core.model_selection._cursor_state_db_path", return_value=MagicMock(exists=lambda: True)):
            with patch("harness.core.model_selection.sqlite3.connect", side_effect=OSError("boom")):
                assert detect_cursor_recent_models() == []

    def test_reads_recent_models_from_sqlite(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
        conn.execute(
            "INSERT INTO ItemTable(key, value) VALUES (?, ?)",
            ("cursor/lastSingleModelPreference", '{"composer":"claude-4.6-opus-high-thinking"}'),
        )
        conn.execute(
            "INSERT INTO ItemTable(key, value) VALUES (?, ?)",
            ("cursor/bestOfNEnsemblePreferences", '{"3":["claude-4.6-opus-high-thinking","gpt-5.4-high","o3"]}'),
        )
        conn.commit()
        conn.close()

        with patch("harness.core.model_selection._cursor_state_db_path", return_value=db_path):
            assert detect_cursor_recent_models() == [
                "claude-4.6-opus-high-thinking",
                "gpt-5.4-high",
                "o3",
            ]

    def test_reads_recent_models_from_sqlite_bytes(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
        conn.execute(
            "INSERT INTO ItemTable(key, value) VALUES (?, ?)",
            ("cursor/lastSingleModelPreference", b'{"composer":"gpt-5.4-high"}'),
        )
        conn.commit()
        conn.close()

        with patch("harness.core.model_selection._cursor_state_db_path", return_value=db_path):
            assert detect_cursor_recent_models() == ["gpt-5.4-high"]


class TestStepEvaluatorModel:
    def test_choice_1_returns_inherit(self):
        with patch("harness.commands.init.detect_cursor_recent_models", return_value=[]):
            with patch("harness.commands.init.typer.prompt", return_value="1"):
                assert _step_evaluator_model() == "inherit"

    def test_choice_recent_model(self):
        with patch("harness.commands.init.detect_cursor_recent_models", return_value=["gpt-4.1"]):
            with patch("harness.commands.init.typer.prompt", return_value="2"):
                assert _step_evaluator_model() == "gpt-4.1"

    def test_custom_input_valid(self):
        with patch("harness.commands.init.detect_cursor_recent_models", return_value=[]):
            with patch(
                "harness.commands.init.typer.prompt",
                side_effect=["2", "my-custom-model"],
            ):
                assert _step_evaluator_model() == "my-custom-model"

    def test_custom_input_invalid_then_valid(self):
        with patch("harness.commands.init.detect_cursor_recent_models", return_value=[]):
            with patch(
                "harness.commands.init.typer.prompt",
                side_effect=["2", "", "gpt-4.1"],
            ):
                assert _step_evaluator_model() == "gpt-4.1"

    def test_recent_models_appear_as_options(self):
        with patch(
            "harness.commands.init.detect_cursor_recent_models",
            return_value=["claude-4.6-opus-high-thinking", "gpt-5.4-high"],
        ):
            with patch("harness.commands.init.typer.prompt", return_value="3"):
                assert _step_evaluator_model() == "gpt-5.4-high"


class TestUpdateGitignore:
    def test_creates_new_gitignore_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        _update_gitignore(tmp_path)
        gi = tmp_path / ".gitignore"
        assert gi.exists()
        text = gi.read_text(encoding="utf-8")
        for rule in _GITIGNORE_RULES:
            assert rule in text
        assert "# harness-flow — local tooling artifacts" in text

    def test_appends_to_existing_gitignore(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        _update_gitignore(tmp_path)
        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert "node_modules/" in text
        for rule in _GITIGNORE_RULES:
            assert rule in text

    def test_skips_when_all_rules_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        original = "foo\n" + "\n".join(_GITIGNORE_RULES) + "\nbar\n"
        (tmp_path / ".gitignore").write_text(original, encoding="utf-8")
        _update_gitignore(tmp_path)
        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == original

    def test_incremental_append_adds_missing_rules(self, tmp_path, monkeypatch):
        """Old .gitignore with only some rules gets remaining rules added."""
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        old_content = "# harness-flow — local tooling artifacts (not version-controlled)\n.harness-flow/\n"
        (tmp_path / ".gitignore").write_text(old_content, encoding="utf-8")
        _update_gitignore(tmp_path)
        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        for rule in _GITIGNORE_RULES:
            assert rule in text

    def test_idempotent_on_repeated_calls(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        _update_gitignore(tmp_path)
        first = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        _update_gitignore(tmp_path)
        second = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert first == second


class TestRunInitNonInteractive:
    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_non_interactive_uses_scanner_when_no_ci_flag(self, _mock_gen, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        run_init(non_interactive=True)
        body = (tmp_path / ".harness-flow" / "config.toml").read_text(encoding="utf-8")
        assert "python -m pytest" in body

    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_creates_agents_layout_and_config(self, mock_gen, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        run_init(
            name="alpha-project",
            ci_command="pytest -q",
            non_interactive=True,
        )
        agents = tmp_path / ".harness-flow"
        assert agents.is_dir()
        assert (agents / "tasks").is_dir()
        assert (agents / "archive").is_dir()
        cfg = agents / "config.toml"
        assert cfg.exists()
        body = cfg.read_text(encoding="utf-8")
        assert 'name = "alpha-project"' in body
        assert 'command = "pytest -q"' in body
        assert 'evaluator_model = "inherit"' in body
        vision = agents / "vision.md"
        assert vision.exists()
        vision_body = vision.read_text(encoding="utf-8")
        assert "## Problem / User" in vision_body
        assert "## North Star" in vision_body
        assert "## Success Signals" in vision_body
        assert "## Non-Goals / Constraints" in vision_body
        assert "## Technical Constraints" not in vision_body
        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs.get("lang") == "en"
        logs = capsys.readouterr()
        rendered = f"{logs.out}\n{logs.err}"
        assert "/harness-plan" in rendered
        assert "git add .gitignore && git commit" in rendered

    def test_loads_business_oriented_zh_vision_template(self):
        tmpl = _load_template("vision.zh.md.j2")
        content = tmpl.render(project_name="alpha-project")
        assert "## Problem / User" in content
        assert "## North Star" in content
        assert "## Success Signals" in content
        assert "## Non-Goals / Constraints" in content
        assert "## 技术约束" not in content

    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_updates_gitignore(self, _mock_gen, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        run_init(non_interactive=True)
        gi = tmp_path / ".gitignore"
        assert gi.exists()
        text = gi.read_text(encoding="utf-8")
        for rule in _GITIGNORE_RULES:
            assert rule in text

    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_auto_commit_flag_invokes_helper(self, _mock_gen, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        with patch("harness.commands.init._auto_commit_init_artifacts") as auto_commit:
            run_init(non_interactive=True, auto_commit=True)
        auto_commit.assert_called_once()


class TestRunInitReinit:
    """With --force and existing config, init skips wizard and regenerates artifacts."""

    @patch("harness.native.skill_gen.generate_native_artifacts", return_value=42)
    def test_reinit_skips_wizard_regenerates(self, mock_gen, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir(parents=True)
        (agents / "config.toml").write_text(
            '[project]\nname = "existing"\nlang = "zh"\n'
            '[ci]\ncommand = "make test"\n'
            '[workflow]\ntrunk_branch = "main"\n',
            encoding="utf-8",
        )
        run_init(force=True)
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("force") is True
        logs = capsys.readouterr()
        rendered = f"{logs.out}\n{logs.err}"
        assert "/harness-plan" in rendered

    @patch("harness.native.skill_gen.generate_native_artifacts", return_value=10)
    def test_reinit_updates_gitignore(self, _mock_gen, monkeypatch, tmp_path):
        """harness init --force should also update .gitignore with all rules."""
        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir(parents=True)
        (agents / "config.toml").write_text(
            '[project]\nname = "x"\nlang = "en"\n'
            '[ci]\ncommand = "make test"\n'
            '[workflow]\ntrunk_branch = "main"\n',
            encoding="utf-8",
        )
        run_init(force=True)
        gi = tmp_path / ".gitignore"
        assert gi.exists()
        text = gi.read_text(encoding="utf-8")
        for rule in _GITIGNORE_RULES:
            assert rule in text

    @patch("harness.native.skill_gen.generate_native_artifacts", return_value=10)
    def test_reinit_uses_config_lang(self, mock_gen, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir(parents=True)
        (agents / "config.toml").write_text(
            '[project]\nname = "zh-proj"\nlang = "zh"\n'
            '[ci]\ncommand = "make test"\n'
            '[workflow]\ntrunk_branch = "main"\n',
            encoding="utf-8",
        )
        run_init(force=True)
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("lang") == "zh"

    def test_reinit_bad_config_exits_with_error(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir(parents=True)
        (agents / "config.toml").write_text("this is not valid toml [[[", encoding="utf-8")
        with pytest.raises(typer.Exit) as exc_info:
            run_init(force=True)
        assert exc_info.value.exit_code == 1

    def test_no_force_config_exists_prompts_overwrite(self, monkeypatch, tmp_path):
        """Without --force, existing config triggers confirm prompt; declining exits."""
        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir(parents=True)
        (agents / "config.toml").write_text(
            '[project]\nname = "x"\n[ci]\ncommand = "t"\n',
            encoding="utf-8",
        )
        with patch("harness.commands.init.typer.confirm", return_value=False):
            with pytest.raises(typer.Exit) as exc_info:
                run_init()
            assert exc_info.value.exit_code == 0

    def test_force_no_config_runs_wizard(self, monkeypatch, tmp_path):
        """--force without existing config falls through to normal wizard."""
        monkeypatch.chdir(tmp_path)
        set_lang("en")
        with patch("harness.native.skill_gen.generate_native_artifacts"):
            run_init(non_interactive=True, force=True)
        assert (tmp_path / ".harness-flow" / "config.toml").exists()

    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_no_force_config_exists_confirm_yes_overwrites(self, _mock_gen, monkeypatch, tmp_path):
        """Confirming overwrite re-runs the wizard and rewrites config."""
        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir(parents=True)
        (agents / "config.toml").write_text(
            '[project]\nname = "stale-proj"\n[ci]\ncommand = "t"\n',
            encoding="utf-8",
        )
        with patch("harness.commands.init.typer.confirm", return_value=True):
            set_lang("en")
            run_init(non_interactive=True)
        body = (agents / "config.toml").read_text(encoding="utf-8")
        assert 'name = "stale-proj"' not in body

    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_non_interactive_config_exists_skips_confirm(self, _mock_gen, monkeypatch, tmp_path):
        """non_interactive + existing config skips confirm prompt and overwrites."""
        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir(parents=True)
        (agents / "config.toml").write_text(
            '[project]\nname = "stale"\n[ci]\ncommand = "x"\n',
            encoding="utf-8",
        )
        set_lang("en")
        run_init(non_interactive=True)
        body = (agents / "config.toml").read_text(encoding="utf-8")
        assert "stale" not in body

    def test_init_blocked_in_worktree_without_force(self, monkeypatch, tmp_path):
        """init without --force in a worktree exits with code 1."""
        from click.exceptions import Exit as ClickExit

        from harness.core.worktree import WorktreeInfo

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "harness.core.worktree.detect_worktree",
            lambda _cwd: WorktreeInfo(
                common_dir=tmp_path / ".git",
                git_dir=tmp_path / ".git/worktrees/x",
                branch="agent/task-100",
            ),
        )
        set_lang("en")
        with pytest.raises(ClickExit) as exc_info:
            run_init(non_interactive=True)
        assert exc_info.value.exit_code == 1

    @patch("harness.native.skill_gen.generate_native_artifacts")
    def test_init_force_allowed_in_worktree(self, _mock_gen, monkeypatch, tmp_path):
        """init --force in a worktree should work (reinit / bootstrap)."""
        from harness.core.worktree import WorktreeInfo

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "harness.core.worktree.detect_worktree",
            lambda _cwd: WorktreeInfo(
                common_dir=tmp_path / ".git",
                git_dir=tmp_path / ".git/worktrees/x",
                branch="agent/task-100",
            ),
        )
        set_lang("en")
        run_init(non_interactive=True, force=True)
        assert (tmp_path / ".harness-flow" / "config.toml").exists()

    def test_init_no_worktree_unaffected(self, monkeypatch, tmp_path):
        """When not in a worktree, detect_worktree returns None and init proceeds."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("harness.core.worktree.detect_worktree", lambda _cwd: None)
        set_lang("en")
        with patch("harness.native.skill_gen.generate_native_artifacts"):
            run_init(non_interactive=True)
        assert (tmp_path / ".harness-flow" / "config.toml").exists()
