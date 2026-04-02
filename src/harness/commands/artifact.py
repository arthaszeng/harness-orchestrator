"""harness save-eval / save-build-log — programmatic artifact writers."""

from __future__ import annotations

import sys
from pathlib import Path

from harness.core.ui import get_ui


def _resolve_task_dir(task: str) -> Path:
    """Resolve task ID to a task directory path, creating if needed."""
    agents_dir = Path.cwd() / ".agents"
    task_dir = agents_dir / "tasks" / task
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

    ui = get_ui()
    task_dir = _resolve_task_dir(task)
    round_num = next_eval_round(task_dir)

    if body:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / f"evaluation-r{round_num}.md"
        path.write_text(body, encoding="utf-8")
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

    ui.info(f"✓ evaluation-r{round_num}.md → {path}")


def run_save_build_log(
    *,
    task: str,
    body: str,
) -> None:
    """Write build log artifact to task directory."""
    from harness.core.artifacts import save_build_log

    ui = get_ui()
    task_dir = _resolve_task_dir(task)

    if not body:
        if sys.stdin.isatty():
            ui.warn("no --body and stdin is a tty; writing empty build log")
            body = ""
        else:
            body = sys.stdin.read()

    path = save_build_log(task_dir, body)
    ui.info(f"✓ {path.name} → {path}")
