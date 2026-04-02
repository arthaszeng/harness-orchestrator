"""Progress report generator — maintains .agents/progress.md.

Provides shared summary helpers used by both progress.md generation and
the `harness status` command.
"""

from __future__ import annotations

from pathlib import Path

from harness.core.state import CompletedTask, SessionState, TaskState
from harness.core.workflow_state import (
    WorkflowState,
    artifact_pairs,
    gate_pairs,
    load_current_workflow_state,
)


# ---------------------------------------------------------------------------
# Shared summary helpers (used by status.py as well)
# ---------------------------------------------------------------------------


def get_recent_completed(state: SessionState) -> CompletedTask | None:
    """Return the most recently completed task, or None."""
    return state.completed[-1] if state.completed else None


def get_recent_blocked(state: SessionState) -> CompletedTask | None:
    """Return the most recently blocked task, or None."""
    return state.blocked[-1] if state.blocked else None


def is_resumable(state: SessionState) -> bool:
    """True when the session has an active task and is not idle."""
    return state.mode != "idle" and state.current_task is not None


def suggest_next_action(
    state: SessionState,
    workflow_state: WorkflowState | None = None,
) -> str:
    """Derive a human-readable next-step suggestion from the current state."""
    if workflow_state and workflow_state.blocker.reason:
        return f"当前任务被阻塞 — {workflow_state.blocker.reason}"
    if workflow_state and workflow_state.phase not in {TaskState.IDLE, TaskState.DONE}:
        phase = workflow_state.phase.value
        if workflow_state.active_plan.title:
            return f"当前任务处于 {phase} 阶段 — 在 Cursor 中继续 `{workflow_state.active_plan.title}`"
        return f"当前任务处于 {phase} 阶段 — 在 Cursor 中通过 harness 技能继续"
    if is_resumable(state):
        return "会话可恢复 — 在 Cursor 中通过 harness 技能继续当前任务"
    if state.mode != "idle":
        return "会话进行中，等待当前流程完成"
    if state.blocked and not state.completed:
        return "所有任务已阻塞，检查阻塞原因后重新发起"
    if state.completed:
        return "使用 Cursor 中的 harness 技能开始新的计划、构建或评审流程"
    return "使用 Cursor 中的 harness 技能开始"


# ---------------------------------------------------------------------------
# progress.md generation
# ---------------------------------------------------------------------------


def update_progress(agents_dir: Path, state: SessionState) -> None:
    """Regenerate progress.md from the current session state."""
    path = agents_dir / "progress.md"
    _, workflow_state = load_current_workflow_state(
        agents_dir,
        session_task_id=state.current_task.id if state.current_task else None,
    )
    lines: list[str] = []

    lines.append("# Progress Report\n")
    lines.append(f"## Session {state.session_id or 'N/A'}\n")
    lines.append(f"- **Mode**: {state.mode}")

    status_label = "active" if state.mode != "idle" else "idle"
    lines.append(f"- **Status**: {status_label}\n")

    # Current Task
    lines.append("### Current Task\n")
    if state.current_task:
        t = state.current_task
        lines.append(f"- **[{t.id}]** {t.requirement} — **{t.state.value}** (iteration {t.iteration})")
        lines.append(f"- Branch: `{t.branch}`")
        _artifacts = []
        if t.artifacts.spec:
            _artifacts.append(f"spec: `{t.artifacts.spec}`")
        if t.artifacts.contract:
            _artifacts.append(f"contract: `{t.artifacts.contract}`")
        if t.artifacts.evaluation:
            _artifacts.append(f"evaluation: `{t.artifacts.evaluation}`")
        if _artifacts:
            lines.append(f"- Artifacts: {', '.join(_artifacts)}")
    elif workflow_state:
        lines.append(f"- **[{workflow_state.task_id}]** canonical workflow state")
    else:
        lines.append("(none)")
    if workflow_state:
        lines.append(f"- Canonical phase: **{workflow_state.phase.value}**")
        if workflow_state.active_plan.title:
            lines.append(f"- Active plan: `{workflow_state.active_plan.title}`")
        if workflow_state.blocker.reason:
            lines.append(f"- Blocker: {workflow_state.blocker.reason}")
        artifacts = artifact_pairs(workflow_state)
        if artifacts:
            lines.append(
                "- Artifact refs: "
                + ", ".join(f"{label}: `{value}`" for label, value in artifacts)
            )
        gates = gate_pairs(workflow_state)
        if gates:
            lines.append(
                "- Gates: "
                + ", ".join(
                    f"{label}={snapshot.status.value}"
                    + (f" ({snapshot.reason})" if snapshot.reason else "")
                    for label, snapshot in gates
                )
            )
        lines.append(
            f"- Workflow state: `.agents/tasks/{workflow_state.task_id}/workflow-state.json`"
        )

    # Recent Completed
    lines.append("\n### Recent Completed\n")
    recent_done = get_recent_completed(state)
    if recent_done:
        lines.append("| Task | Score | Verdict | Iterations |")
        lines.append("|------|-------|---------|------------|")
        lines.append(
            f"| {recent_done.requirement} | {recent_done.score:.1f} "
            f"| {recent_done.verdict} | {recent_done.iterations} |"
        )
    else:
        lines.append("(none)")

    # Recent Blocked
    lines.append("\n### Recent Blocked\n")
    recent_block = get_recent_blocked(state)
    if recent_block:
        lines.append("| Task | Score | Verdict |")
        lines.append("|------|-------|---------|")
        lines.append(
            f"| {recent_block.requirement} | {recent_block.score:.1f} "
            f"| {recent_block.verdict} |"
        )
    else:
        lines.append("(none)")

    # Resumable
    lines.append("\n### Resumable\n")
    if is_resumable(state):
        lines.append(f"⚠️ 会话可恢复 (session: `{state.session_id}`)")
        lines.append("- 在 Cursor 中通过 harness 技能继续")
    else:
        lines.append("(无可恢复会话)")

    # Next Action
    lines.append("\n### Next Action\n")
    lines.append(suggest_next_action(state, workflow_state))

    # Full completed list
    lines.append("\n### Completed Tasks\n")
    if state.completed:
        lines.append("| # | Task | Score | Iterations | Time |")
        lines.append("|---|------|-------|------------|------|")
        for i, task in enumerate(state.completed, 1):
            elapsed = _fmt_elapsed(task.elapsed_seconds)
            lines.append(
                f"| {i} | {task.requirement} | {task.score:.1f} ({task.verdict}) "
                f"| {task.iterations} | {elapsed} |"
            )
    else:
        lines.append("(none)")

    # Full blocked list
    lines.append("\n### Blocked\n")
    if state.blocked:
        for task in state.blocked:
            lines.append(f"- [{task.id}] {task.requirement} — score {task.score:.1f}")
    else:
        lines.append("(none)")

    # Stats
    lines.append("\n### Stats\n")
    s = state.stats
    lines.append(f"- Completed: {s.completed}/{s.total_tasks} tasks")
    lines.append(f"- Blocked: {s.blocked}")
    lines.append(f"- Average score: {s.avg_score:.1f}")
    lines.append(f"- Total iterations: {s.total_iterations}")
    lines.append(f"- Elapsed: {_fmt_elapsed(s.elapsed_seconds)}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed duration for display."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    mins = seconds / 60
    if mins < 60:
        return f"{mins:.0f}min"
    hours = mins / 60
    return f"{hours:.1f}h"
