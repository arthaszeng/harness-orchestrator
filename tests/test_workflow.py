"""workflow.py 集成测试 — mock drivers"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.core.config import HarnessConfig
from harness.core.state import StateMachine
from harness.drivers.base import AgentResult
from harness.drivers.resolver import DriverResolver
from harness.integrations.git_ops import DirtyWorktreeError, current_branch
from harness.orchestrator.workflow import _split_spec_contract, run_single_task


def _mock_driver(name: str) -> MagicMock:
    d = MagicMock()
    d.name = name
    return d


def test_split_spec_contract_with_marker():
    text = "# Spec\nsome spec content\n# Contract\n- [ ] item 1"
    spec, contract = _split_spec_contract(text)
    assert "# Spec" in spec
    assert "# Contract" in contract
    assert "item 1" in contract
    assert "# Contract" not in spec


def test_split_spec_contract_without_marker():
    text = "just some text without contract heading"
    spec, contract = _split_spec_contract(text)
    assert spec == text
    assert contract == text


def test_split_spec_contract_case_insensitive():
    text = "spec stuff\n# contract\n- deliverable"
    spec, contract = _split_spec_contract(text)
    assert "spec stuff" in spec
    assert "# contract" in contract


def _make_eval_output(score: float = 4.0) -> str:
    return f"""\
# Evaluation — Iteration 1

## 评分
| 维度 | 分数 | 说明 |
|------|------|------|
| completeness | {score} | ok |
| quality | {score} | ok |
| regression | {score} | ok |
| design | {score} | ok |

