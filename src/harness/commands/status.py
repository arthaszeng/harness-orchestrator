"""harness status — Rich terminal dashboard"""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from harness.core.progress import (
    get_recent_blocked,
    get_recent_completed,
    is_resumable,
    suggest_next_action,
)
from harness.core.state import SessionState
from harness.core.ui import get_ui


def run_status() -> None:
    """Load state.json and render a Rich panel."""
    ui = get_ui()
    console = ui.console

    agents_dir = Path.cwd() / ".agents"
    state = SessionState.load(agents_dir)

    if state.mode == "idle" and not state.completed and not state.blocked:
        ui.info("no active session. run `harness run` or `harness auto` to begin.")
        return

    _render_header(console, state)
    _render_current(console, state)
    _render_recent_result(console, state)
    _render_resume(console, state)
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


def _render_recent_result(console, state: SessionState) -> None:
    recent_done = get_recent_completed(state)
    recent_block = get_recent_blocked(state)

    if not recent_done and not recent_block:
        return

    console.print("\n[cyber.magenta]Recent Result:[/]")

    if recent_done:
        score_style = "cyber.ok" if recent_done.score >= 3.5 else "cyber.warn"
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


def _render_resume(console, state: SessionState) -> None:
    if not is_resumable(state):
        return
    cmd = "harness run --resume" if state.mode == "run" else "harness auto --resume"
    console.print(f"\n[cyber.warn]Resume:[/] session `{state.session_id}` can be resumed")
    console.print(f"  → [bold]`{cmd}`[/bold]")


def _render_next_action(console, state: SessionState) -> None:
    action = suggest_next_action(state)
    console.print(f"\n[cyber.magenta]Next Action:[/] {action}")


def _render_stats(console, state: SessionState) -> None:
    s = state.stats
    console.print(
        f"\n[cyber.dim]Stats: {s.completed} done, {s.blocked} blocked | "
        f"Avg: {s.avg_score:.1f} | Iters: {s.total_iterations}[/]",
    )
