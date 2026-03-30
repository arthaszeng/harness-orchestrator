"""单任务工作流: plan → contract → build → eval"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from harness.core.archive import archive_task, ensure_task_dir
from harness.core.config import HarnessConfig
from harness.core.events import EventEmitter, NullEventEmitter
from harness.core.index import update_index
from harness.core.progress import update_progress
from harness.core.state import StateMachine, TaskState
from harness.core.ui import get_ui
from harness.drivers.base import AgentResult
from harness.drivers.resolver import DriverResolver
from harness.methodology.contracts import parse_contract, write_contract_sidecar
from harness.methodology.evaluation import parse_evaluation, run_ci_check
from harness.methodology.scoring import write_evaluation_sidecar


@dataclass
class WorkflowResult:
    task_id: str
    requirement: str
    verdict: str  # PASS / BLOCKED
    score: float
    iterations: int
    feedback: str = ""


def _resolve_profile(config: HarnessConfig) -> tuple[int, float]:
    """Return (max_iterations, pass_threshold) adjusted for the active profile."""
    profile = config.workflow.profile
    if profile == "lite":
        return (
            min(config.workflow.max_iterations, 2),
            min(config.workflow.pass_threshold, 3.0),
        )
    return config.workflow.max_iterations, config.workflow.pass_threshold


def run_single_task(
    config: HarnessConfig,
    sm: StateMachine,
    resolver: DriverResolver,
    requirement: str,
    task_id: str | None = None,
    *,
    resume: bool = False,
    events: EventEmitter | None = None,
) -> WorkflowResult:
    """执行完整的 plan→contract→build→eval 循环"""
    from harness.integrations import git_ops

    ui = get_ui()
    ev = events or NullEventEmitter()
    project_root = config.project_root
    agents_dir = sm.agents_dir
    is_lite = config.workflow.profile == "lite"

    if not task_id:
        seq = len(sm.state.completed) + len(sm.state.blocked) + 1
        task_id = f"task-{seq:03d}"

    slug = re.sub(r"[^a-z0-9]+", "-", requirement.lower())[:40].strip("-")
    branch = f"{config.workflow.branch_prefix}/{slug}"
    task_dir = ensure_task_dir(agents_dir, task_id)

    current = sm.state.current_task
    if resume and current and current.id == task_id:
        ui.info(f"resuming [{task_id}] from {current.state.value}")
    else:
        main_branch = git_ops.current_branch(project_root)
        git_ops.create_branch(branch, project_root)
        sm.start_task(task_id, requirement, branch)

    ui.task_panel(task_id, requirement, branch)
    ev.task_start(task_id=task_id, requirement=requirement, branch=branch)

    max_iter, pass_threshold = _resolve_profile(config)
    last_feedback = ""
    task_start = time.monotonic()
    abort_reason = ""

    # On resume, continue from the last recorded iteration to avoid overwriting artifacts
    start_iteration = 1
    if resume and sm.state.current_task and sm.state.current_task.iteration > 0:
        start_iteration = sm.state.current_task.iteration

    for iteration in range(start_iteration, start_iteration + max_iter):
        if sm.stop_requested():
            ui.warn("stop signal detected, saving progress...")
            break

        current_state = sm.state.current_task.state if sm.state.current_task else TaskState.IDLE

        # === Phase 1: Planning ===
        if current_state in (TaskState.IDLE, TaskState.EVALUATING):
            ui.iteration_header(iteration, max_iter)
            sm.transition(TaskState.PLANNING)

            planner = resolver.resolve("planner")
            planner_name = resolver.agent_name("planner")

            if iteration == 1:
                plan_prompt = _build_plan_prompt(requirement, project_root)
            else:
                plan_prompt = _build_iterate_prompt(requirement, last_feedback, project_root)

            ev.agent_start(role="planner", driver=planner.name, agent_name=planner_name, iteration=iteration)
            t0 = time.monotonic()
            with ui.agent_step("[1/3 planner] generating spec + contract", planner.name) as on_out:
                plan_result = planner.invoke(
                    planner_name, plan_prompt, project_root,
                    readonly=True, on_output=on_out,
                )
            elapsed = time.monotonic() - t0
            ev.agent_end(
                role="planner", driver=planner.name, agent_name=planner_name,
                iteration=iteration, exit_code=plan_result.exit_code,
                success=plan_result.success, output_len=len(plan_result.output),
                elapsed_ms=int(elapsed * 1000),
            )

            if plan_result.success:
                ui.step_done("[1/3 planner]", elapsed, True, "locked")
            else:
                ui.step_done(
                    "[1/3 planner]", elapsed, False, "failed",
                    fail_tail=plan_result.output.split("\n"),
                )
                abort_reason = f"planner failed (exit {plan_result.exit_code})"
                ui.error(f"[abort] {abort_reason}")
                break

            if is_lite:
                combined = plan_result.output.strip()
                (task_dir / f"spec-r{iteration}.md").write_text(combined, encoding="utf-8")
                (task_dir / f"contract-r{iteration}.md").write_text(combined, encoding="utf-8")
            else:
                spec_text, contract_text = _split_spec_contract(plan_result.output)
                (task_dir / f"spec-r{iteration}.md").write_text(spec_text, encoding="utf-8")
                (task_dir / f"contract-r{iteration}.md").write_text(contract_text, encoding="utf-8")
            sm.state.current_task.artifacts.spec = str(task_dir / f"spec-r{iteration}.md")
            sm.state.current_task.artifacts.contract = str(task_dir / f"contract-r{iteration}.md")

            contract_md_path = task_dir / f"contract-r{iteration}.md"
            parsed_contract = parse_contract(contract_md_path.read_text(encoding="utf-8"))
            parsed_contract.iteration = iteration
            write_contract_sidecar(parsed_contract, contract_md_path)

        # === Phase 2: Contracted → Building ===
        if sm.state.current_task.state == TaskState.PLANNING:
            sm.transition(TaskState.CONTRACTED)

        if sm.state.current_task.state == TaskState.CONTRACTED:
            sm.transition(TaskState.BUILDING)

            builder = resolver.resolve("builder")
            builder_name = resolver.agent_name("builder")
            build_prompt = _build_builder_prompt(requirement, task_dir, iteration, project_root)

            ev.agent_start(role="builder", driver=builder.name, agent_name=builder_name, iteration=iteration)
            t0 = time.monotonic()
            with ui.agent_step("[2/3 builder] executing contract", builder.name) as on_out:
                build_result = builder.invoke(
                    builder_name, build_prompt, project_root,
                    on_output=on_out,
                )
            elapsed = time.monotonic() - t0
            ev.agent_end(
                role="builder", driver=builder.name, agent_name=builder_name,
                iteration=iteration, exit_code=build_result.exit_code,
                success=build_result.success, output_len=len(build_result.output),
                elapsed_ms=int(elapsed * 1000),
            )

            (task_dir / f"build-r{iteration}.log").write_text(
                build_result.output, encoding="utf-8"
            )

            if build_result.success:
                ui.step_done("[2/3 builder]", elapsed, True, "deployed")
            else:
                ui.step_done(
                    "[2/3 builder]", elapsed, False, "build failed",
                    fail_tail=build_result.output.split("\n"),
                )
                if _is_driver_error(elapsed, build_result):
                    abort_reason = f"builder driver error (exit {build_result.exit_code}, {elapsed:.0f}s)"
                    ui.error(f"[abort] {abort_reason} — 驱动级错误，重试无意义")
                    break
                # 代码级失败：跳过 eval，用 builder 错误做 feedback 进入下一轮
                last_feedback = f"Builder 执行失败:\n{build_result.output[-2000:]}"
                sm.transition(TaskState.EVALUATING)
                continue

        # === Phase 3: Evaluating ===
        if sm.state.current_task.state == TaskState.BUILDING:
            sm.transition(TaskState.EVALUATING)

            # Stage 1: CI 门禁
            t0 = time.monotonic()
            with ui.agent_step("[3/3 eval] CI gate", "local") as on_out:
                ci_result = run_ci_check(config.ci.command, project_root, on_output=on_out)
            elapsed = time.monotonic() - t0
            ev.ci_result(
                command=config.ci.command,
                exit_code=0 if ci_result.verdict != "CI_FAIL" else 1,
                verdict=ci_result.verdict,
                elapsed_ms=int(elapsed * 1000),
            )

            if ci_result.verdict == "CI_FAIL":
                ui.step_done(
                    "[3/3 eval] CI gate", elapsed, False, "failed",
                    fail_tail=ci_result.feedback.split("\n"),
                )
                last_feedback = f"CI 失败:\n{ci_result.feedback}"
                (task_dir / f"evaluation-r{iteration}.md").write_text(
                    f"# CI 失败\n\n{ci_result.feedback}", encoding="utf-8"
                )
                sm.state.current_task.artifacts.evaluation = str(
                    task_dir / f"evaluation-r{iteration}.md"
                )
                continue
            else:
                ui.step_done("[3/3 eval] CI gate", elapsed, True, "clear")

            # Stage 2: Quality review (primary evaluator)
            evaluator = resolver.resolve("evaluator")
            eval_name = resolver.agent_name("evaluator")
            eval_prompt = _build_eval_prompt(
                requirement, task_dir, iteration, project_root, branch=branch,
            )

            ev.agent_start(role="evaluator", driver=evaluator.name, agent_name=eval_name, iteration=iteration)
            t0 = time.monotonic()
            with ui.agent_step("[3/3 eval] quality review", evaluator.name) as on_out:
                eval_result = evaluator.invoke(
                    eval_name, eval_prompt, project_root,
                    readonly=True, on_output=on_out,
                )
            elapsed = time.monotonic() - t0
            ev.agent_end(
                role="evaluator", driver=evaluator.name, agent_name=eval_name,
                iteration=iteration, exit_code=eval_result.exit_code,
                success=eval_result.success, output_len=len(eval_result.output),
                elapsed_ms=int(elapsed * 1000),
            )

            if not eval_result.success:
                ui.step_done(
                    "[3/3 eval] quality review", elapsed, False, "evaluator failed",
                    fail_tail=eval_result.output.split("\n"),
                )
                abort_reason = f"evaluator failed (exit {eval_result.exit_code})"
                ui.error(f"[abort] {abort_reason}")
                break

            parsed = parse_evaluation(eval_result.output, pass_threshold)
            eval_md_path = task_dir / f"evaluation-r{iteration}.md"
            eval_md_path.write_text(eval_result.output, encoding="utf-8")
            sm.state.current_task.artifacts.evaluation = str(eval_md_path)

            if parsed.scores:
                write_evaluation_sidecar(
                    parsed.scores, parsed.verdict, parsed.feedback,
                    iteration, eval_md_path,
                )

            score = parsed.scores.weighted if parsed.scores else 0.0
            verdict_detail = f"score {score:.1f} → {parsed.verdict}"
            ui.step_done("[3/3 eval] quality review", elapsed, parsed.verdict == "PASS", verdict_detail)

            # Stage 3 (optional): Alignment review
            alignment_feedback = ""
            if config.workflow.dual_evaluation and parsed.verdict == "PASS":
                align_eval = resolver.resolve("alignment_evaluator")
                align_name = resolver.agent_name("alignment_evaluator")
                align_prompt = _build_alignment_eval_prompt(
                    requirement, task_dir, iteration, project_root, branch=branch,
                )
                ev.agent_start(
                    role="alignment_evaluator", driver=align_eval.name,
                    agent_name=align_name, iteration=iteration,
                )
                t0 = time.monotonic()
                with ui.agent_step("[3/3 eval] alignment review", align_eval.name) as on_out:
                    align_result = align_eval.invoke(
                        align_name, align_prompt, project_root,
                        readonly=True, on_output=on_out,
                    )
                a_elapsed = time.monotonic() - t0
                ev.agent_end(
                    role="alignment_evaluator", driver=align_eval.name,
                    agent_name=align_name, iteration=iteration,
                    exit_code=align_result.exit_code, success=align_result.success,
                    output_len=len(align_result.output), elapsed_ms=int(a_elapsed * 1000),
                )

                align_md = task_dir / f"alignment-r{iteration}.md"
                align_md.write_text(align_result.output, encoding="utf-8")

                if align_result.success and "MISALIGNED" in align_result.output:
                    parsed.verdict = "ITERATE"
                    alignment_feedback = align_result.output
                    ui.step_done("[3/3 eval] alignment", a_elapsed, False, "MISALIGNED → iterate")
                elif align_result.success and "CONTRACT_ISSUE" in align_result.output:
                    parsed.verdict = "ITERATE"
                    alignment_feedback = f"[CONTRACT_ISSUE] {align_result.output}"
                    ui.step_done("[3/3 eval] alignment", a_elapsed, False, "CONTRACT_ISSUE → replan")
                else:
                    ui.step_done("[3/3 eval] alignment", a_elapsed, True, "ALIGNED")

            if parsed.verdict == "PASS":
                sm.transition(TaskState.DONE)
                sm.complete_task(score=score, verdict="PASS")
                ev.task_end(task_id=task_id, verdict="PASS", score=score, iterations=iteration)

                if config.workflow.auto_merge:
                    ui.info("[git] merging to main...")
                    git_ops.merge_branch(branch, "main", project_root)

                archive_task(agents_dir, task_id)
                update_progress(agents_dir, sm.state)
                update_index(agents_dir, sm.state)

                task_elapsed = time.monotonic() - task_start
                ui.task_complete(task_id, score, task_elapsed)
                return WorkflowResult(
                    task_id=task_id, requirement=requirement,
                    verdict="PASS", score=score, iterations=iteration,
                )

            last_feedback = alignment_feedback if alignment_feedback else parsed.feedback

    # 达到最大迭代、被中断或 abort
    final_score = 0.0
    total_iterations = iteration - start_iteration + 1
    sm.transition(TaskState.BLOCKED)
    sm.complete_task(score=final_score, verdict="BLOCKED")
    ev.task_end(task_id=task_id, verdict="BLOCKED", score=final_score, iterations=total_iterations)
    update_progress(agents_dir, sm.state)
    update_index(agents_dir, sm.state)

    block_reason = abort_reason or f"max iterations ({max_iter})"
    ui.task_blocked(task_id, max_iter, reason=block_reason)
    return WorkflowResult(
        task_id=task_id, requirement=requirement,
        verdict="BLOCKED", score=final_score,
        iterations=total_iterations if not abort_reason else total_iterations,
        feedback=abort_reason or last_feedback,
    )


_DRIVER_ERROR_THRESHOLD_SECS = 10
_DRIVER_ERROR_OUTPUT_LEN = 200

_CONTRACT_MARKERS = [
    re.compile(r"^#\s+Contract\b", re.IGNORECASE | re.MULTILINE),
]


def _is_driver_error(elapsed: float, result: AgentResult) -> bool:
    """判断是否为驱动级错误（非代码问题，重试无意义）"""
    output_len = len(result.output.strip())
    return elapsed < _DRIVER_ERROR_THRESHOLD_SECS and output_len < _DRIVER_ERROR_OUTPUT_LEN


def _split_spec_contract(text: str) -> tuple[str, str]:
    """按 '# Contract' 标记拆分 planner 输出为 (spec, contract)。
    找不到标记时 spec=全文, contract=全文（兼容旧行为）。"""
    for pattern in _CONTRACT_MARKERS:
        m = pattern.search(text)
        if m:
            spec = text[: m.start()].rstrip()
            contract = text[m.start() :].strip()
            return (spec or text.strip(), contract or text.strip())
    return text.strip(), text.strip()


def _git_branch_summary(project_root: Path, branch: str) -> str:
    """获取分支相对于 main 的 diff stat 和 commit log"""
    parts: list[str] = []
    try:
        stat = subprocess.run(
            ["git", "diff", "main..HEAD", "--stat"],
            capture_output=True, text=True, cwd=str(project_root), timeout=10,
        )
        if stat.stdout.strip():
            parts.append(f"### git diff main..HEAD --stat\n```\n{stat.stdout.strip()}\n```")
    except Exception:
        pass

    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "main..HEAD"],
            capture_output=True, text=True, cwd=str(project_root), timeout=10,
        )
        if log.stdout.strip():
            parts.append(f"### git log --oneline main..HEAD\n```\n{log.stdout.strip()}\n```")
    except Exception:
        pass

    return "\n\n".join(parts) if parts else "(无法获取分支差异)"


def _build_plan_prompt(requirement: str, project_root: Path) -> str:
    agents_md = ""
    agents_file = project_root / "AGENTS.md"
    if agents_file.exists():
        agents_md = agents_file.read_text(encoding="utf-8")[:3000]

    file_tree = _get_file_tree(project_root)
    tree_block = f"\n## 项目文件树\n```\n{file_tree}\n```" if file_tree else ""

    return f"""\
