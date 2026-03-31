"""init._ai_suggest_ci — advisor 路由下 resolve_model 与 driver.invoke(model=...) 透传。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from harness.commands.init import _ai_suggest_ci
from harness.core.scanner import ProjectScan
from harness.drivers.base import AgentResult


@patch("harness.commands.init.typer")
@patch("harness.drivers.resolver.DriverResolver")
def test_ai_suggest_ci_calls_resolve_model_advisor_and_passes_to_invoke(
    mock_resolver_cls, mock_typer, tmp_path: Path,
):
    mock_typer.echo = MagicMock()
    mock_typer.confirm = MagicMock(return_value=True)

    resolver_inst = mock_resolver_cls.return_value
    driver = MagicMock()
    driver.invoke.return_value = AgentResult(
        success=True, output="pytest -q\n", exit_code=0,
    )
    resolver_inst.resolve.return_value = driver
    resolver_inst.resolve_model.return_value = "gpt-advisor"

    scan = ProjectScan()
    roles = {"advisor": "codex"}
    out = _ai_suggest_ci(tmp_path, {"codex": True}, scan, "codex", roles)

    resolver_inst.resolve.assert_called_with("advisor")
    resolver_inst.resolve_model.assert_called_with("advisor")
    driver.invoke.assert_called_once()
    assert driver.invoke.call_args.kwargs["model"] == "gpt-advisor"
    assert out == "pytest -q"


@patch("harness.commands.init.typer")
@patch("harness.drivers.resolver.DriverResolver")
def test_ai_suggest_ci_empty_advisor_model_passes_empty_string_to_invoke(
    mock_resolver_cls, mock_typer, tmp_path: Path,
):
    """空模型保持不写死非空 --model，invoke 收到空字符串由 driver 按 IDE 默认处理。"""
    mock_typer.echo = MagicMock()
    mock_typer.confirm = MagicMock(return_value=True)

    resolver_inst = mock_resolver_cls.return_value
    driver = MagicMock()
    driver.invoke.return_value = AgentResult(
        success=True, output="make test\n", exit_code=0,
    )
    resolver_inst.resolve.return_value = driver
    resolver_inst.resolve_model.return_value = ""

    scan = ProjectScan()
    roles = {"advisor": "codex"}
    out = _ai_suggest_ci(tmp_path, {"codex": True}, scan, "codex", roles)

    resolver_inst.resolve_model.assert_called_once_with("advisor")
    driver.invoke.assert_called_once()
    assert driver.invoke.call_args.kwargs["model"] == ""
    assert out == "make test"
