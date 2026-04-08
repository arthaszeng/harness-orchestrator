"""Shared test fixtures for harness-flow test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner


@pytest.fixture()
def capture_echo():
    """Fixture that captures typer.echo output (excluding err=True)."""
    lines: list[str] = []
    original_echo = typer.echo

    def _mock_echo(message=None, **kwargs):
        if kwargs.get("err"):
            return
        if message is not None:
            lines.append(str(message))

    typer.echo = _mock_echo
    yield lines
    typer.echo = original_echo


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Provide a fresh Typer CLI test runner."""
    return CliRunner()


@pytest.fixture()
def harness_project(tmp_path: Path) -> Path:
    """Create a minimal harness project directory with config.toml.

    Returns the project root path (tmp_path) with .harness-flow/config.toml
    and .harness-flow/tasks/ already created.
    """
    agents_dir = tmp_path / ".harness-flow"
    agents_dir.mkdir()
    (agents_dir / "tasks").mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test-project"\nlang = "en"\n\n'
        '[ci]\ncommand = "./scripts/ci.sh"\n\n'
        "[workflow]\ntrunk_branch = \"main\"\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def task_dir(harness_project: Path) -> Path:
    """Create a minimal task directory inside a harness project.

    Returns the task-001 directory path.
    """
    td = harness_project / ".harness-flow" / "tasks" / "task-001"
    td.mkdir(parents=True, exist_ok=True)
    return td
