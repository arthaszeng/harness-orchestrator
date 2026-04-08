"""Shared test utilities for harness tests."""

from __future__ import annotations

import typer
import pytest


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
