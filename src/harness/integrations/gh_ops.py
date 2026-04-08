"""GitHub CLI (``gh``) operations — unified subprocess wrapper.

All ``gh`` invocations go through :func:`run_gh_result` so that timeout,
error-code, and JSON-parse conventions stay consistent across
:mod:`~harness.core.pr_monitor` and :mod:`~harness.core.post_ship`.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from harness.integrations.git_ops import GitOperationResult

log = logging.getLogger(__name__)


def run_gh_result(
    args: list[str],
    cwd: Path,
    *,
    timeout: int = 30,
    code_on_error: str = "GH_COMMAND_FAILED",
    message: str = "",
) -> GitOperationResult:
    """Run a ``gh`` CLI command and return a structured result."""
    full_args = ["gh", *args]
    try:
        completed = subprocess.run(
            full_args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return GitOperationResult(
            ok=False,
            code="GH_NOT_FOUND",
            message="gh CLI is not installed or not on PATH",
        )
    except subprocess.TimeoutExpired as exc:
        return GitOperationResult(
            ok=False,
            code="GH_TIMEOUT",
            message=f"gh {' '.join(args)} timed out after {timeout}s",
            stderr=str(exc),
            context={"args": " ".join(args)},
        )
    except OSError as exc:
        return GitOperationResult(
            ok=False,
            code="GH_IO_ERROR",
            message=f"unable to execute gh {' '.join(args)}",
            stderr=str(exc),
            context={"args": " ".join(args)},
        )

    if completed.returncode != 0:
        return GitOperationResult(
            ok=False,
            code=code_on_error,
            message=message or f"gh {' '.join(args)} failed",
            stdout=completed.stdout,
            stderr=completed.stderr,
            context={"args": " ".join(args), "returncode": str(completed.returncode)},
        )
    return GitOperationResult(
        ok=True,
        code="OK",
        stdout=completed.stdout,
        stderr=completed.stderr,
        context={"args": " ".join(args)},
    )


def run_gh_json(
    args: list[str],
    cwd: Path,
    *,
    timeout: int = 30,
    code_on_error: str = "GH_COMMAND_FAILED",
) -> tuple[GitOperationResult, dict | list | None]:
    """Run ``gh`` and parse the stdout as JSON.

    Returns ``(result, parsed)`` where *parsed* is ``None`` when ``result.ok``
    is ``False`` or JSON parsing fails.
    """
    result = run_gh_result(args, cwd, timeout=timeout, code_on_error=code_on_error)
    if not result.ok:
        return result, None
    try:
        parsed = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        return (
            GitOperationResult(
                ok=False,
                code="GH_JSON_PARSE_FAILED",
                message="failed to parse gh JSON output",
                stdout=result.stdout,
                stderr=str(exc),
            ),
            None,
        )
    return result, parsed


# ── PR helpers ───────────────────────────────────────────────────


@dataclass(frozen=True)
class PrCheckRun:
    """A single CI check associated with a PR."""

    name: str
    status: str
    conclusion: str
    workflow_name: str = ""


@dataclass(frozen=True)
class PrStatusSummary:
    """Aggregated PR CI and merge status."""

    pr_number: int
    ci_status: str  # "pass" | "fail" | "pending"
    mergeable: bool
    conflict: bool
    checks: list[PrCheckRun] = field(default_factory=list)


def gh_pr_status(
    cwd: Path,
    *,
    pr_number: int | None = None,
    branch: str | None = None,
    timeout: int = 30,
) -> tuple[GitOperationResult, PrStatusSummary | None]:
    """Query the CI and merge status of a pull request.

    Exactly one of *pr_number* or *branch* must be provided.
    """
    if pr_number is None and not (branch and branch.strip()):
        return (
            GitOperationResult(
                ok=False,
                code="PR_SELECTOR_REQUIRED",
                message="either pr_number or branch must be provided",
            ),
            None,
        )

    args = ["pr", "view"]
    if pr_number is not None:
        args.append(str(pr_number))
    else:
        args.extend(["--head", branch.strip()])  # type: ignore[union-attr]
    args.extend([
        "--json",
        "number,state,mergeable,statusCheckRollup",
    ])

    result, payload = run_gh_json(args, cwd, timeout=timeout, code_on_error="PR_STATUS_FAILED")
    if not result.ok or payload is None:
        return result, None

    if not isinstance(payload, dict):
        return (
            GitOperationResult(ok=False, code="PR_STATUS_UNEXPECTED", message="unexpected payload shape"),
            None,
        )

    number = int(payload.get("number", pr_number or 0))
    mergeable_raw = str(payload.get("mergeable", "")).upper()
    conflict = mergeable_raw == "CONFLICTING"
    mergeable = mergeable_raw == "MERGEABLE"

    checks: list[PrCheckRun] = []
    for item in payload.get("statusCheckRollup", []) or []:
        checks.append(PrCheckRun(
            name=item.get("name", item.get("context", "")),
            status=str(item.get("status", "")).lower(),
            conclusion=str(item.get("conclusion", "")).lower(),
            workflow_name=str(item.get("workflowName", "")),
        ))

    if not checks:
        ci_status = "pending"
    elif all(c.conclusion == "success" for c in checks):
        ci_status = "pass"
    elif any(c.conclusion in ("failure", "cancelled", "timed_out") for c in checks):
        ci_status = "fail"
    else:
        ci_status = "pending"

    summary = PrStatusSummary(
        pr_number=number,
        ci_status=ci_status,
        mergeable=mergeable,
        conflict=conflict,
        checks=checks,
    )
    return result, summary


@dataclass(frozen=True)
class FailedJobLog:
    """Log excerpt from a single failed CI job."""

    name: str
    conclusion: str
    log_tail: str


def gh_ci_logs(
    cwd: Path,
    *,
    pr_number: int | None = None,
    branch: str | None = None,
    max_lines: int = 200,
    timeout: int = 60,
) -> tuple[GitOperationResult, list[FailedJobLog]]:
    """Retrieve logs for failed CI jobs on a PR.

    First lists runs, finds the latest failed run, then fetches its failed
    job logs.  Returns ``(result, [FailedJobLog, ...])``.

    If only *pr_number* is given, resolves the head branch first.
    """
    resolved_branch = branch.strip() if branch and branch.strip() else None

    if resolved_branch is None and pr_number is not None:
        pr_result, pr_data = run_gh_json(
            ["pr", "view", str(pr_number), "--json", "headRefName"],
            cwd,
            timeout=timeout,
            code_on_error="CI_PR_RESOLVE_FAILED",
        )
        if pr_result.ok and isinstance(pr_data, dict):
            resolved_branch = pr_data.get("headRefName")

    if resolved_branch is None and pr_number is None:
        return (
            GitOperationResult(
                ok=False,
                code="CI_SELECTOR_REQUIRED",
                message="either pr_number or branch must be provided",
            ),
            [],
        )

    # Step 1: find the latest failed run
    args = ["run", "list", "--limit", "5", "--json", "databaseId,conclusion,status,headBranch"]
    if resolved_branch:
        args.extend(["--branch", resolved_branch])
    result, runs = run_gh_json(args, cwd, timeout=timeout, code_on_error="CI_RUN_LIST_FAILED")
    if not result.ok or runs is None:
        return result, []

    if not isinstance(runs, list):
        return (
            GitOperationResult(ok=False, code="CI_RUN_LIST_UNEXPECTED", message="unexpected run list shape"),
            [],
        )

    failed_run_id: int | None = None
    for run in runs:
        if run.get("conclusion") in ("failure", "cancelled", "timed_out"):
            failed_run_id = int(run["databaseId"])
            break

    if failed_run_id is None:
        return (
            GitOperationResult(ok=True, code="NO_FAILED_RUNS", message="no recent failed runs found"),
            [],
        )

    # Step 2: get the failed log
    log_result = run_gh_result(
        ["run", "view", str(failed_run_id), "--log-failed"],
        cwd,
        timeout=timeout,
        code_on_error="CI_LOG_FETCH_FAILED",
    )
    if not log_result.ok:
        return log_result, []

    jobs = _parse_log_output(log_result.stdout, max_lines=max_lines)
    return log_result, jobs


def _parse_log_output(raw: str, *, max_lines: int = 200) -> list[FailedJobLog]:
    """Parse ``gh run view --log-failed`` output into per-job excerpts.

    The output format is tab-separated: ``job_name\\tstep\\tline_content``.
    """
    job_lines: dict[str, list[str]] = {}
    for line in raw.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        job_name = parts[0]
        content = parts[-1] if len(parts) == 3 else parts[1]
        job_lines.setdefault(job_name, []).append(content)

    result: list[FailedJobLog] = []
    for name, lines in job_lines.items():
        tail = lines[-max_lines:] if len(lines) > max_lines else lines
        result.append(FailedJobLog(
            name=name,
            conclusion="failure",
            log_tail="\n".join(tail),
        ))
    return result
