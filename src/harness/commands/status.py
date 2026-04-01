"""harness status — Rich terminal dashboard"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from harness.core.config import HarnessConfig, WorkflowConfig
from harness.core.progress import (
    get_recent_blocked,
    get_recent_completed,
    suggest_next_action,
)
from harness.core.state import SessionState
from harness.core.ui import get_ui

log = logging.getLogger("harness.commands.status")

_DEFAULT_PASS_THRESHOLD = WorkflowConfig().pass_threshold


def _load_pass_threshold() -> float:
    """Load pass_threshold from config, falling back to default on any error."""
    try:
        cfg = HarnessConfig.load()
        return cfg.workflow.pass_threshold
    except Exception:
        log.debug("could not load config for pass_threshold, using default", exc_info=True)
        return _DEFAULT_PASS_THRESHOLD


def run_status() -> None:
    """Load state.json and render a Rich panel."""
    from harness import __version__

    ui = get_ui()
    console = ui.console

    ui.banner("status", __version__)

    agents_dir = Path.cwd() / ".agents"
    state = SessionState.load(agents_dir)

    if state.mode == "idle" and not state.completed and not state.blocked:
        ui.info("no active session.")
        return

    pass_threshold = _load_pass_threshold()

    _render_header(console, state)
    _render_current(console, state)
    _render_agents(console, state, agents_dir)
    _render_recent_result(console, state, pass_threshold=pass_threshold)
    _render_next_action(console, state)
    _render_stats(console, state)


def _render_header(console, state: SessionState) -> None:
    mode_str = state.mode.upper() if state.mode != "idle" else "IDLE"
    console.print(Panel(
        f"[bold]HARNESS[/bold] — Session {state.session_id or 'N/A'}",
        subtitle=f"{mode_str} mode",
        border_style="cyber.border",
    ))


def _render_current(console, state: SessionState) -> None:
    if not state.current_task:
        return
    t = state.current_task
    console.print(f"\n[cyber.magenta]Current Task:[/] {t.requirement}")
    console.print(f"  Phase:     {t.state.value}")
    console.print(f"  Iteration: {t.iteration}")
    console.print(f"  Branch:    [cyber.dim]{t.branch}[/]")


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
            f"({recent_done.verdict}, {recent_done.iterations} iterations)"
        )

    if recent_block:
        console.print(
            f"  ✗ {recent_block.requirement} — "
            f"[cyber.red]{recent_block.score:.1f}[/cyber.red] "
            f"({recent_block.verdict})"
        )


def _render_next_action(console, state: SessionState) -> None:
    action = suggest_next_action(state)
    console.print(f"\n[cyber.magenta]Next Action:[/] {action}")


def _render_agents(console, state: SessionState, agents_dir: Path) -> None:
    """Show agent-level runs for the current task from the SQLite registry."""
    if not state.current_task:
        return

    task_id = state.current_task.id
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


def _render_stats(console, state: SessionState) -> None:
    s = state.stats
    console.print(
        f"\n[cyber.dim]Stats: {s.completed} done, {s.blocked} blocked | "
        f"Avg: {s.avg_score:.1f} | Iters: {s.total_iterations}[/]",
    )
