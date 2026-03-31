"""DriverResolver tests — probe-based availability."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from harness.core.config import HarnessConfig
from harness.drivers.cursor import DriverProbe as CursorProbe
from harness.drivers.codex import DriverProbe as CodexProbe
from harness.drivers.resolver import DriverResolver


def _make_config(default: str = "auto", *, models: dict | None = None) -> HarnessConfig:
    data: dict = {"drivers": {"default": default}}
    if models is not None:
        data["models"] = models
    return HarnessConfig.model_validate(data)


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


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolve_model_uses_three_level_fallback(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=True, version="1.0")
    cursor_inst.name = "cursor"

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")
    codex_inst.name = "codex"

    cfg = _make_config(models={
        "default": "gpt-4o",
        "driver_defaults": {"codex": "o3"},
        "role_overrides": {"planner": "o3-pro"},
    })
    resolver = DriverResolver(cfg)

    # per-role override 最高优先
    assert resolver.resolve_model("planner") == "o3-pro"
    # per-driver default 次之（evaluator 用 codex）
    assert resolver.resolve_model("evaluator") == "o3"
    # global default 兜底（builder 用 cursor，无 driver_default）
    assert resolver.resolve_model("builder") == "gpt-4o"


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolve_model_empty_when_no_config(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=True, version="1.0")
    cursor_inst.name = "cursor"

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")
    codex_inst.name = "codex"

    resolver = DriverResolver(_make_config())
    # 无配置时返回空字符串（使用 IDE 默认模型）
    assert resolver.resolve_model("planner") == ""


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolve_model_zero_config_all_known_roles(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    """零配置时，所有已知角色通过 resolver 均返回空字符串。"""
    from harness.core.config import KNOWN_MODEL_ROLES

    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=True, version="1.0")
    cursor_inst.name = "cursor"

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")
    codex_inst.name = "codex"

    resolver = DriverResolver(_make_config())
    for role in KNOWN_MODEL_ROLES:
        assert resolver.resolve_model(role) == "", f"role={role} should return empty"


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolve_model_role_override_with_driver_routing(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    """role_overrides 正确覆盖，即使 driver 路由将角色分配到不同 driver。"""
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=True, version="1.0")
    cursor_inst.name = "cursor"

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")
    codex_inst.name = "codex"

    cfg = _make_config(models={
        "default": "",
        "driver_defaults": {"codex": "o3"},
        "role_overrides": {"builder": "claude-sonnet-4-20250514"},
    })
    resolver = DriverResolver(cfg)

    # builder 走 cursor（auto 模式），但 role_overrides 优先
    assert resolver.resolve_model("builder") == "claude-sonnet-4-20250514"
    # evaluator 走 codex，命中 driver_defaults
    assert resolver.resolve_model("evaluator") == "o3"
    # reflector 走 codex，命中 driver_defaults
    assert resolver.resolve_model("reflector") == "o3"


@patch("harness.drivers.resolver.CursorDriver")
@patch("harness.drivers.resolver.CodexDriver")
def test_resolve_model_driver_default_only(
    MockCodex: Mock, MockCursor: Mock,
) -> None:
    """仅配置 driver_defaults 时，按角色实际 driver 正确分流。"""
    cursor_inst = MockCursor.return_value
    cursor_inst.is_available.return_value = True
    cursor_inst.probe.return_value = CursorProbe(available=True, version="1.0")
    cursor_inst.name = "cursor"

    codex_inst = MockCodex.return_value
    codex_inst.is_available.return_value = True
    codex_inst.probe.return_value = CodexProbe(available=True, version="0.5")
    codex_inst.name = "codex"

    cfg = _make_config(models={
        "driver_defaults": {"codex": "o3", "cursor": "claude-sonnet-4-20250514"},
    })
    resolver = DriverResolver(cfg)

    # auto 模式: builder → cursor, 其他 → codex
    assert resolver.resolve_model("builder") == "claude-sonnet-4-20250514"
    assert resolver.resolve_model("planner") == "o3"
    assert resolver.resolve_model("evaluator") == "o3"
