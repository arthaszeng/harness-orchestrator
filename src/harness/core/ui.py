"""Cyberpunk-style terminal UI — unified output layer.

All Harness terminal output goes through HarnessUI.
By default, agent subprocess output is shown as a scrolling tail (last 5 lines),
then collapses to a one-line summary when done. --verbose restores full streaming.
"""

from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Generator

from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.theme import Theme

if TYPE_CHECKING:
    pass

# ── Cyber color theme ───────────────────────────────────────────

CYBER_THEME = Theme({
    "cyber.cyan": "bold #00ffff",
    "cyber.magenta": "bold #ff00ff",
    "cyber.green": "bold #39ff14",
    "cyber.yellow": "bold #ffff00",
    "cyber.red": "bold #ff0040",
    "cyber.dim": "dim #888888",
    "cyber.label": "#ff00ff",
    "cyber.ok": "#39ff14",
    "cyber.fail": "#ff0040",
    "cyber.warn": "#ffff00",
    "cyber.border": "#00ffff",
    "cyber.header": "bold #00ffff",
})

# ── ASCII Banner ──────────────────────────────────────────────────

_BANNER = r"""
 [cyber.cyan]██╗  ██╗ █████╗ ██████╗ ███╗   ██╗███████╗███████╗███████╗[/]
 [cyber.cyan]██║  ██║██╔══██╗██╔══██╗████╗  ██║██╔════╝██╔════╝██╔════╝[/]
 [cyber.magenta]███████║███████║██████╔╝██╔██╗ ██║█████╗  ███████╗███████╗[/]
 [cyber.magenta]██╔══██║██╔══██║██╔══██╗██║╚██╗██║██╔══╝  ╚════██║╚════██║[/]
 [cyber.cyan]██║  ██║██║  ██║██║  ██║██║ ╚████║███████╗███████║███████║[/]
 [cyber.dim]╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝╚══════╝[/]"""

_TAIL_LINES = 5


# ── Scrolling-tail Rich renderable ──────────────────────────────

class _TailRenderable:
    """Rich Live renderable for the scrolling tail of agent output."""

    def __init__(self, label: str, runtime_name: str, start: float) -> None:
        self.label = label
        self.runtime_name = runtime_name
        self.start = start
        self.lines: deque[str] = deque(maxlen=_TAIL_LINES)
        self.line_count = 0

    def add_line(self, line: str) -> None:
        self.lines.append(line.rstrip())
        self.line_count += 1

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        elapsed = time.monotonic() - self.start
        for line in self.lines:
            truncated = line[:options.max_width - 6] if len(line) > options.max_width - 6 else line
            yield Text(f"    ┊ {truncated}", style="cyber.dim")
        yield Text(
            f"    ┊ [{self.line_count} lines / {elapsed:.0f}s]",
            style="cyber.dim",
        )


# ── Main UI class ───────────────────────────────────────────────