项目根目录: {project_root}

## 需求
{requirement}

## 项目规范（摘要）
{agents_md if agents_md else '（未找到 AGENTS.md）'}
{tree_block}

请分析需求，输出 Spec（技术规格）和首次迭代的 Contract（合同）。
严格按照你的 agent 指令中定义的格式输出。
"""


def _build_iterate_prompt(requirement: str, feedback: str, project_root: Path) -> str:
    return f"""\
项目根目录: {project_root}

## 原始需求
{requirement}

## Evaluator 反馈
{feedback}

请根据反馈调整合同，只关注反馈中提到的问题。
严格按照 Contract 格式输出。
"""


def _build_builder_prompt(
    requirement: str, task_dir: Path, iteration: int, project_root: Path | None = None,
) -> str:
    contract = ""
    contract_file = task_dir / f"contract-r{iteration}.md"
    if contract_file.exists():
        contract = contract_file.read_text(encoding="utf-8")[:5000]

    spec = ""
    spec_file = task_dir / f"spec-r{iteration}.md"
    if spec_file.exists():
        spec = spec_file.read_text(encoding="utf-8")[:5000]

    context_sections: list[str] = []

    if project_root:
        # AGENTS.md
        agents_file = project_root / "AGENTS.md"
        if agents_file.exists():
            try:
                content = agents_file.read_text(encoding="utf-8")[:3000]
                context_sections.append(f"### AGENTS.md（项目规范）\n{content}")
            except OSError:
                pass

        # 文件树快照
        file_tree = _get_file_tree(project_root)
        if file_tree:
            context_sections.append(f"### 项目文件树\n```\n{file_tree}\n```")

        # 从 contract 提取引用的文件路径并预读内容
        if contract:
            referenced = _extract_file_refs(contract, project_root)
            if referenced:
                context_sections.append(referenced)

    context_block = "\n\n".join(context_sections)

    return f"""\
