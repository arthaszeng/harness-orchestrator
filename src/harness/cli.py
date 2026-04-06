"""Harness CLI entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from harness import __version__
from harness.core.post_ship_pending import (
    has_pending_post_ship,
    is_auto_reconcile_eligible_subcommand,
)

def _log_debug_error(subcommand: str) -> None:
    """Append a structured error entry to .harness-flow/debug.log.

    Never raises — this is best-effort diagnostics that must not block
    the user's command execution.
    """
    import traceback
    from datetime import datetime, timezone

    try:
        log_dir = Path.cwd() / ".harness-flow"
        if not log_dir.is_dir():
            return
        entry = (
            f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
            f"subcommand={subcommand} cwd={Path.cwd()}\n"
            f"{traceback.format_exc()}\n"
        )
        (log_dir / "debug.log").open("a", encoding="utf-8").write(entry)
    except Exception:
        pass


app = typer.Typer(
    name="harness",
    help="Cursor-native multi-agent development framework",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"harness-flow {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Cursor-native multi-agent development framework."""
    if not is_auto_reconcile_eligible_subcommand(ctx.invoked_subcommand):
        return
    if not has_pending_post_ship(Path.cwd()):
        return
    try:
        from harness.commands.git_lifecycle import run_git_post_ship_reconcile_background

        run_git_post_ship_reconcile_background(max_items=20)
    except Exception:
        _log_debug_error(ctx.invoked_subcommand or "unknown")


@app.command()
def init(
    name: str = typer.Option("", "--name", "-n", help="Project name"),
    ci_command: str = typer.Option("", "--ci", help="CI command (e.g. make test)"),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", "-y", help="Skip interactive wizard, use defaults",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Skip wizard and regenerate artifacts from existing config",
    ),
    auto_commit: bool = typer.Option(
        False, "--auto-commit",
        help="Auto-commit init artifacts when git working tree was clean before init",
    ),
) -> None:
    """Initialize harness in the current project (interactive wizard)."""
    from harness.commands.init import run_init
    run_init(
        name=name,
        ci_command=ci_command,
        non_interactive=non_interactive,
        force=force,
        auto_commit=auto_commit,
    )


@app.command()
def gate(
    task: str = typer.Option(
        "", "--task", "-t",
        help="Explicit task ID (e.g. task-001). Auto-detects if omitted.",
    ),
) -> None:
    """Check ship-readiness gates for the current task"""
    from harness.commands.gate import run_gate
    run_gate(task=task or None)


@app.command()
def status() -> None:
    """Show current progress and status"""
    from harness.commands.status import run_status
    run_status()


@app.command(name="git-preflight")
def git_preflight(
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON result"),
) -> None:
    """Run structured git preflight checks."""
    from harness.commands.git_lifecycle import run_git_preflight
    run_git_preflight(as_json=as_json)


@app.command(name="git-prepare-branch")
def git_prepare_branch(
    task_key: str = typer.Option(..., "--task-key", "-t", help="Task key (e.g. task-001 or PROJ-123)"),
    short_desc: str = typer.Option("", "--short-desc", "-s", help="Short branch description"),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON result"),
) -> None:
    """Create or resume task branch on top of trunk."""
    from harness.commands.git_lifecycle import run_git_prepare_branch
    run_git_prepare_branch(task_key=task_key, short_desc=short_desc, as_json=as_json)


@app.command(name="git-sync-trunk")
def git_sync_trunk(
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON result"),
) -> None:
    """Sync current feature branch with configured trunk."""
    from harness.commands.git_lifecycle import run_git_sync_trunk
    run_git_sync_trunk(as_json=as_json)


