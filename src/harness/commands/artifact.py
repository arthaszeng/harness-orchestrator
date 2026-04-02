"""harness save-eval / save-build-log — programmatic artifact writers."""

from __future__ import annotations

import json
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
    agents_dir = Path.cwd() / ".harness-flow"
    task_dir = (agents_dir / "tasks" / task).resolve()
    if not task_dir.is_relative_to((agents_dir / "tasks").resolve()):
        raise typer.BadParameter(f"Invalid task ID '{task}': path traversal detected")
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def run_save_eval(
    *,
    task: str,
    kind: str,
    verdict: str,
    score: float,
    body: str,
) -> None:
    """Write evaluation artifact to task directory."""
    from harness.core.artifacts import next_eval_round, save_evaluation
    from harness.core.state import TaskState
    from harness.core.workflow_state import sync_task_state

    ui = get_ui()
    if kind not in {"code", "plan"}:
        raise typer.BadParameter("kind must be 'code' or 'plan'")
    task_dir = _resolve_task_dir(task)
    round_num = next_eval_round(task_dir)

    if body:
        path = save_evaluation(
            task_dir,
            kind=kind,
            round_num=round_num,
            verdict=verdict,
            raw_body=body,
        )
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
            kind=kind,
            round_num=round_num,
            scores=scores,
            verdict=verdict,
        )

    status = (
        "pass"
        if verdict.upper() == "PASS"
        else ("pending" if verdict.upper() == "ITERATE" else "blocked")
    )
    gate_key = "evaluation" if kind == "code" else "plan_review"
    phase = TaskState.EVALUATING if kind == "code" else TaskState.PLANNING
    eval_updates = {f"{kind}_evaluation": f".harness-flow/tasks/{task}/{path.name}"}
    if kind == "code":
        eval_updates["evaluation"] = f".harness-flow/tasks/{task}/{path.name}"
    sync_task_state(
        task_dir,
        artifact_updates=eval_updates,
        gate_updates={
            gate_key: {
                "status": status,
                "reason": f"{path.name} saved with verdict {verdict.upper()}",
            },
        },
        phase=phase,
    )
    ui.info(f"✓ {path.name} → {path}")


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
        artifact_updates={"build_log": f".harness-flow/tasks/{task}/{path.name}"},
        phase=TaskState.BUILDING,
    )
    ui.info(f"✓ {path.name} → {path}")


def run_save_feedback_ledger(
    *,
    task: str,
    body: str,
) -> None:
    """Write feedback-ledger.jsonl to task directory from JSONL body."""
    from harness.core.feedback_ledger import FeedbackItem, save_feedback_ledger

    ui = get_ui()
    task_dir = _resolve_task_dir(task)

    if not body:
        if sys.stdin.isatty():
            raise typer.BadParameter("no --body and stdin is a tty")
        body = sys.stdin.read()

    items: list[FeedbackItem] = []
    for idx, line in enumerate(body.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            items.append(FeedbackItem.model_validate(raw))
        except Exception as exc:  # pragma: no cover - normalized via typer below
            raise typer.BadParameter(f"invalid JSONL at line {idx}: {exc}") from exc

    path = save_feedback_ledger(task_dir, items)
    ui.info(f"✓ {path.name} → {path}")
