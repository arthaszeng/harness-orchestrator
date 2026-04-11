"""harness status — Rich terminal dashboard"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from harness.core.progress import suggest_next_action
from harness.core.ui import get_ui
from harness.core.workflow_progress_line import format_harness_progress_line
from harness.core.workflow_state import (
    WorkflowState,
    artifact_pairs,
    gate_pairs,
    load_current_workflow_state,
)
from harness.i18n import apply_project_lang_from_cwd, t

log = logging.getLogger("harness.commands.status")


def _emit_progress_line_only() -> None:
    """Stdout: one HARNESS_PROGRESS line when workflow-state is valid; else silent."""
    agents_dir = Path.cwd() / ".harness-flow"
    apply_project_lang_from_cwd()

    _, workflow_state = load_current_workflow_state(agents_dir)
    if workflow_state is None:
        return
    typer.echo(format_harness_progress_line(phase=workflow_state.phase))


def run_status(*, verbose: bool = False, progress_line: bool = False) -> None:
    """Load workflow state and render a Rich panel.

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
    _, workflow_state = load_current_workflow_state(agents_dir)

    if workflow_state is None:
        ui.info(t("status.no_session"))
        return

    action = suggest_next_action(workflow_state)
    console.print(Panel(
        action,
        title=f"[bold]{t('status.next_title')}[/]",
        border_style="cyber.border",
    ))

    _render_task_headline(console, workflow_state)

    if verbose:
        _render_current(console, workflow_state)
        _render_agents(console, agents_dir, workflow_state)

    console.print()


def _render_task_headline(
    console,
    workflow_state: WorkflowState,
) -> None:
    task_label = workflow_state.active_plan.title or workflow_state.task_id
    console.print(f"\n[cyber.magenta]{t('status.current_task')}:[/] {task_label}")


def _render_current(
    console,
    workflow_state: WorkflowState,
) -> None:
    task_label = workflow_state.active_plan.title or workflow_state.task_id
    console.print(f"\n[cyber.magenta]{t('status.current_task')}:[/] {task_label}")
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


def _render_agents(
    console,
    agents_dir: Path,
    workflow_state: WorkflowState,
) -> None:
    """Show agent-level runs for the current task from the SQLite registry."""
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
