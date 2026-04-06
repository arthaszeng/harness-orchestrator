"""harness save-eval / save-build-log — programmatic artifact writers."""

from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path
import re

import typer

from harness.core.config import HarnessConfig
from harness.core.task_identity import TaskIdentityResolver
from harness.core.ui import get_ui


def _normalize_literal_escapes(text: str) -> str:
    """Normalize common shell-passed literal escapes when body is single-line.

    Users sometimes pass `--body "# Eval\\n\\n## Verdict: PASS\\n"` expecting
    real newlines. Keep true multi-line input untouched, and only normalize
    escaped newlines/tabs when the payload has no real line breaks.
    """
    if "\n" in text or "\r" in text:
        return text
    if "\\n" not in text and "\\r" not in text and "\\t" not in text:
        return text

    normalized = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    normalized = normalized.replace("\\t", "\t")
    return normalized


def _resolve_task_dir(task: str) -> Path:
    """Resolve task ID to a task directory path, creating if needed.

    Rejects values that don't match configured task identity strategy.
    """
    cfg = HarnessConfig.load(Path.cwd())
    resolver = TaskIdentityResolver.from_config(cfg)
    if not resolver.is_valid_task_key(task):
        raise typer.BadParameter(
            f"Invalid task ID '{task}' for strategy '{resolver.strategy}'"
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
        body = _normalize_literal_escapes(body)
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


def run_save_intervention_audit(
    *,
    task: str,
    event_type: str,
    command: str,
    summary: str = "",
) -> None:
    """Append one intervention-audit event for the given task."""
    from harness.core.intervention_audit import record_intervention_event

    ui = get_ui()
    task_dir = _resolve_task_dir(task)
    ok = record_intervention_event(
        Path.cwd(),
        task_id=task_dir.name,
        event_type=event_type,
        command=command,
        summary=summary,
    )
    if not ok:
        raise typer.BadParameter("failed to write intervention audit event")
    ui.info(f"✓ intervention-audit.jsonl updated for {task_dir.name}")


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        warnings.warn(f"invalid ISO timestamp in workflow state: {ts}", stacklevel=2)
        return None


def _infer_e2e_total_time_sec(task_dir: Path) -> float:
    from harness.core.workflow_state import load_workflow_state

    state = load_workflow_state(task_dir)
    if state is None:
        return 0.0
    start = _parse_iso(state.gates.plan_review.updated_at)
    end = _parse_iso(state.gates.ship_readiness.updated_at)
    if start is None or end is None:
        return 0.0
    delta = (end - start).total_seconds()
    return max(delta, 0.0)


def _infer_manual_interventions_per_task(task_dir: Path) -> float:
    from harness.core.intervention_audit import load_intervention_counts

    counts = load_intervention_counts(task_dir)
    total = float(sum(counts.values()))
    return total


def _infer_first_pass_rate(task_dir: Path) -> float:
    code_eval_rounds: list[int] = []
    for path in task_dir.glob("code-eval-r*.md"):
        match = re.search(r"code-eval-r(\d+)\.md$", path.name)
        if match:
            code_eval_rounds.append(int(match.group(1)))
    for path in task_dir.glob("evaluation-r*.md"):
        match = re.search(r"evaluation-r(\d+)\.md$", path.name)
        if match:
            code_eval_rounds.append(int(match.group(1)))

    if not code_eval_rounds:
        return 0.0
    # First-pass only when there is exactly one code-eval round and it is r1.
    return 1.0 if sorted(set(code_eval_rounds)) == [1] else 0.0


def run_save_ship_metrics(
    *,
    task: str,
    branch: str = "",
    pr_quality_score: float = 0.0,
    test_count: int = 0,
    eval_rounds: int = 1,
    findings_critical: int = 0,
    findings_informational: int = 0,
    auto_fixed: int = 0,
    plan_total: int = 0,
    plan_done: int = 0,
    coverage_pct: int = 0,
    e2e_total_time_sec: float | None = None,
    manual_interventions_per_task: float | None = None,
    first_pass_rate: float | None = None,
) -> None:
    """Write ship-metrics.json with optional efficiency baseline fields."""
    from harness.core.artifacts import save_ship_metrics

    ui = get_ui()
    task_dir = _resolve_task_dir(task)

    if first_pass_rate is not None and not (0.0 <= first_pass_rate <= 1.0):
        raise typer.BadParameter("first_pass_rate must be between 0 and 1")
    if e2e_total_time_sec is not None and e2e_total_time_sec < 0:
        raise typer.BadParameter("e2e_total_time_sec must be >= 0")
    if manual_interventions_per_task is not None and manual_interventions_per_task < 0:
        raise typer.BadParameter("manual_interventions_per_task must be >= 0")

    inferred_e2e = _infer_e2e_total_time_sec(task_dir)
    inferred_manual = _infer_manual_interventions_per_task(task_dir)
    inferred_first_pass = _infer_first_pass_rate(task_dir)

    path = save_ship_metrics(
        task_dir,
        branch=branch,
        pr_quality_score=pr_quality_score,
        test_count=test_count,
        eval_rounds=eval_rounds,
        findings_critical=findings_critical,
        findings_informational=findings_informational,
        auto_fixed=auto_fixed,
        plan_total=plan_total,
        plan_done=plan_done,
        coverage_pct=coverage_pct,
        e2e_total_time_sec=e2e_total_time_sec if e2e_total_time_sec is not None else inferred_e2e,
        manual_interventions_per_task=(
            manual_interventions_per_task
            if manual_interventions_per_task is not None
            else inferred_manual
        ),
        first_pass_rate=first_pass_rate if first_pass_rate is not None else inferred_first_pass,
    )
    ui.info(f"✓ {path.name} → {path}")
