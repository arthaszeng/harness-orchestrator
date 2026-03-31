"""harness vision — interactive vision create/update"""

from __future__ import annotations

import time
from pathlib import Path

import typer

from harness.core.config import HarnessConfig
from harness.core.ui import get_ui
from harness.drivers.resolver import DriverResolver
from harness.i18n import set_lang, t
from harness.orchestrator.vision_flow import (
    gather_context,
    invoke_advisor,
    write_vision,
)


def run_vision() -> None:
    """Interactive vision flow: user input → advisor → confirm → write."""
    project_root = Path.cwd()
    agents_dir = project_root / ".agents"
    ui = get_ui()

    if not (agents_dir / "config.toml").exists():
        ui.error(t("vision.no_config"))
        raise typer.Exit(1)

    config = HarnessConfig.load(project_root)
    set_lang(config.project.lang)
    resolver = DriverResolver(config)

    avail = resolver.available_drivers
    if not any(avail.values()):
        ui.error(t("vision.no_ide"))
        raise typer.Exit(1)

    ui.info(t("vision.gathering"))
    ctx = gather_context(project_root)
    _show_context_summary(ctx, agents_dir, ui)

    user_input = typer.prompt(t("vision.prompt_input"))

    driver = resolver.resolve("advisor")
    agent_name = resolver.agent_name("advisor")
    advisor_model = resolver.resolve_model("advisor")

    while True:
        t0 = time.monotonic()
        with ui.agent_step(t("vision.advisor_label"), driver.name) as on_out:
            result = invoke_advisor(
                driver, agent_name, ctx, user_input, project_root,
                on_output=on_out,
                model=advisor_model,
            )
        elapsed = time.monotonic() - t0

        if not result.vision_content:
            ui.step_done("[vision] advisor", elapsed, False, t("vision.gen_failed"))
            user_input = typer.prompt(t("vision.rephrase"))
            continue

        ui.step_done("[vision] advisor", elapsed, True, t("vision.gen_ok"))

        if result.questions:
            ui.info(t("vision.questions_intro"))
            for i, q in enumerate(result.questions, 1):
                ui.info(f"  {i}. {q}")
            answers = typer.prompt(t("vision.answer_prompt"), default="")
            if answers.strip():
                user_input = f"{user_input}\n\n{t('vision.supplement', answers=answers)}"
                continue

        ui.console.print()
        ui.console.print(
            f"  [cyber.cyan]{'─' * 50}[/]"
        )
        ui.console.print(f"  [cyber.label]{t('vision.expanded_title')}[/]")
        ui.console.print(
            f"  [cyber.cyan]{'─' * 50}[/]"
        )
        ui.console.print()
        for line in result.vision_content.split("\n"):
            ui.console.print(f"  {line}")
        ui.console.print()
        ui.console.print(
            f"  [cyber.cyan]{'─' * 50}[/]"
        )

        while True:
            choice = typer.prompt(
                t("vision.confirm_prompt"),
                default="y",
            ).strip().lower()
            if choice in ("y", "e", "r"):
                break
            ui.warn(t("vision.invalid_choice"))

        if choice == "y":
            size = write_vision(agents_dir, result.vision_content)
            ui.info(t("vision.written", size=size))
            break
        if choice == "e":
            extra = typer.prompt(t("vision.amend_prompt"))
            user_input = f"{user_input}\n\n{t('vision.user_supplement', extra=extra)}"
        else:
            user_input = typer.prompt(t("vision.regenerate_prompt"))


def _show_context_summary(ctx, agents_dir: Path, ui) -> None:
    """Print a short summary of gathered context."""
    vision_path = agents_dir / "vision.md"
    if vision_path.exists():
        size = vision_path.stat().st_size
        ui.info(t("vision.ctx_vision_exists", size=size))
    else:
        ui.info(t("vision.ctx_vision_missing"))

    reflection_path = agents_dir / "reflection.md"
    if reflection_path.exists():
        ui.info(t("vision.ctx_reflection"))

    progress_path = agents_dir / "progress.md"
    if progress_path.exists():
        ui.info(t("vision.ctx_progress"))

    doc_count = len(ctx.doc_summaries)
    if doc_count:
        ui.info(t("vision.ctx_docs", count=doc_count))