## 任务
{requirement}

## 技术规格（Planner 的分析结果，供参考）
{spec if spec else '（无）'}

## 合同（你的交付清单）
{contract}

## 项目上下文（已预读，不要重复读取这些文件）
{context_block if context_block else '（无预读上下文）'}

## 执行要求
- 按合同交付物逐项实现，完成后提交代码
- 上方已提供项目规范和关键文件内容，**跳过探索阶段，直接开始编码**
- 只在需要查看 prompt 未包含的文件时才调用 read/glob
- 遵守项目的编码规范和架构约束
"""


_FILE_TREE_MAX_LINES = 80
_FILE_REF_PATTERN = re.compile(r"`([a-zA-Z_][\w./\-]*(?:\.(?:py|md|toml|json|yaml|yml|txt|cfg|sh))?/?)`")
_FILE_REF_PER_FILE = 4000
_FILE_REF_MAX_TOTAL = 20000


def _get_file_tree(project_root: Path) -> str:
    """生成项目文件树快照（3 层深度，排除常见噪音目录）"""
    try:
        result = subprocess.run(
            [
                "find", ".", "-maxdepth", "3",
                "-not", "-path", "./.git/*",
                "-not", "-path", "./.git",
                "-not", "-path", "./__pycache__/*",
                "-not", "-path", "./.mypy_cache/*",
                "-not", "-path", "./node_modules/*",
                "-not", "-path", "./.next/*",
                "-not", "-path", "./.pytest_cache/*",
                "-not", "-path", "./.agents/tasks/*",
                "-not", "-name", "*.pyc",
            ],
            capture_output=True, text=True,
            cwd=str(project_root), timeout=5,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) > _FILE_TREE_MAX_LINES:
            lines = lines[:_FILE_TREE_MAX_LINES] + [f"... ({len(lines) - _FILE_TREE_MAX_LINES} more)"]
        return "\n".join(sorted(lines))
    except Exception:
        return ""


def _extract_file_refs(contract: str, project_root: Path) -> str:
    """从 contract 文本中提取文件路径引用，预读存在的文件内容"""
    matches = _FILE_REF_PATTERN.findall(contract)
    seen: set[str] = set()
    parts: list[str] = []
    total_len = 0

    for ref in matches:
        ref = ref.rstrip("/")
        if ref in seen or not ref or ref.startswith("."):
            continue
        seen.add(ref)

        path = project_root / ref
        if not path.is_file():
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        if len(content) > _FILE_REF_PER_FILE:
            content = content[:_FILE_REF_PER_FILE] + "\n... (truncated)"

        chunk = f"#### {ref}\n```\n{content}\n```"
        if total_len + len(chunk) > _FILE_REF_MAX_TOTAL:
            parts.append("... (更多文件已省略，请自行读取)")
            break
        parts.append(chunk)
        total_len += len(chunk)

    if not parts:
        return ""
    return "### 合同引用的关键文件\n" + "\n\n".join(parts)


def _build_alignment_eval_prompt(
    requirement: str,
    task_dir: Path,
    iteration: int,
    project_root: Path,
    *,
    branch: str = "",
) -> str:
    contract = ""
    contract_file = task_dir / f"contract-r{iteration}.md"
    if contract_file.exists():
        contract = contract_file.read_text(encoding="utf-8")[:5000]

    branch_summary = _git_branch_summary(project_root, branch)

    return f"""\
