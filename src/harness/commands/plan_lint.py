"""harness plan-lint — plan.md structural validation."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harness.core.plan_lint import lint_plan
from harness.core.workflow_state import resolve_task_dir


def run_plan_lint(*, task: str | None = None, as_json: bool = True) -> None:
    """Validate plan.md structure for the specified task."""
    agents_dir = Path.cwd() / ".harness-flow"
    task_dir = resolve_task_dir(agents_dir, explicit_task_id=task)

    if task_dir is None:
        msg = f"no task directory found{' for ' + task if task else ''}"
        if as_json:
            typer.echo(json.dumps({"error": msg}))
        else:
            typer.echo(f"Error: {msg}", err=True)
        raise typer.Exit(1)

    plan_path = task_dir / "plan.md"
    result = lint_plan(plan_path)

    if as_json:
        typer.echo(json.dumps(result.to_dict()))
    else:
        if result.valid:
            typer.echo(f"  ✓ plan.md valid ({result.deliverable_count} deliverables)")
        else:
            typer.echo("  ✗ plan.md invalid:")
            for err in result.errors:
                typer.echo(f"    - [{err.code}] {err.message}")
