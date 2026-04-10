"""Harness CLI entry point."""

from __future__ import annotations

from typing import Optional

import typer

from harness import __version__

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
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Cursor-native multi-agent development framework."""


workflow_cli = typer.Typer(help="Workflow hints from local task state (same resolution as gate)")


@workflow_cli.command("next")
def workflow_next_cmd(
    task: str = typer.Option(
        "",
        "--task",
        "-t",
        help="Explicit task ID (e.g. task-001). Auto-detects if omitted.",
    ),
) -> None:
    """Print one HARNESS_NEXT line from workflow-state.json for agents/scripts."""
    from harness.commands.workflow_next import run_workflow_next

    run_workflow_next(task=task or None)


app.add_typer(workflow_cli, name="workflow")

task_cli = typer.Typer(help="Task directory queries (next-id, resolve)")


@task_cli.command("next-id")
def task_next_id_cmd(
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Print the next available task-NNN identifier."""
    from harness.commands.task_info import run_task_next_id

    run_task_next_id(as_json=as_json)


@task_cli.command("resolve")
def task_resolve_cmd(
    task: str = typer.Option(
        "",
        "--task",
        "-t",
        help="Explicit task ID (e.g. task-001). Auto-detects if omitted.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Print the currently active task directory and its state."""
    from harness.commands.task_info import run_task_resolve

    run_task_resolve(task=task or None, as_json=as_json)


@task_cli.command("list")
def task_list_cmd(
    phase: str = typer.Option(
        "",
        "--phase",
        help="Comma-separated phase filter (e.g. done,evaluating)",
    ),
    include_archived: bool = typer.Option(
        False, "--include-archived", help="Include archived tasks",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """List tasks with phase, gates, and artifact count."""
    from harness.commands.task_lifecycle import run_task_list

    run_task_list(phase_filter=phase, include_archived=include_archived, as_json=as_json)


@task_cli.command("archive")
def task_archive_cmd(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID to archive (e.g. task-001)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip phase=done check",
    ),
) -> None:
    """Move a completed task from tasks/ to archive/."""
    from harness.commands.task_lifecycle import run_task_archive

    run_task_archive(task=task, force=force)


@task_cli.command("done")
def task_done_cmd(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID to mark as done (e.g. task-001)",
    ),
) -> None:
    """Mark a task as done (phase=done) and clear blockers."""
    from harness.commands.task_lifecycle import run_task_done

    run_task_done(task=task)


app.add_typer(task_cli, name="task")


@app.command(name="diff-stat")
def diff_stat_cmd(
    as_json: bool = typer.Option(True, "--json/--no-json", help="JSON output (default: on)"),
) -> None:
    """Print branch diff statistics relative to trunk."""
    from harness.commands.diff_stat import run_diff_stat

    run_diff_stat(as_json=as_json)



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
def status(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show technical details (phase, gates, artifact paths, agent runs)",
    ),
    progress_line: bool = typer.Option(
        False,
        "--progress-line",
        help="Emit one machine-readable HARNESS_PROGRESS line (or nothing) and exit",
    ),
) -> None:
    """Show current progress and status"""
    from harness.commands.status import run_status
    run_status(verbose=verbose, progress_line=progress_line)


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
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON result"),
) -> None:
    """Run post-ship cleanup after PR merge."""
    from harness.commands.git_lifecycle import run_git_post_ship

    run_git_post_ship(
        task_key=task_key,
        pr=pr,
        branch=branch,
        as_json=as_json,
    )


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
        case_sensitive=False,
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
    verdict_upper = verdict.upper()
    if verdict_upper not in {"PASS", "ITERATE"}:
        raise typer.BadParameter("verdict must be 'PASS' or 'ITERATE'")
    run_save_eval(task=task, kind=kind, verdict=verdict_upper, score=score, body=body)


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
    _VALID_EVENT_TYPES = {"manual_confirmation", "manual_retry", "manual_compensation"}
    if event_type not in _VALID_EVENT_TYPES:
        raise typer.BadParameter(
            f"event-type must be one of: {', '.join(sorted(_VALID_EVENT_TYPES))}"
        )
    from harness.commands.artifact import run_save_intervention_audit

    run_save_intervention_audit(task=task, event_type=event_type, command=command, summary=summary)


