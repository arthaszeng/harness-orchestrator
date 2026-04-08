"""Tests for harness diff-stat command."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import typer

from harness.commands.diff_stat import _classify_file, run_diff_stat


class TestClassifyFile:
    def test_python_code(self):
        assert _classify_file("src/harness/cli.py") == "code"

    def test_typescript(self):
        assert _classify_file("src/app.tsx") == "code"

    def test_test_file_in_tests_dir(self):
        assert _classify_file("tests/test_cli.py") == "test"

    def test_test_file_by_name(self):
        assert _classify_file("src/test_utils.py") == "test"

    def test_markdown_doc(self):
        assert _classify_file("README.md") == "doc"

    def test_other_file(self):
        assert _classify_file("pyproject.toml") == "other"

    def test_js_test_in_tests_dir(self):
        assert _classify_file("__tests__/app.test.js") == "test"

    def test_config_json(self):
        assert _classify_file("tsconfig.json") == "other"


class TestRunDiffStat:
    def test_with_changes(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/foo.py\ntests/test_foo.py\nREADME.md\npyproject.toml\n"
        monkeypatch.setattr("harness.commands.diff_stat.run_git", lambda *a, **kw: mock_result)

        out = _capture(lambda: run_diff_stat(as_json=True))
        data = json.loads(out)
        assert data["total_files"] == 4
        assert data["code_files"] == 1
        assert data["test_files"] == 1
        assert data["doc_files"] == 1
        assert data["other_files"] == 1
        assert data["has_md_changes"] is True
        assert data["trunk_branch"] == "main"

    def test_no_changes(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        monkeypatch.setattr("harness.commands.diff_stat.run_git", lambda *a, **kw: mock_result)

        out = _capture(lambda: run_diff_stat(as_json=True))
        data = json.loads(out)
        assert data["total_files"] == 0
        assert data["has_md_changes"] is False

    def test_only_md_changes(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CHANGELOG.md\ndocs/api.md\n"
        monkeypatch.setattr("harness.commands.diff_stat.run_git", lambda *a, **kw: mock_result)

        out = _capture(lambda: run_diff_stat(as_json=True))
        data = json.loads(out)
        assert data["code_files"] == 0
        assert data["doc_files"] == 2
        assert data["has_md_changes"] is True

    def test_git_failure_exits_1(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "fatal: not a git repository"
        monkeypatch.setattr("harness.commands.diff_stat.run_git", lambda *a, **kw: mock_result)

        with pytest.raises(typer.Exit) as exc_info:
            run_diff_stat(as_json=True)
        assert exc_info.value.exit_code == 1

    def test_mixed_changes(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "src/harness/commands/task_info.py\n"
            "src/harness/commands/diff_stat.py\n"
            "src/harness/cli.py\n"
            "tests/test_task_info.py\n"
            "tests/test_diff_stat.py\n"
            "README.md\n"
            ".harness-flow/config.toml\n"
        )
        monkeypatch.setattr("harness.commands.diff_stat.run_git", lambda *a, **kw: mock_result)

        out = _capture(lambda: run_diff_stat(as_json=True))
        data = json.loads(out)
        assert data["total_files"] == 7
        assert data["code_files"] == 3
        assert data["test_files"] == 2
        assert data["doc_files"] == 1
        assert data["other_files"] == 1


def _capture(fn) -> str:
    """Capture typer.echo output from a function call."""
    lines: list[str] = []
    original_echo = typer.echo

    def _mock_echo(message=None, **kwargs):
        if kwargs.get("err"):
            return
        if message is not None:
            lines.append(str(message))

    typer.echo = _mock_echo
    try:
        fn()
    finally:
        typer.echo = original_echo
    return "\n".join(lines)
