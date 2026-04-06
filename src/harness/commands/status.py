"""harness status — Rich terminal dashboard"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from harness.core.post_ship_pending import has_pending_post_ship
from harness.core.config import HarnessConfig, WorkflowConfig
from harness.core.progress import (
    get_recent_blocked,
    get_recent_completed,
    suggest_next_action,
)
from harness.core.state import SessionState
from harness.core.ui import get_ui
from harness.core.worktree import detect_worktree, extract_task_id_from_branch
from harness.core.workflow_progress_line import format_harness_progress_line
from harness.core.workflow_state import (
    WorkflowState,
    artifact_pairs,
    gate_pairs,
    load_current_workflow_state,
)
from harness.i18n import set_lang, t

log = logging.getLogger("harness.commands.status")

_DEFAULT_PASS_THRESHOLD = WorkflowConfig().pass_threshold


def _emit_progress_line_only() -> None:
    """Stdout: one HARNESS_PROGRESS line when workflow-state is valid; else silent."""
    from harness.core.config import HarnessConfig

    agents_dir = Path.cwd() / ".harness-flow"
    try:
        cfg = HarnessConfig.load(Path.cwd())
        set_lang(cfg.project.lang)
    except Exception:
        set_lang("en")

    state = SessionState.load(agents_dir)
    _, workflow_state = load_current_workflow_state(
        agents_dir,
        session_task_id=state.current_task.id if state.current_task else None,
    )
    if workflow_state is None:
        return
    typer.echo(format_harness_progress_line(phase=workflow_state.phase))


def _load_pass_threshold() -> float:
    """Load pass_threshold from config, falling back to default on any error."""
    try:
        cfg = HarnessConfig.load()
        return cfg.workflow.pass_threshold
    except Exception:
        log.debug("could not load config for pass_threshold, using default", exc_info=True)
        return _DEFAULT_PASS_THRESHOLD


def run_status(*, verbose: bool = False, progress_line: bool = False) -> None:
    """Load state.json and render a Rich panel.

    Default view leads with task-language "next step"; technical rows (phase,
    gates, artifact paths, agent registry) require ``verbose=True``.
    With ``progress_line=True``, print at most one ``HARNESS_PROGRESS`` line
    (or nothing) and return — no Rich dashboard.
    """
    if progress_line:
        _emit_progress_line_only()
        return

    from harness import __version__

    ui = get_ui()
    console = ui.console

    ui.banner("status", __version__)

    agents_dir = Path.cwd() / ".harness-flow"
    state = SessionState.load(agents_dir)
    wt = detect_worktree()
    _, workflow_state = load_current_workflow_state(
        agents_dir,
        session_task_id=state.current_task.id if state.current_task else None,
    )

    if state.mode == "idle" and not state.completed and not state.blocked and workflow_state is None:
        ui.info("no active session.")
        return

    pass_threshold = _load_pass_threshold()

    if wt is not None:
        label = wt.branch or str(wt.git_dir)
        task_hint = extract_task_id_from_branch(wt.branch) if wt.branch else None
        suffix = f" → {task_hint}" if task_hint else ""
        console.print(f"  [dim]\\[Worktree: {label}{suffix}][/dim]")

    action = suggest_next_action(state, workflow_state)
    console.print(Panel(
        action,
        title=f"[bold]{t('status.next_title')}[/]",
        border_style="cyber.border",
    ))

    _render_task_headline(console, state, workflow_state=workflow_state)

    if verbose:
        _render_header(console, state)
        _render_current(console, state, workflow_state=workflow_state)
        _render_agents(console, state, agents_dir, workflow_state=workflow_state)

    _render_recent_result(console, state, pass_threshold=pass_threshold)

    _render_stats(console, state, verbose=verbose)


def _render_task_headline(
    console,
    state: SessionState,
    *,
    workflow_state: WorkflowState | None = None,
) -> None:
    if not state.current_task and workflow_state is None:
        return
    task_label = "…"
    if state.current_task:
        task_label = state.current_task.requirement
    elif workflow_state:
        task_label = workflow_state.active_plan.title or workflow_state.task_id
    console.print(f"\n[cyber.magenta]{t('status.current_task')}:[/] {task_label}")


def _render_header(console, state: SessionState) -> None:
    mode_str = state.mode.upper() if state.mode != "idle" else "IDLE"
    console.print(Panel(
        f"[bold]HARNESS[/bold] — Session {state.session_id or 'N/A'}",
        subtitle=f"{mode_str} mode",
        border_style="cyber.border",
    ))


def _render_current(
    console,
    state: SessionState,
    *,
    workflow_state: WorkflowState | None = None,
) -> None:
    if not state.current_task and workflow_state is None:
        return
    task_label = "current task"
    if state.current_task:
        task_label = state.current_task.requirement
    elif workflow_state:
        task_label = workflow_state.active_plan.title or workflow_state.task_id
    console.print(f"\n[cyber.magenta]Current Task:[/] {task_label}")
    if workflow_state:
        console.print(f"  Task ID:   {workflow_state.task_id}")
        console.print(f"  Phase:     {workflow_state.phase.value}")
        console.print(f"  Iteration: {workflow_state.iteration}")
        console.print(f"  Branch:    [cyber.dim]{workflow_state.branch}[/]")
        if workflow_state.active_plan.title:
            console.print(f"  Plan:      {workflow_state.active_plan.title}")
        if workflow_state.blocker.reason:
            console.print(f"  Blocker:   [cyber.red]{workflow_state.blocker.reason}[/]")
        artifacts = artifact_pairs(workflow_state)
        if artifacts:
            rendered = ", ".join(f"{label}={value}" for label, value in artifacts)
            console.print(f"  Artifacts: [cyber.dim]{rendered}[/]")
        gates = gate_pairs(workflow_state)
        if gates:
            rendered = ", ".join(
                f"{label}={snapshot.status.value}"
                + (f" ({snapshot.reason})" if snapshot.reason else "")
                for label, snapshot in gates
            )
            console.print(f"  Gates:     [cyber.dim]{rendered}[/]")
        console.print(
            f"  State:     [cyber.dim].harness-flow/tasks/{workflow_state.task_id}/workflow-state.json[/]",
        )
        return
    trec = state.current_task
    console.print(f"  Phase:     {trec.state.value}")
    console.print(f"  Iteration: {trec.iteration}")
    console.print(f"  Branch:    [cyber.dim]{trec.branch}[/]")


def _render_recent_result(
    console,
    state: SessionState,
    *,
    pass_threshold: float = _DEFAULT_PASS_THRESHOLD,
) -> None:
    recent_done = get_recent_completed(state)
    recent_block = get_recent_blocked(state)

    if not recent_done and not recent_block:
        return

    console.print("\n[cyber.magenta]Recent Result:[/]")

    if recent_done:
        score_style = "cyber.ok" if recent_done.score >= pass_threshold else "cyber.warn"
        console.print(
            f"  ✓ {recent_done.requirement} — "
            f"[{score_style}]{recent_done.score:.1f}[/{score_style}] "
            f"({recent_done.verdict}, {recent_done.iterations} iterations)",
        )

    if recent_block:
        console.print(
            f"  ✗ {recent_block.requirement} — "
            f"[cyber.red]{recent_block.score:.1f}[/cyber.red] "
            f"({recent_block.verdict})",
        )


def _render_agents(
    console,
    state: SessionState,
    agents_dir: Path,
    *,
    workflow_state: WorkflowState | None = None,
) -> None:
    """Show agent-level runs for the current task from the SQLite registry."""
    task_id = state.current_task.id if state.current_task else ""
    if not task_id and workflow_state:
        task_id = workflow_state.task_id
    if not task_id:
        return
    db_path = agents_dir / "registry.db"
    if not db_path.exists():
        return

    try:
        from harness.core.registry import Registry
        registry = Registry(agents_dir)
        runs = registry.get_by_task(task_id)
        registry.close()
    except Exception:
        log.debug("could not read registry for status", exc_info=True)
        return

    if not runs:
        return

    table = Table(
        title=f"Agents ({task_id})",
        show_header=True,
        header_style="bold",
        border_style="cyber.border",
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=5)
    table.add_column("Role", min_width=10)
    table.add_column("Status", min_width=9)
    table.add_column("Elapsed", justify="right", min_width=7)
    table.add_column("Detail", style="dim")

    for r in runs:
        status_style = {
            "completed": "cyber.ok",
            "failed": "cyber.red",
            "running": "cyber.warn",
        }.get(r.status, "")

        elapsed_str = f"{r.elapsed_ms / 1000:.1f}s" if r.elapsed_ms else "..."
        detail = ""
        if r.status == "failed" and r.exit_code is not None:
            detail = f"exit={r.exit_code}"
        if r.error:
            detail = r.error[:60]

        table.add_row(
            f"#{r.id}",
            r.role,
            f"[{status_style}]{r.status}[/{status_style}]" if status_style else r.status,
            elapsed_str,
            detail,
        )

    console.print()
    console.print(table)


def _render_stats(console, state: SessionState, *, verbose: bool) -> None:
    s = state.stats
    if verbose:
        reconcile_mode = "hit" if has_pending_post_ship(Path.cwd()) else "skip"
        console.print(
            f"\n[cyber.dim]Stats: {s.completed} done, {s.blocked} blocked | "
            f"Avg: {s.avg_score:.1f} | Iters: {s.total_iterations} | "
            f"Auto reconcile: {reconcile_mode}[/]",
        )
        return
    line = t(
        "status.stats_brief",
        completed=s.completed,
        blocked=s.blocked,
        avg=s.avg_score,
    )
    pending = has_pending_post_ship(Path.cwd())
    rec = t("status.stats_reconcile_on") if pending else t("status.stats_reconcile_off")
    console.print(f"\n[cyber.dim]{line} | {rec}[/]")
