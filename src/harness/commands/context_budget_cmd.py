"""harness context-budget — scan task artifacts and estimate token usage."""

from __future__ import annotations

import json

import typer

from harness.commands._resolve import resolve_task_dir_readonly
from harness.core.context_budget import BudgetResult, check_budget


def run_context_budget(*, task: str, as_json: bool = False) -> None:
    """Scan task artifacts and report estimated token usage vs budget."""
    from pathlib import Path

    from harness.core.config import HarnessConfig

    cfg = HarnessConfig.load(Path.cwd())
    task_dir = resolve_task_dir_readonly(task)

    budget_tokens = cfg.workflow.context_budget_tokens

    if task_dir is None:
        result = BudgetResult(budget=budget_tokens)
    else:
        result = check_budget(task_dir, budget_tokens)

    if as_json:
        output: dict[str, object] = {
            "task": task,
            "budget_tokens": result.budget,
            "total_chars": result.total_chars,
            "total_tokens": result.total_tokens,
            "over_budget": result.over_budget,
            "artifacts": [
                {"file": f.name, "chars": f.chars, "tokens": f.tokens}
                for f in result.files
            ],
        }
        if result.over_budget:
            output["suggestion"] = (
                f"Total estimated tokens ({result.total_tokens}) exceeds budget ({result.budget}). "
                "Consider archiving old build logs or trimming plan.md."
            )
        typer.echo(json.dumps(output, indent=2))
    else:
        typer.echo(f"Context budget: {result.budget} tokens (chars/4 estimate, ±20%)")
        typer.echo("")
        if result.files:
            for f in result.files:
                typer.echo(f"  {f.name:<40s}  {f.chars:>8,} chars  ~{f.tokens:>7,} tokens")
            typer.echo("")
        typer.echo(f"  Total: {result.total_chars:,} chars  ~{result.total_tokens:,} tokens")
        if result.over_budget:
            typer.echo("")
            typer.echo(
                f"⚠ OVER BUDGET by ~{result.total_tokens - result.budget:,} tokens. "
                "Consider archiving old build logs or trimming plan.md."
            )

    if result.over_budget:
        raise typer.Exit(code=1)
