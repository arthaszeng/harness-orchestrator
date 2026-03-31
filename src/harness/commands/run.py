"""harness run — execute a single development task"""

from __future__ import annotations

from pathlib import Path

import typer

from harness import __version__
from harness.core.config import HarnessConfig
from harness.core.registry import Registry
from harness.core.state import SessionState, StateMachine
from harness.core.ui import get_ui, init_ui
from harness.drivers.resolver import DriverResolver
from harness.i18n import set_lang, t
from harness.orchestrator.workflow import run_single_task


def run_task(*, requirement: str, resume: bool = False, verbose: bool = False) -> None:
    """Run the full workflow for a single task."""
    init_ui(verbose=verbose)
    ui = get_ui()

    project_root = Path.cwd()
    agents_dir = project_root / ".agents"

    if not (agents_dir / "config.toml").exists():
        ui.error(t("run.no_config"))
        raise typer.Exit(1)

    config = HarnessConfig.load(project_root)
    set_lang(config.project.lang)
    sm = StateMachine(project_root)

    if resume:
        incomplete = SessionState.detect_incomplete(agents_dir)
        if incomplete and incomplete.current_task:
            ui.info(f"resuming: {incomplete.current_task.requirement}")
            requirement = incomplete.current_task.requirement
        else:
            ui.info("no resumable task, starting fresh")
            resume = False

    resolver = DriverResolver(config)
    avail = resolver.available_drivers
    if not any(avail.values()):
        ui.error(t("run.no_ide"))
        raise typer.Exit(1)

    ui.banner("run", __version__)
    ui.system_status(avail)

    if not resume:
        sm.start_session("run")

    sm.clear_stop_signal()

    registry = Registry(agents_dir)
    result = run_single_task(
        config, sm, resolver, requirement,
        resume=resume,
        registry=registry,
    )

    sm.end_session()

    if result.verdict == "PASS":
        ui.info(f"task passed! score: {result.score:.1f}, iterations: {result.iterations}")
    else:
        ui.error(f"task blocked. feedback: {result.feedback[:300]}")
        raise typer.Exit(1)