项目根目录: {project_root}

## 原始需求
{requirement}

## 合同
{contract}

## Builder 分支变更
分支: {branch}

{branch_summary}

## 对齐评估指引
请评估实现是否与原始需求和合同对齐。关注：
1. 需求中的每个要点是否被覆盖
2. 合同的每个交付物和验收标准是否被满足
3. 实现是否偏离需求的核心意图
4. 合同本身是否遗漏了需求中的关键点

严格按照你的 agent 指令中定义的格式输出。
"""


def _build_eval_prompt(
    requirement: str,
    task_dir: Path,
    iteration: int,
    project_root: Path,
    *,
    branch: str = "",
) -> str:
    contract = ""
    contract_file = task_dir / f"contract-r{iteration}.md"
    if contract_file.exists():
        contract = contract_file.read_text(encoding="utf-8")[:5000]

    # 注入分支变更摘要，让 evaluator 看到 builder 的实际 commit
    branch_summary = _git_branch_summary(project_root, branch)

    # 注入 build log 摘要
    build_log = ""
    build_log_file = task_dir / f"build-r{iteration}.log"
    if build_log_file.exists():
        raw = build_log_file.read_text(encoding="utf-8")
        build_log = raw[-2000:] if len(raw) > 2000 else raw

    return f"""\
项目根目录: {project_root}

## 原始需求
{requirement}

## 合同
{contract}

## Builder 分支变更（重要：请用此数据评估，不要依赖 working tree diff）
分支: {branch}

{branch_summary}

## Builder 工作日志（摘要）
{build_log if build_log else '（无日志）'}

## 评估指引
- **关键**：Builder 会 commit 代码，因此 `git diff`（working tree）可能为空。
  请使用上方的分支变更摘要，或执行 `git diff main..HEAD` 来查看实际变更。
- 检查测试状态，按四维标准打分。
- 严格按照你的 agent 指令中定义的 Evaluation 格式输出。
"""