class HarnessUI:
    """Harness cyberpunk terminal UI."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.console = Console(stderr=True, theme=CYBER_THEME, highlight=False)

    # ── Banner & Session ──

    def banner(self, mode: str, version: str) -> None:
        self.console.print(_BANNER)
        self.console.print(
            f"                    [cyber.dim]v{version} // {mode} mode[/]",
        )
        self.console.print()

    def system_status(self) -> None:
        content = "  IDE :: Cursor [cyber.ok]ON[/]"
        self.console.print(Panel(
            content,
            title="[cyber.header]SYSTEM[/]",
            border_style="cyber.border",
            padding=(0, 1),
        ))
        self.console.print()

    def session_end(self, completed: int, blocked: int, avg_score: float) -> None:
        content = (
            f"  completed [cyber.green]{completed}[/]"
            f"  │  blocked [cyber.red]{blocked}[/]"
            f"  │  avg [cyber.cyan]{avg_score:.1f}[/]"
        )
        self.console.print(Panel(
            content,
            title="[cyber.header]SESSION END[/]",
            border_style="cyber.border",
            padding=(0, 1),
        ))

    # ── Task ──

    def task_panel(self, task_id: str, requirement: str, branch: str) -> None:
        content = (
            f"  [cyber.label]TASK[/]    {task_id}\n"
            f"  [cyber.label]OBJ[/]     {requirement}\n"
            f"  [cyber.label]BRANCH[/]  [cyber.dim]{branch}[/]"
        )
        self.console.print()
        self.console.print(Panel(
            content,
            border_style="cyber.border",
            padding=(0, 1),
        ))

    def iteration_header(self, n: int, max_n: int) -> None:
        self.console.print()
        self.console.print(
            Rule(
                f"[cyber.magenta]◆ Iteration {n}/{max_n}[/]",
                style="cyber.dim",
            ),
        )

    def task_complete(self, task_id: str, score: float, elapsed: float) -> None:
        self.console.print()
        self.console.print(Rule(style="cyber.green"))
        self.console.print(
            f"  [cyber.green]✓ TASK COMPLETE[/]  "
            f"{task_id} // [cyber.cyan]{score:.1f}[/] // [cyber.dim]{elapsed:.0f}s[/]",
        )
        self.console.print(Rule(style="cyber.green"))

    def task_blocked(self, task_id: str, max_iter: int, *, reason: str = "") -> None:
        self.console.print()
        self.console.print(Rule(style="cyber.red"))
        detail = reason or f"max iterations {max_iter}"
        self.console.print(
            f"  [cyber.red]✗ TASK BLOCKED[/]  "
            f"{task_id} // [cyber.dim]{detail}[/]",
        )
        self.console.print(Rule(style="cyber.red"))

    # ── Agent steps ──

    @contextmanager
    def agent_step(
        self, label: str, runtime_name: str,
    ) -> Generator[Callable[[str], None] | None, None, None]:
        """Context manager for an agent step.

        Default mode: Rich Live shows a scrolling tail, then clears when done.
        Verbose mode: yields None; caller handles raw stderr.
        """
        self.console.print(
            f"  [cyber.magenta]▸[/] [cyber.label]{label}[/] "
            f"[cyber.dim]// {runtime_name}[/]",
        )

        if self.verbose:
            yield None
            return

        start = time.monotonic()
        tail = _TailRenderable(label, runtime_name, start)

        def on_output(line: str) -> None:
            tail.add_line(line)

        try:
            with Live(
                tail,
                console=self.console,
                refresh_per_second=4,
                transient=True,
            ):
                yield on_output
        except Exception:
            yield on_output

    def step_done(
        self, label: str, elapsed: float, success: bool, detail: str = "",
        *, fail_tail: list[str] | None = None,
    ) -> None:
        if success:
            self.console.print(
                f"  [cyber.ok]✓[/] [cyber.label]{label}[/] "
                f"[cyber.dim]({elapsed:.0f}s)[/]"
                f"{'  ' + detail if detail else ''}",
            )
        else:
            self.console.print(
                f"  [cyber.fail]✗[/] [cyber.label]{label}[/] "
                f"[cyber.dim]({elapsed:.0f}s)[/]"
                f"{'  ' + detail if detail else ''}",
            )
            if fail_tail:
                for line in fail_tail[-3:]:
                    self.console.print(f"    [cyber.dim]┊ {line.rstrip()}[/]")

    # ── Generic messages ──

    def info(self, msg: str) -> None:
        self.console.print(f"  [cyber.dim]{msg}[/]")

    def warn(self, msg: str) -> None:
        self.console.print(f"  [cyber.warn]![/] {msg}")

    def error(self, msg: str) -> None:
        self.console.print(f"  [cyber.fail]✗[/] {msg}", style="")

    def safety_stop(self, reason: str) -> None:
        self.console.print(f"\n  [cyber.yellow]▪ [safety][/] {reason}")


# ── Singleton ─────────────────────────────────────────────────────

_ui: HarnessUI | None = None


def init_ui(verbose: bool = False) -> HarnessUI:
    """Initialize the global UI singleton (called from CLI entry)."""
    global _ui
    _ui = HarnessUI(verbose=verbose)
    return _ui


def get_ui() -> HarnessUI:
    """Return the global UI; create a default instance if unset."""
    global _ui
    if _ui is None:
        _ui = HarnessUI()
    return _ui