## 判定
PASS
"""


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "t@t.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "t@t.com",
    "HOME": str(Path.home()),
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, env=_GIT_ENV)


def _setup(tmp_path: Path) -> tuple[HarnessConfig, StateMachine, MagicMock]:
    """创建测试环境 — git repo 保持 clean 状态"""
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = ""\n',
        encoding="utf-8",
    )
    (agents_dir / "tasks").mkdir()

    _git(["init"], tmp_path)
    _git(["checkout", "-b", "main"], tmp_path)
    (tmp_path / "dummy.txt").write_text("init", encoding="utf-8")

    config = HarnessConfig.load(tmp_path)
    sm = StateMachine(tmp_path)
    sm.start_session("run")

    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)

    resolver = MagicMock(spec=DriverResolver)
    return config, sm, resolver


def test_single_task_pass_invokes_agent_with_resolver_model_per_role(tmp_path: Path):
    """run_single_task 传给各 role 的 model 与 resolve_model(role) 一致。"""
    config, sm, resolver = _setup(tmp_path)
    resolver.resolve_model.side_effect = lambda role: f"model:{role}"

    planner = _mock_driver("codex")
    planner.invoke.return_value = AgentResult(
        success=True,
        output="# Spec\ntest spec\n# Contract\n- [ ] do thing",
        exit_code=0,
    )
    builder = _mock_driver("cursor")
    builder.invoke.return_value = AgentResult(
        success=True, output="Built successfully", exit_code=0,
    )
    evaluator = _mock_driver("codex")
    evaluator.invoke.return_value = AgentResult(
        success=True, output=_make_eval_output(4.0), exit_code=0,
    )

    def _resolve(role: str):
        if role == "planner":
            return planner
        if role == "builder":
            return builder
        return evaluator

    resolver.resolve.side_effect = _resolve
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"

    result = run_single_task(config, sm, resolver, "add test feature")

    assert result.verdict == "PASS"
    assert planner.invoke.call_args.kwargs["model"] == "model:planner"
    assert builder.invoke.call_args.kwargs["model"] == "model:builder"
    assert evaluator.invoke.call_args.kwargs["model"] == "model:evaluator"


def test_single_task_pass(tmp_path: Path):
    """测试单任务 PASS 流程"""
    config, sm, resolver = _setup(tmp_path)

    # Mock planner
    planner = MagicMock()
    planner.name = "mock-planner"
    planner.invoke.return_value = AgentResult(
        success=True,
        output="# Spec\ntest spec\n# Contract\n- [ ] do thing",
        exit_code=0,
    )

    # Mock builder
    builder = MagicMock()
    builder.name = "mock-builder"
    builder.invoke.return_value = AgentResult(
        success=True, output="Built successfully", exit_code=0,
    )

    # Mock evaluator
    evaluator = MagicMock()
    evaluator.name = "mock-evaluator"
    evaluator.invoke.return_value = AgentResult(
        success=True, output=_make_eval_output(4.0), exit_code=0,
    )

    def _resolve(role: str):
        if role == "planner":
            return planner
        if role == "builder":
            return builder
        return evaluator

    resolver.resolve.side_effect = _resolve
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    result = run_single_task(config, sm, resolver, "add test feature")

    assert result.verdict == "PASS"
    assert result.score > 0
    assert result.iterations == 1
    assert len(sm.state.completed) == 1

    # insights.json 应随任务归档到 archive 目录
    archive_dir = tmp_path / ".agents" / "archive" / result.task_id
    insights_path = archive_dir / "insights.json"
    assert insights_path.exists(), "insights.json should be archived with the task"
    data = json.loads(insights_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["task"]["verdict"] == "PASS"
    assert data["quality_summary"] is not None
    assert data["quality_summary"]["weighted_score"] > 0


def test_single_task_blocked_after_max_iterations(tmp_path: Path):
    """测试达到最大迭代后阻塞"""
    config, sm, resolver = _setup(tmp_path)
    config.workflow.max_iterations = 1

    planner = MagicMock()
    planner.name = "mock-planner"
    planner.invoke.return_value = AgentResult(success=True, output="spec", exit_code=0)

    builder = MagicMock()
    builder.name = "mock-builder"
    builder.invoke.return_value = AgentResult(success=True, output="built", exit_code=0)

    evaluator = MagicMock()
    evaluator.name = "mock-evaluator"
    evaluator.invoke.return_value = AgentResult(
        success=True, output=_make_eval_output(1.5), exit_code=0,
    )

    def _resolve(role: str):
        if role == "planner":
            return planner
        if role == "builder":
            return builder
        return evaluator

    resolver.resolve.side_effect = _resolve
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    result = run_single_task(config, sm, resolver, "bad task")

    assert result.verdict == "BLOCKED"

    # BLOCKED 任务的 insights.json 留在 tasks 目录
    task_dir = tmp_path / ".agents" / "tasks" / result.task_id
    insights_path = task_dir / "insights.json"
    assert insights_path.exists(), "insights.json should exist for blocked tasks"
    data = json.loads(insights_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["task"]["verdict"] == "BLOCKED"


def test_single_task_pass_with_dual_evaluation(tmp_path: Path):
    """PASS + dual_evaluation 时 insights 包含 alignment 摘要。"""
    config, sm, resolver = _setup(tmp_path)
    config.workflow.dual_evaluation = True

    planner = MagicMock()
    planner.name = "mock-planner"
    planner.invoke.return_value = AgentResult(
        success=True,
        output="# Spec\nspec text\n# Contract\n- [ ] deliverable",
        exit_code=0,
    )

    builder = MagicMock()
    builder.name = "mock-builder"
    builder.invoke.return_value = AgentResult(success=True, output="built", exit_code=0)

    evaluator = MagicMock()
    evaluator.name = "mock-evaluator"
    evaluator.invoke.return_value = AgentResult(
        success=True, output=_make_eval_output(4.0), exit_code=0,
    )

    alignment_evaluator = MagicMock()
    alignment_evaluator.name = "mock-alignment-evaluator"
    alignment_evaluator.invoke.return_value = AgentResult(
        success=True, output="ALIGNED — all deliverables met.", exit_code=0,
    )

    def _resolve(role: str):
        if role == "planner":
            return planner
        if role == "builder":
            return builder
        if role == "alignment_evaluator":
            return alignment_evaluator
        return evaluator

    resolver.resolve.side_effect = _resolve
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    result = run_single_task(config, sm, resolver, "dual eval feature")

    assert result.verdict == "PASS"

    archive_dir = tmp_path / ".agents" / "archive" / result.task_id
    insights_path = archive_dir / "insights.json"
    assert insights_path.exists()
    data = json.loads(insights_path.read_text(encoding="utf-8"))
    assert data["alignment_summary"]["has_alignment"] is True
    assert data["alignment_summary"]["aligned"] is True
    assert data["source_artifacts"]["alignment_md"] is not None


def test_single_task_dual_eval_alignment_failure(tmp_path: Path):
    """alignment evaluator success=False → insights 不记录 aligned=True。"""
    config, sm, resolver = _setup(tmp_path)
    config.workflow.dual_evaluation = True

    planner = MagicMock()
    planner.name = "mock-planner"
    planner.invoke.return_value = AgentResult(
        success=True,
        output="# Spec\nspec\n# Contract\n- [ ] item",
        exit_code=0,
    )

    builder = MagicMock()
    builder.name = "mock-builder"
    builder.invoke.return_value = AgentResult(success=True, output="built", exit_code=0)

    evaluator = MagicMock()
    evaluator.name = "mock-evaluator"
    evaluator.invoke.return_value = AgentResult(
        success=True, output=_make_eval_output(4.0), exit_code=0,
    )

    alignment_evaluator = MagicMock()
    alignment_evaluator.name = "mock-alignment-evaluator"
    alignment_evaluator.invoke.return_value = AgentResult(
        success=False, output="segfault", exit_code=139,
    )

    def _resolve(role: str):
        if role == "planner":
            return planner
        if role == "builder":
            return builder
        if role == "alignment_evaluator":
            return alignment_evaluator
        return evaluator

    resolver.resolve.side_effect = _resolve
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    result = run_single_task(config, sm, resolver, "alignment fail task")

    assert result.verdict == "PASS"

    archive_dir = tmp_path / ".agents" / "archive" / result.task_id
    insights_path = archive_dir / "insights.json"
    assert insights_path.exists()
    data = json.loads(insights_path.read_text(encoding="utf-8"))
    assert data["alignment_summary"]["has_alignment"] is True
    assert data["alignment_summary"]["aligned"] is not True


def test_single_task_dual_eval_alignment_unknown_verdict(tmp_path: Path):
    """alignment evaluator 成功但输出不含已知 verdict → aligned != True。"""
    config, sm, resolver = _setup(tmp_path)
    config.workflow.dual_evaluation = True

    planner = MagicMock()
    planner.name = "mock-planner"
    planner.invoke.return_value = AgentResult(
        success=True,
        output="# Spec\nspec\n# Contract\n- [ ] item",
        exit_code=0,
    )

    builder = MagicMock()
    builder.name = "mock-builder"
    builder.invoke.return_value = AgentResult(success=True, output="built", exit_code=0)

    evaluator = MagicMock()
    evaluator.name = "mock-evaluator"
    evaluator.invoke.return_value = AgentResult(
        success=True, output=_make_eval_output(4.0), exit_code=0,
    )

    alignment_evaluator = MagicMock()
    alignment_evaluator.name = "mock-alignment-evaluator"
    alignment_evaluator.invoke.return_value = AgentResult(
        success=True, output="I checked the code and it looks fine.", exit_code=0,
    )

    def _resolve(role: str):
        if role == "planner":
            return planner
        if role == "builder":
            return builder
        if role == "alignment_evaluator":
            return alignment_evaluator
        return evaluator

    resolver.resolve.side_effect = _resolve
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    result = run_single_task(config, sm, resolver, "unknown verdict task")

    assert result.verdict == "PASS"

    archive_dir = tmp_path / ".agents" / "archive" / result.task_id
    insights_path = archive_dir / "insights.json"
    assert insights_path.exists()
    data = json.loads(insights_path.read_text(encoding="utf-8"))
    assert data["alignment_summary"]["has_alignment"] is True
    assert data["alignment_summary"]["aligned"] is None


def test_single_task_blocked_early_abort_degraded(tmp_path: Path):
    """Planner 失败直接阻塞 — insights 降级为只含元数据。"""
    config, sm, resolver = _setup(tmp_path)

    planner = MagicMock()
    planner.name = "mock-planner"
    planner.invoke.return_value = AgentResult(
        success=False, output="segfault", exit_code=139,
    )

    resolver.resolve.side_effect = lambda role: planner
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    result = run_single_task(config, sm, resolver, "doomed task")

    assert result.verdict == "BLOCKED"

    task_dir = tmp_path / ".agents" / "tasks" / result.task_id
    insights_path = task_dir / "insights.json"
    assert insights_path.exists()
    data = json.loads(insights_path.read_text(encoding="utf-8"))
    assert data["task"]["verdict"] == "BLOCKED"
    assert data["quality_summary"] is None
    assert data["source_artifacts"]["evaluation_json"] is None


# ── Branch lifecycle integration tests ────────────────────────────


def test_dirty_worktree_blocks_task_start(tmp_path: Path):
    """ensure_clean prevents task start when working tree is dirty."""
    config, sm, resolver = _setup(tmp_path)

    (tmp_path / "uncommitted.txt").write_text("dirty", encoding="utf-8")

    resolver.resolve.side_effect = lambda role: MagicMock(name="mock")
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    with pytest.raises(DirtyWorktreeError):
        run_single_task(config, sm, resolver, "should not start")


def test_pass_rebases_to_trunk(tmp_path: Path):
    """PASS path uses rebase_and_merge, landing on trunk with linear history."""
    config, sm, resolver = _setup(tmp_path)

    planner = MagicMock(name="mock-planner")
    planner.invoke.return_value = AgentResult(
        success=True,
        output="# Spec\nspec\n# Contract\n- [ ] item",
        exit_code=0,
    )
    builder = MagicMock(name="mock-builder")
    builder.invoke.return_value = AgentResult(
        success=True, output="built", exit_code=0,
    )
    evaluator = MagicMock(name="mock-evaluator")
    evaluator.invoke.return_value = AgentResult(
        success=True, output=_make_eval_output(4.0), exit_code=0,
    )

    def _resolve(role: str):
        if role == "planner":
            return planner
        if role == "builder":
            return builder
        return evaluator

    resolver.resolve.side_effect = _resolve
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    result = run_single_task(config, sm, resolver, "rebase feature")
    assert result.verdict == "PASS"
    assert current_branch(tmp_path) == "main"

    branches = subprocess.run(
        ["git", "branch"], cwd=str(tmp_path), capture_output=True, text=True,
    ).stdout
    assert "agent/" not in branches


def test_exception_triggers_safe_cleanup(tmp_path: Path):
    """Unhandled exception in task loop triggers safe_cleanup back to trunk."""
    config, sm, resolver = _setup(tmp_path)

    planner = MagicMock(name="mock-planner")
    planner.invoke.side_effect = RuntimeError("driver exploded")

    resolver.resolve.side_effect = lambda role: planner
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    with pytest.raises(Exception):
        run_single_task(config, sm, resolver, "crash task")

    assert current_branch(tmp_path) == "main"


def test_trunk_branch_configurable(tmp_path: Path):
    """Custom trunk_branch is used instead of hardcoded 'main'."""
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = ""\n'
        '[workflow]\ntrunk_branch = "develop"\n',
        encoding="utf-8",
    )
    (agents_dir / "tasks").mkdir()

    _git(["init"], tmp_path)
    _git(["checkout", "-b", "develop"], tmp_path)
    (tmp_path / "dummy.txt").write_text("init", encoding="utf-8")

    config = HarnessConfig.load(tmp_path)
    sm = StateMachine(tmp_path)
    sm.start_session("run")

    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "init"], tmp_path)

    assert config.workflow.trunk_branch == "develop"

    planner = MagicMock(name="mock-planner")
    planner.invoke.return_value = AgentResult(
        success=True,
        output="# Spec\nspec\n# Contract\n- [ ] item",
        exit_code=0,
    )
    builder = MagicMock(name="mock-builder")
    builder.invoke.return_value = AgentResult(
        success=True, output="built", exit_code=0,
    )
    evaluator = MagicMock(name="mock-evaluator")
    evaluator.invoke.return_value = AgentResult(
        success=True, output=_make_eval_output(4.5), exit_code=0,
    )

    def _resolve(role: str):
        if role == "planner":
            return planner
        if role == "builder":
            return builder
        return evaluator

    resolver = MagicMock(spec=DriverResolver)
    resolver.resolve.side_effect = _resolve
    resolver.agent_name.side_effect = lambda r: f"harness-{r}"
    resolver.resolve_model.return_value = ""

    result = run_single_task(config, sm, resolver, "develop feature")
    assert result.verdict == "PASS"
    assert current_branch(tmp_path) == "develop"
