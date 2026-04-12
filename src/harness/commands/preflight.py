"""harness preflight-bundle — 4-in-1 preflight for build/ship phases.

Combines task resolve + handoff read + session read + context-budget
into a single CLI call, replacing 4 serial invocations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from harness.core.workflow_state import resolve_task_dir


def run_preflight_bundle(
    *,
    task: str | None = None,
    phase: str = "build",
    as_json: bool = True,
) -> None:
    """Run combined preflight checks and return aggregated result."""
    agents_dir = Path.cwd() / ".harness-flow"
    result: dict[str, Any] = {"ok": True, "phase": phase, "errors": []}

    task_dir = resolve_task_dir(agents_dir, explicit_task_id=task)
    if task_dir is None:
        result["ok"] = False
        result["errors"].append("no task directory found")
        if as_json:
            typer.echo(json.dumps(result))
        raise typer.Exit(1)

    result["task_id"] = task_dir.name
    result["task_dir"] = str(task_dir)

    plan_path = task_dir / "plan.md"
    result["has_plan"] = plan_path.exists()

    handoff_data = _read_handoff(task_dir, phase)
    result["handoff"] = handoff_data

    session_data = _read_session(task_dir)
    result["session"] = session_data

    budget_result = _check_context_budget(task_dir)
    result["context_budget_ok"] = not budget_result.get("over_budget", False)
    if budget_result.get("over_budget"):
        result["warnings"] = result.get("warnings", [])
        result["warnings"].append(
            f"context budget exceeded: ~{budget_result['total_tokens']} tokens "
            f"vs {budget_result['budget']} budget"
        )

    file_count_ok = _check_file_count(task_dir)
    result["file_count_ok"] = file_count_ok
    if not file_count_ok:
        result["ok"] = False
        result["errors"].append("task directory has 50+ artifact files")

    ws_path = task_dir / "workflow-state.json"
    if ws_path.exists():
        try:
            ws = json.loads(ws_path.read_text(encoding="utf-8"))
            result["workflow_phase"] = ws.get("phase", "unknown")
        except (json.JSONDecodeError, OSError):
            result["workflow_phase"] = "unknown"
    else:
        result["workflow_phase"] = None

    if as_json:
        typer.echo(json.dumps(result, default=str))
    else:
        status = "✓" if result["ok"] else "✗"
        typer.echo(f"  {status} preflight for {result['task_id']} ({phase})")


def _read_handoff(task_dir: Path, phase: str) -> dict[str, Any] | None:
    """Read the most relevant handoff file."""
    phase_map = {"build": "plan", "eval": "build", "ship": "build"}
    source = phase_map.get(phase, "plan")
    handoff_path = task_dir / f"handoff-{source}.json"

    if not handoff_path.exists():
        return None

    try:
        data = json.loads(handoff_path.read_text(encoding="utf-8"))
        return {
            "source_phase": data.get("source_phase"),
            "summary": data.get("summary", ""),
            "decisions": data.get("decisions", []),
            "risks": data.get("risks", []),
            "open_items": data.get("open_items", []),
        }
    except (json.JSONDecodeError, OSError):
        return None


def _read_session(task_dir: Path) -> dict[str, Any] | None:
    """Read session context if exists."""
    session_path = task_dir / "session-context.json"
    if not session_path.exists():
        return None

    try:
        return json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _check_context_budget(task_dir: Path) -> dict[str, object]:
    """Token-based context budget check using core module."""
    from harness.core.config import HarnessConfig
    from harness.core.context_budget import check_budget

    cfg = HarnessConfig.load(Path.cwd())
    result = check_budget(task_dir, cfg.workflow.context_budget_tokens)
    return {
        "total_tokens": result.total_tokens,
        "budget": result.budget,
        "over_budget": result.over_budget,
    }


def _check_file_count(task_dir: Path, limit: int = 50) -> bool:
    """Check that the task directory doesn't have too many artifact files."""
    artifact_count = sum(1 for f in task_dir.iterdir() if f.is_file())
    return artifact_count < limit
