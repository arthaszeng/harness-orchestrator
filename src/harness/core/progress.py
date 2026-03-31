"""Progress report generator — maintains .agents/progress.md.

Provides shared summary helpers used by both progress.md generation and
the `harness status` command.
"""

from __future__ import annotations

from pathlib import Path

from harness.core.state import CompletedTask, SessionState


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


def suggest_next_action(state: SessionState) -> str:
    """Derive a human-readable next-step suggestion from the current state."""
    if is_resumable(state):
        cmd = "harness run --resume" if state.mode == "run" else "harness auto --resume"
        return f"会话可恢复，运行 `{cmd}` 继续"
    if state.mode != "idle":
        return "会话进行中，等待当前流程完成"
    if state.blocked and not state.completed:
        return "所有任务已阻塞，检查阻塞原因后重新发起"
    if state.completed:
        return "运行 `harness auto` 开始新会话，或 `harness run <requirement>` 执行单个任务"
    return "运行 `harness run <requirement>` 或 `harness auto` 开始"


# ---------------------------------------------------------------------------
# progress.md generation
# ---------------------------------------------------------------------------


def update_progress(agents_dir: Path, state: SessionState) -> None:
    """Regenerate progress.md from the current session state."""
    path = agents_dir / "progress.md"
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
    else:
        lines.append("(none)")

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
        cmd = "harness run --resume" if state.mode == "run" else "harness auto --resume"
        lines.append(f"⚠️ 会话可恢复 (session: `{state.session_id}`)")
        lines.append(f"- 建议命令: `{cmd}`")
    else:
        lines.append("(无可恢复会话)")

    # Next Action
    lines.append("\n### Next Action\n")
    lines.append(suggest_next_action(state))

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
