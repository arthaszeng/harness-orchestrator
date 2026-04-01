"""WorkflowDeps Protocol 单元测试"""

from pathlib import Path
from unittest.mock import MagicMock

from harness.drivers.base import AgentResult
from harness.orchestrator.deps import CIResult, ProductionDeps, WorkflowDeps


def test_ci_result_dataclass():
    r = CIResult(verdict="PASS", feedback="ok")
    assert r.verdict == "PASS"
    assert r.exit_code == 0


def test_production_deps_implements_protocol():
    resolver = MagicMock()
    deps = ProductionDeps(resolver)
    assert isinstance(deps, WorkflowDeps)


def test_production_deps_invoke_agent():
    resolver = MagicMock()
    driver = MagicMock()
    driver.invoke.return_value = AgentResult(success=True, output="ok", exit_code=0)
    resolver.resolve.return_value = driver

    deps = ProductionDeps(resolver)
    result = deps.invoke_agent("planner", "harness-planner", "prompt", Path("/tmp"))

    driver.invoke.assert_called_once()
    assert result.success is True


def test_production_deps_uuid_format():
    resolver = MagicMock()
    deps = ProductionDeps(resolver)
    uid = deps.uuid()
    assert len(uid) == 8
    int(uid, 16)
