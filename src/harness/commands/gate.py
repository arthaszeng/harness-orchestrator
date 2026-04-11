"""harness gate — Ship-readiness gate check."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from pydantic import ValidationError

from harness.core.gates import CheckStatus, GateVerdict, check_ship_readiness, write_gate_snapshot
from harness.core.ui import get_ui
from harness.core.workflow_state import resolve_task_dir

if TYPE_CHECKING:
    from harness.core.config import HarnessConfig
    from harness.core.trust_engine import TrustProfile

log = logging.getLogger("harness.commands.gate")


def run_gate(*, task: Optional[str] = None) -> None:
    """Check ship-readiness for the current (or specified) task and render results."""
    from harness import __version__
    from harness.core.config import HarnessConfig

    ui = get_ui()
    console = ui.console

    ui.banner("gate", __version__)

    from harness.i18n import t

    agents_dir = Path.cwd() / ".harness-flow"
    task_dir = resolve_task_dir(agents_dir, explicit_task_id=task)
    if task_dir is None:
        suffix = f" for '{task}'" if task else ""
        ui.error(t("gate.no_task", suffix=suffix))
        ui.info(t("gate.no_task_hint"))
        ui.info(t("gate.recovery.no_task"))
        raise typer.Exit(code=1)

    cfg = None
    try:
        cfg = HarnessConfig.load()
        review_gate_mode = cfg.native.review_gate
    except (OSError, ValueError, KeyError, ValidationError):
        ui.warn(t("gate.config_fallback"))
        review_gate_mode = "eng"

    trust_profile = _compute_trust_for_gate(cfg)
    verdict = check_ship_readiness(
        task_dir,
        review_gate_mode=review_gate_mode,
        trust_profile=trust_profile,
    )

    _render_verdict(console, task_dir, verdict)

    try:
        write_gate_snapshot(task_dir, verdict)
    except ValueError as exc:
        ui.error(str(exc))
        raise typer.Exit(code=1) from exc

    if not verdict.passed:
        raise typer.Exit(code=1)


def _compute_trust_for_gate(cfg: "HarnessConfig | None") -> "TrustProfile | None":
    """Best-effort trust profile computation for gate display."""
    try:
        from harness.core.review_calibration import (
            collect_outcomes,
            generate_calibration_report,
        )
        from harness.core.trust_engine import TrustConfig, compute_trust_profile

        trust_cfg = cfg.workflow.trust if cfg is not None else TrustConfig()
        agents_dir = Path.cwd() / ".harness-flow"
        outcomes = collect_outcomes(agents_dir)
        if not outcomes:
            return None
        report = generate_calibration_report(outcomes)
        return compute_trust_profile(report, outcomes, config=trust_cfg)
    except (OSError, ValueError, ValidationError, AttributeError) as exc:
        log.debug("trust profile computation failed: %s", exc, exc_info=True)
        return None


def _gate_check_label(check_name: str) -> str:
    """Map machine check id to user-facing label (i18n)."""
    from harness.i18n import t

    key = f"gate.check.{check_name}"
    label = t(key)
    if label == key:
        log.debug("missing i18n for gate check label: %s", check_name)
        return t("gate.check_fallback", id=check_name)
    return label


def _render_verdict(console, task_dir: Path, verdict: GateVerdict) -> None:
    """Render the gate verdict using Rich."""
    from harness.i18n import t

    task_id = task_dir.name

    status_icon = {
        CheckStatus.PASS: "[cyber.ok]✓[/]",
        CheckStatus.BLOCKED: "[cyber.red]✗[/]",
        CheckStatus.WARNING: "[cyber.warn]![/]",
        CheckStatus.SKIPPED: "[cyber.dim]–[/]",
    }

    console.print(f"\n[cyber.magenta]{t('gate.title')} — {task_id}[/]\n")

    for check in verdict.checks:
        icon = status_icon.get(check.status, "?")
        label = _gate_check_label(check.name)
        reason_str = f"  {check.reason}" if check.reason else ""
        console.print(f"  {icon} {label}{reason_str}")

    console.print()

    if verdict.passed:
        console.print(f"[cyber.ok]{t('gate.pass')}[/]")
    else:
        console.print(f"[cyber.red]{t('gate.blocked', summary=verdict.summary)}[/]")
        console.print(f"[cyber.dim]{t('gate.blocked_hint')}[/]")
        console.print(f"[cyber.dim]{t('gate.recovery.blocked')}[/]")

    if verdict.passed and verdict.score_band is not None and verdict.aggregate_score is not None:
        band_key = f"score_band.{verdict.score_band.value}"
        band_text = t(band_key, score=f"{verdict.aggregate_score:.1f}")
        console.print(f"\n  {band_text}")

    if verdict.trust_level is not None:
        from harness.core.trust_engine import get_trust_level_meta

        meta = get_trust_level_meta(verdict.trust_level)
        sign = "+" if meta.escalation_adjustment >= 0 else ""
        console.print(
            f"\n  [cyber.dim]Trust: {verdict.trust_level.value} — "
            f"escalation adjustment {sign}{meta.escalation_adjustment} "
            f"({meta.description})[/]"
        )

    console.print()
