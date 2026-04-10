"""harness context-budget — scan task artifacts and estimate token usage."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harness.commands._resolve import resolve_task_dir_readonly

_ARTIFACT_GLOBS = [
    "plan.md",
    "handoff-*.json",
    "session-context.json",
    "build-r*.md",
    "code-eval-r*.md",
    "plan-eval-r*.md",
    "workflow-state.json",
    "ship-metrics.json",
    "feedback-ledger.jsonl",
    "failure-patterns.jsonl",
    "build-notes.md",
]


def _scan_artifacts(task_dir: Path) -> list[tuple[str, int, int]]:
    """Return (filename, chars, estimated_tokens) for each artifact."""
    results: list[tuple[str, int, int]] = []
    for pattern in _ARTIFACT_GLOBS:
        for path in sorted(task_dir.glob(pattern)):
            if not path.is_file():
                continue
            try:
                chars = len(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            results.append((path.name, chars, chars // 4))
    return results


def run_context_budget(*, task: str, as_json: bool = False) -> None:
    """Scan task artifacts and report estimated token usage vs budget."""
    from harness.core.config import HarnessConfig

    cfg = HarnessConfig.load(Path.cwd())
    task_dir = resolve_task_dir_readonly(task)

    if task_dir is None:
        artifacts: list[tuple[str, int, int]] = []
        total_chars = 0
    else:
        artifacts = _scan_artifacts(task_dir)
        total_chars = sum(c for _, c, _ in artifacts)

    budget = cfg.workflow.context_budget_tokens
    total_tokens = total_chars // 4
    over_budget = total_tokens > budget

    if as_json:
        output: dict[str, object] = {
            "task": task,
            "budget_tokens": budget,
            "total_chars": total_chars,
            "total_tokens": total_tokens,
            "over_budget": over_budget,
            "artifacts": [
                {"file": name, "chars": chars, "tokens": tokens}
                for name, chars, tokens in artifacts
            ],
        }
        if over_budget:
            output["suggestion"] = (
                f"Total estimated tokens ({total_tokens}) exceeds budget ({budget}). "
                "Consider archiving old build logs or trimming plan.md."
            )
        typer.echo(json.dumps(output, indent=2))
    else:
        typer.echo(f"Context budget: {budget} tokens (chars/4 estimate, ±20%)")
        typer.echo("")
        if artifacts:
            for name, chars, tokens in artifacts:
                typer.echo(f"  {name:<40s}  {chars:>8,} chars  ~{tokens:>7,} tokens")
            typer.echo("")
        typer.echo(f"  Total: {total_chars:,} chars  ~{total_tokens:,} tokens")
        if over_budget:
            typer.echo("")
            typer.echo(
                f"⚠ OVER BUDGET by ~{total_tokens - budget:,} tokens. "
                "Consider archiving old build logs or trimming plan.md."
            )

    if over_budget:
        raise typer.Exit(code=1)
