"""Tests for harness CLI entry point."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from harness.cli import app

runner = CliRunner()


class TestVersionOutput:
    def test_version_flag_contains_harness_flow(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "harness-flow" in result.output
        assert "harness-orchestrator" not in result.output

    def test_version_flag_short(self):
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "harness-flow" in result.output
        assert "harness-orchestrator" not in result.output


class TestHelpOutput:
    def test_help_lists_three_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "status" in result.output
        assert "update" in result.output

    def test_help_does_not_list_install(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        lines = result.output.lower().splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("install") and "completion" not in stripped:
                pytest.fail(f"'install' command found in help: {line}")
