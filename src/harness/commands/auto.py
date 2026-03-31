"""harness auto — start the autonomous development loop"""

from __future__ import annotations

from pathlib import Path

import typer

from harness.core.config import HarnessConfig
from harness.core.registry import Registry
from harness.core.state import SessionState, StateMachine
from harness.core.ui import get_ui, init_ui
from harness.drivers.resolver import DriverResolver
from harness.i18n import set_lang, t
from harness.orchestrator.autonomous import run_autonomous


def run_auto(*, resume: bool = False, verbose: bool = False) -> None:
    """Run the Strategist-driven autonomous loop."""
    init_ui(verbose=verbose)
    ui = get_ui()

    project_root = Path.cwd()
    agents_dir = project_root / ".agents"

    if not (agents_dir / "config.toml").exists():
        ui.error(t("auto.no_config"))
        raise typer.Exit(1)

    if not (agents_dir / "vision.md").exists():
        ui.error(t("auto.no_vision"))
        raise typer.Exit(1)

    config = HarnessConfig.load(project_root)
    set_lang(config.project.lang)
    sm = StateMachine(project_root)

    if not resume:
        incomplete = SessionState.detect_incomplete(agents_dir)
        if incomplete:
            do_resume = typer.confirm(
                t("auto.resume_confirm", session_id=incomplete.session_id),
                default=True,
            )
            if do_resume:
                resume = True
            else:
                ui.info("abandoned previous session, starting fresh")

    resolver = DriverResolver(config)
    avail = resolver.available_drivers
    if not any(avail.values()):
        ui.error(t("auto.no_ide"))
        raise typer.Exit(1)

    if not resume:
        sm.start_session("auto")

    sm.clear_stop_signal()

    registry = Registry(agents_dir)
    results = run_autonomous(config, sm, resolver, resume=resume, registry=registry)

    sm.end_session()

    passed = sum(1 for r in results if r.verdict == "PASS")
    blocked = sum(1 for r in results if r.verdict != "PASS")
    ui.info(f"autonomous loop finished: {passed} passed, {blocked} blocked")