@app.command(name="git-post-ship")
def git_post_ship(
    task_key: str = typer.Option("", "--task-key", "-t", help="Task key (e.g. task-001 or PROJ-123)"),
    pr: Optional[int] = typer.Option(None, "--pr", help="Pull request number"),
    branch: str = typer.Option("", "--branch", "-b", help="Feature branch name for PR lookup"),
    wait_merge: bool = typer.Option(
        False,
        "--wait-merge",
        help="Wait for PR merge and auto-run post cleanup when merged",
    ),
    timeout_sec: int = typer.Option(
        86400,
        "--timeout-sec",
        help="Timeout (seconds) when --wait-merge is enabled",
    ),
    poll_interval_sec: int = typer.Option(
        10,
        "--poll-interval-sec",
        help="Polling interval (seconds) when --wait-merge is enabled",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON result"),
) -> None:
    """Run post-ship cleanup after PR merge."""
    from harness.commands.git_lifecycle import run_git_post_ship

    run_git_post_ship(
        task_key=task_key,
        pr=pr,
        branch=branch,
        wait_merge=wait_merge,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
        as_json=as_json,
    )


@app.command(name="git-post-ship-watch")
def git_post_ship_watch(
    task_key: str = typer.Option("", "--task-key", "-t", help="Task key (e.g. task-001 or PROJ-123)"),
    pr: Optional[int] = typer.Option(None, "--pr", help="Pull request number"),
    branch: str = typer.Option("", "--branch", "-b", help="Feature branch name for PR lookup"),
    timeout_sec: int = typer.Option(
        86400,
        "--timeout-sec",
        help="Watcher timeout (seconds) before auto-stop",
    ),
    poll_interval_sec: int = typer.Option(
        10,
        "--poll-interval-sec",
        help="Polling interval (seconds) for merge detection",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON result"),
) -> None:
    """Start detached post-ship watcher and return immediately."""
    from harness.commands.git_lifecycle import run_git_post_ship_watch_start

    run_git_post_ship_watch_start(
        task_key=task_key,
        pr=pr,
        branch=branch,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
        as_json=as_json,
    )


@app.command(name="git-post-ship-reconcile")
def git_post_ship_reconcile(
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON result"),
    max_items: int = typer.Option(20, "--max-items", help="Maximum pending items to process this run"),
) -> None:
    """Reconcile persisted post-ship pending queue."""
    from harness.commands.git_lifecycle import run_git_post_ship_reconcile

    run_git_post_ship_reconcile(as_json=as_json, max_items=max_items)


@app.command(name="save-eval")
def save_eval(
    kind: str = typer.Option(
        "code", "--kind",
        help="Evaluation kind: code or plan",
    ),
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    verdict: str = typer.Option(
        "PASS", "--verdict",
        help="Evaluation verdict: PASS or ITERATE",
    ),
    score: float = typer.Option(
        0.0, "--score",
        help="Weighted average score (0-10)",
    ),
    body: str = typer.Option(
        "", "--body",
        help="Full evaluation body (markdown). If empty, generates minimal template.",
    ),
) -> None:
    """Save evaluation results to task directory (programmatic artifact write)."""
    from harness.commands.artifact import run_save_eval
    if kind not in {"code", "plan"}:
        raise typer.BadParameter("kind must be 'code' or 'plan'")
    run_save_eval(task=task, kind=kind, verdict=verdict, score=score, body=body)


@app.command(name="save-build-log")
def save_build_log(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    body: str = typer.Option(
        "", "--body",
        help="Build log content. If empty, reads from stdin.",
    ),
) -> None:
    """Save build log to task directory (programmatic artifact write)."""
    from harness.commands.artifact import run_save_build_log
    run_save_build_log(task=task, body=body)


@app.command(name="save-ship-metrics")
def save_ship_metrics(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    branch: str = typer.Option("", "--branch", help="Feature branch name"),
    pr_quality_score: float = typer.Option(0.0, "--pr-quality-score", help="PR quality score (0-10)"),
    test_count: int = typer.Option(0, "--test-count", help="Total test cases"),
    eval_rounds: int = typer.Option(1, "--eval-rounds", help="Number of eval rounds"),
    findings_critical: int = typer.Option(0, "--findings-critical", help="Critical findings count"),
    findings_informational: int = typer.Option(0, "--findings-informational", help="Informational findings count"),
    auto_fixed: int = typer.Option(0, "--auto-fixed", help="Auto-fixed findings count"),
    plan_total: int = typer.Option(0, "--plan-total", help="Plan deliverables total"),
    plan_done: int = typer.Option(0, "--plan-done", help="Plan deliverables completed"),
    coverage_pct: int = typer.Option(0, "--coverage-pct", help="Estimated coverage percentage"),
    e2e_total_time_sec: float = typer.Option(
        -1.0,
        "--e2e-total-time-sec",
        help="End-to-end runtime in seconds (auto-infer when negative)",
    ),
    manual_interventions_per_task: float = typer.Option(
        -1.0,
        "--manual-interventions-per-task",
        help="Manual interventions per task (auto-infer when negative)",
    ),
    first_pass_rate: float = typer.Option(
        -1.0,
        "--first-pass-rate",
        help="First-pass rate between 0 and 1 (auto-infer when negative)",
    ),
) -> None:
    """Save ship-metrics.json to task directory (programmatic artifact write)."""
    from harness.commands.artifact import run_save_ship_metrics

    run_save_ship_metrics(
        task=task,
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
        e2e_total_time_sec=None if e2e_total_time_sec < 0 else e2e_total_time_sec,
        manual_interventions_per_task=(
            None
            if manual_interventions_per_task < 0
            else manual_interventions_per_task
        ),
        first_pass_rate=None if first_pass_rate < 0 else first_pass_rate,
    )


@app.command(name="save-feedback-ledger")
def save_feedback_ledger(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    body: str = typer.Option(
        "", "--body",
        help="Feedback ledger JSONL content. If empty, reads from stdin.",
    ),
) -> None:
    """Save feedback-ledger.jsonl to task directory (programmatic artifact write)."""
    from harness.commands.artifact import run_save_feedback_ledger
    run_save_feedback_ledger(task=task, body=body)


@app.command(name="save-intervention-audit")
def save_intervention_audit(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    event_type: str = typer.Option(
        ..., "--event-type",
        help="Intervention type: manual_confirmation | manual_retry | manual_compensation",
    ),
    command: str = typer.Option(
        ..., "--command",
        help="Command or workflow step that required intervention",
    ),
    summary: str = typer.Option(
        "", "--summary",
        help="Short summary of the intervention context",
    ),
) -> None:
    """Save one intervention-audit event to task directory."""
    from harness.commands.artifact import run_save_intervention_audit

    run_save_intervention_audit(task=task, event_type=event_type, command=command, summary=summary)


@app.command()
def update(
    check: bool = typer.Option(
        False, "--check", "-c",
        help="Only check for updates, do not install",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Do not write project artifacts; print init --force reminder for target repo",
    ),
) -> None:
    """Self-update harness and run config migration checks.

    Steps:
    1. Check PyPI for newer version and upgrade via pip
    2. Print project-safe reminder to run `harness init --force` in target repo
    3. Check .harness-flow/config.toml for new/deprecated keys
    """
    from harness.commands.update import run_update
    run_update(check=check, force=force)
