"""CLI wrapper for recording review outcomes (post-merge calibration data)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from harness.core.ui import get_ui

log = logging.getLogger(__name__)


def _create_manager(project_root: Path):
    from harness.core.post_ship import PostShipManager

    return PostShipManager.create(project_root)


def run_record_outcome(
    *,
    task: str,
    pr: int | None = None,
    branch: str = "",
    as_json: bool = False,
) -> None:
    """Record actual outcome for a task's review-outcome.json."""
    from harness.commands.artifact import _resolve_task_dir
    from harness.core.review_calibration import load_review_outcome

    ui = get_ui()
    task_dir = _resolve_task_dir(task)

    manager = _create_manager(Path.cwd())
    manager.record_outcome(
        task_dir=task_dir,
        pr_number=pr,
        branch=branch or None,
    )

    outcome = load_review_outcome(task_dir)
    if outcome is None:
        ui.warn(f"review-outcome.json not found after recording for {task}")
        if as_json:
            typer.echo(json.dumps({"ok": False, "task": task, "reason": "no outcome file"}))
        return

    if as_json:
        typer.echo(json.dumps(outcome.model_dump(), indent=2, default=str))
    else:
        ci = outcome.outcome.ci_passed
        revert = outcome.outcome.has_revert
        ui.info(
            f"✓ review outcome recorded for {task}"
            f" (ci_passed={ci}, has_revert={revert})"
        )
