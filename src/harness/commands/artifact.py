"""harness save-eval / save-build-log — programmatic artifact writers."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import typer

from harness.core.ui import get_ui

_TASK_DIR_RE = re.compile(r"^task-\d+$")


def _resolve_task_dir(task: str) -> Path:
    """Resolve task ID to a task directory path, creating if needed.

    Rejects values that don't match ``task-NNN`` to prevent path traversal.
    """
    if not _TASK_DIR_RE.match(task):
        raise typer.BadParameter(
            f"Invalid task ID '{task}': must match task-NNN (e.g. task-001)"
        )
    agents_dir = Path.cwd() / ".agents"
    task_dir = (agents_dir / "tasks" / task).resolve()
    if not task_dir.is_relative_to((agents_dir / "tasks").resolve()):
        raise typer.BadParameter(f"Invalid task ID '{task}': path traversal detected")
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def run_save_eval(
    *,
    task: str,
    verdict: str,
    score: float,
    body: str,
) -> None:
    """Write evaluation artifact to task directory."""
    from harness.core.artifacts import next_eval_round, save_evaluation
    from harness.core.state import TaskState
    from harness.core.workflow_state import sync_task_state

    ui = get_ui()
    task_dir = _resolve_task_dir(task)
    round_num = next_eval_round(task_dir)

    if body:
        path = save_evaluation(task_dir, round_num=round_num, verdict=verdict, raw_body=body)
    else:
        scores = {
            "Design": {"role": "architect", "score": score},
            "Completeness": {"role": "product-owner", "score": score},
            "Quality": {"role": "engineer", "score": score},
            "Regression": {"role": "qa", "score": score},
            "Scope": {"role": "project-manager", "score": score},
        }
        path = save_evaluation(
            task_dir,
            round_num=round_num,
            scores=scores,
            verdict=verdict,
        )

    sync_task_state(
        task_dir,
        artifact_updates={"evaluation": f".agents/tasks/{task}/{path.name}"},
        gate_updates={
            "evaluation": {
                "status": "pass" if verdict.upper() == "PASS" else "blocked",
                "reason": f"{path.name} saved with verdict {verdict.upper()}",
            },
        },
        phase=TaskState.EVALUATING,
    )
    ui.info(f"✓ evaluation-r{round_num}.md → {path}")


def run_save_build_log(
    *,
    task: str,
    body: str,
) -> None:
    """Write build log artifact to task directory."""
    from harness.core.artifacts import save_build_log
    from harness.core.state import TaskState
    from harness.core.workflow_state import sync_task_state

    ui = get_ui()
    task_dir = _resolve_task_dir(task)

    if not body:
        if sys.stdin.isatty():
            ui.warn("no --body and stdin is a tty; writing empty build log")
            body = ""
        else:
            body = sys.stdin.read()

    path = save_build_log(task_dir, body)
    sync_task_state(
        task_dir,
        artifact_updates={"build_log": f".agents/tasks/{task}/{path.name}"},
        phase=TaskState.BUILDING,
    )
    ui.info(f"✓ {path.name} → {path}")