@app.command(name="save-failure")
def save_failure(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    phase: str = typer.Option(
        ..., "--phase",
        help="Pipeline phase where failure occurred (e.g. build, eval, ship)",
    ),
    category: str = typer.Option(
        ..., "--category",
        help="Failure category (e.g. ci-failure, test-failure, lint-error)",
    ),
    summary: str = typer.Option(
        ..., "--summary",
        help="Short summary of the failure",
    ),
    error_output: str = typer.Option(
        "", "--error-output",
        help="Relevant error output (truncated, no secrets)",
    ),
    root_cause: str = typer.Option(
        "", "--root-cause",
        help="Root cause analysis",
    ),
    fix: str = typer.Option(
        "", "--fix",
        help="Fix that was applied",
    ),
    as_json: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON (includes memverse_sync payload)",
    ),
) -> None:
    """Record a failure pattern to task directory (append to failure-patterns.jsonl)."""
    from harness.commands.artifact import run_save_failure

    run_save_failure(
        task=task,
        phase=phase,
        category=category,
        summary=summary,
        error_output=error_output,
        root_cause=root_cause,
        fix_applied=fix,
        as_json=as_json,
    )


@app.command(name="search-failures")
def search_failures(
    query: str = typer.Option(
        "", "--query", "-q",
        help="Search query (normalized substring match against signatures)",
    ),
    category: str = typer.Option(
        "", "--category", "-c",
        help="Filter by category (case-insensitive exact match)",
    ),
    limit: int = typer.Option(
        20, "--limit", "-n",
        help="Maximum number of results (min 1)",
        min=1,
    ),
) -> None:
    """Search failure patterns across all tasks."""
    from harness.commands.artifact import run_search_failures

    run_search_failures(query=query, category=category, limit=limit)


@app.command(name="pr-status")
def pr_status_cmd(
    pr: Optional[int] = typer.Option(None, "--pr", help="Pull request number"),
    branch: str = typer.Option("", "--branch", "-b", help="Branch name for PR lookup"),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Query CI and merge status of a pull request."""
    from harness.commands.pr_lifecycle import run_pr_status

    if pr is None and not branch:
        raise typer.BadParameter("either --pr or --branch is required")
    run_pr_status(pr=pr, branch=branch, as_json=as_json)


@app.command(name="ci-logs")
def ci_logs_cmd(
    pr: Optional[int] = typer.Option(None, "--pr", help="Pull request number"),
    branch: str = typer.Option("", "--branch", "-b", help="Branch name for CI lookup"),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Retrieve logs from failed CI jobs."""
    from harness.commands.pr_lifecycle import run_ci_logs

    if pr is None and not branch:
        raise typer.BadParameter("either --pr or --branch is required")
    run_ci_logs(pr=pr, branch=branch, as_json=as_json)


@app.command(name="worktree-setup")
def worktree_setup() -> None:
    """Create symlinks in a linked worktree to share artifacts from the main tree."""
    from harness.commands.worktree_setup import run_worktree_setup
    run_worktree_setup()


handoff_cli = typer.Typer(help="Structured cross-stage handoff read/write")


@handoff_cli.command("write")
def handoff_write_cmd(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
) -> None:
    """Write handoff from stdin JSON → validate → save."""
    from harness.commands.handoff_cmd import run_handoff_write

    run_handoff_write(task=task)


@handoff_cli.command("read")
def handoff_read_cmd(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    phase: str = typer.Option(
        "", "--phase",
        help="Specific phase to read (plan/build/eval/ship). Latest if omitted.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Read the latest (or phase-specific) handoff for a task."""
    from harness.commands.handoff_cmd import run_handoff_read

    run_handoff_read(task=task, phase=phase or None, as_json=as_json)


app.add_typer(handoff_cli, name="handoff")

session_cli = typer.Typer(help="Intra-phase session context read/write")


@session_cli.command("write")
def session_write_cmd(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
) -> None:
    """Write session context from stdin JSON → validate → save."""
    from harness.commands.session_cmd import run_session_write

    run_session_write(task=task)


@session_cli.command("read")
def session_read_cmd(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Read the current session context for a task."""
    from harness.commands.session_cmd import run_session_read

    run_session_read(task=task, as_json=as_json)


app.add_typer(session_cli, name="session")


@app.command(name="calibrate")
def calibrate_cmd(
    task: str = typer.Option(
        "", "--task", "-t",
        help="Show outcome for a single task (e.g. task-068). Omit for aggregate report.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Review calibration report — prediction vs actual outcome analysis."""
    from harness.commands.calibrate_cmd import run_calibrate

    run_calibrate(task=task or None, as_json=as_json)


@app.command(name="trust")
def trust_cmd(
    task: str = typer.Option(
        "", "--task", "-t",
        help="Explicit task ID for filtering scope. Omit for project-wide profile.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Progressive trust profile — display trust level and advisory adjustments."""
    from harness.commands.trust_cmd import run_trust

    run_trust(task=task or None, as_json=as_json)


@app.command(name="context-budget")
def context_budget_cmd(
    task: str = typer.Option(
        ..., "--task", "-t",
        help="Task ID (e.g. task-001)",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
) -> None:
    """Scan task artifacts and estimate token usage vs budget."""
    from harness.commands.context_budget_cmd import run_context_budget

    run_context_budget(task=task, as_json=as_json)


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
