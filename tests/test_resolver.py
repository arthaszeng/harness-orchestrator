"""DriverResolver tests — probe-based availability."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from harness.core.config import HarnessConfig
from harness.drivers.cursor import DriverProbe as CursorProbe
from harness.drivers.codex import DriverProbe as CodexProbe
from harness.drivers.resolver import DriverResolver


def _make_config(default: str = "auto") -> HarnessConfig:
    return HarnessConfig.model_validate({"drivers": {"default": default}})


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolver_marks_cursor_unavailable_when_probe_fails(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=False, warnings=["not ready"])

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")

    resolver = DriverResolver(_make_config())
    assert resolver.available_drivers == {"cursor": False, "codex": True}


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolver_marks_codex_unavailable_when_probe_fails(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=True, version="1.0")

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=False, warnings=["not ready"])

    resolver = DriverResolver(_make_config())
    assert resolver.available_drivers == {"cursor": True, "codex": False}


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolver_both_available_after_probe(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=True, version="1.0")

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")

    resolver = DriverResolver(_make_config())
    assert resolver.available_drivers == {"cursor": True, "codex": True}


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolver_raises_when_neither_functional(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=False)

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=False)

    resolver = DriverResolver(_make_config())
    with pytest.raises(RuntimeError, match="Neither"):
        resolver.resolve("planner")


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolver_falls_back_to_codex_when_cursor_probe_fails(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=False, warnings=["installing"])

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")

    resolver = DriverResolver(_make_config())
    driver = resolver.resolve("builder")
    assert driver is codex_inst


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolver_get_driver_by_name_respects_probe(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=False)

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")

    resolver = DriverResolver(_make_config())
    assert resolver.get_driver_by_name("cursor") is None
    assert resolver.get_driver_by_name("codex") is codex_inst


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolver_first_available_respects_probe(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=True, version="1.0")

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=False)

    resolver = DriverResolver(_make_config())
    assert resolver.first_available_driver() is cursor_inst
