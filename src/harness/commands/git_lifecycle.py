"""harness git lifecycle helper commands."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.core.intervention_audit import record_intervention_event
from harness.core.post_ship import PostShipManager
from harness.core.post_ship_pending import (
    enqueue_pending_post_ship,
    has_pending_post_ship,
    reconcile_pending_post_ship,
)
from harness.core.post_ship_watcher import PostShipWatcher
from harness.integrations.git_ops import GitOperationResult


def run_git_preflight(*, as_json: bool = False) -> None:
    from harness.core.config import HarnessConfig
    from harness.i18n import set_lang, t

    manager = BranchLifecycleManager.create(Path.cwd())
    result = manager.preflight_repo_state()
    payload = {
        "ok": result.ok,
        "code": result.code,
        "message": result.diagnostic,
        "context": result.context,
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"[{result.code}] {result.diagnostic}")
    if not result.ok:
        try:
            cfg = HarnessConfig.load(Path.cwd())
            set_lang(cfg.project.lang)
        except Exception:
            set_lang("en")
        key = f"git_preflight.recovery.{result.code}"
        msg = t(key)
        if msg == key:
            msg = t("git_preflight.recovery.generic")
        typer.echo(msg, err=True)
        raise typer.Exit(code=1)


def run_git_prepare_branch(*, task_key: str, short_desc: str = "", as_json: bool = False) -> None:
    manager = BranchLifecycleManager.create(Path.cwd())
    result = manager.prepare_task_branch(task_key, short_desc)
    payload = {
        "ok": result.ok,
        "code": result.code,
        "message": result.diagnostic,
        "context": result.context,
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"[{result.code}] {result.diagnostic}")
    if not result.ok:
        raise typer.Exit(code=1)


def run_git_sync_trunk(*, as_json: bool = False) -> None:
    manager = BranchLifecycleManager.create(Path.cwd())
    result = manager.sync_feature_with_trunk()
    payload = {
        "ok": result.ok,
        "code": result.code,
        "message": result.diagnostic,
        "context": result.context,
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"[{result.code}] {result.diagnostic}")
    if not result.ok:
        raise typer.Exit(code=1)


def run_git_post_ship(
    *,
    task_key: str = "",
    pr: Optional[int] = None,
    branch: str = "",
    wait_merge: bool = False,
    timeout_sec: int = 86400,
    poll_interval_sec: int = 10,
    as_json: bool = False,
) -> None:
    manager = PostShipManager.create(Path.cwd())
    if pr is not None and pr < 1:
        raise typer.BadParameter("pr must be a positive integer")

    inferred_from_branch = manager.infer_task_key_from_branch(branch or None) if branch else None
    if not task_key:
        if inferred_from_branch:
            task_key = inferred_from_branch

    if not task_key:
        raise typer.BadParameter("task key is required (provide --task-key or run from task branch)")
    if pr is None and not branch:
        raise typer.BadParameter("either --pr or --branch is required for PR lookup")
    if branch and inferred_from_branch and task_key != inferred_from_branch:
        raise typer.BadParameter("task key does not match provided branch")
    if timeout_sec < 1:
        raise typer.BadParameter("timeout_sec must be >= 1")
    if poll_interval_sec < 1:
        raise typer.BadParameter("poll_interval_sec must be >= 1")

    if wait_merge:
        watcher = PostShipWatcher.create(Path.cwd())
        result = watcher.wait_and_finalize(
            task_key=task_key,
            pr_number=pr,
            branch=branch or None,
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )
        if result.code in {"PR_WAIT_TIMEOUT", "POST_SHIP_DEFERRED_BRANCH_CHANGED"}:
            queued = enqueue_pending_post_ship(
                Path.cwd(),
                task_key=task_key,
                pr_number=pr,
                branch=branch or None,
            )
            status = "queued" if queued else "already_queued"
            reason = "timeout" if result.code == "PR_WAIT_TIMEOUT" else "branch_changed"
            deferred_message = (
                "merge watcher timed out; registered fallback reconciliation"
                if reason == "timeout"
                else "merge detected but cleanup deferred due to branch switch; registered fallback reconciliation"
            )
            result = GitOperationResult(
                ok=True,
                code="PR_WATCH_DEFERRED",
                message=deferred_message,
                context={
                    "task_key": task_key,
                    "timeout_sec": str(timeout_sec),
                    "fallback_status": status,
                    "fallback_reason": reason,
                },
            )
    else:
        result = manager.finalize_after_merge(
            task_key=task_key,
            pr_number=pr,
            branch=branch or None,
        )

    payload = {
        "ok": result.ok,
        "code": result.code,
        "message": result.diagnostic,
        "context": result.context,
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"[{result.code}] {result.diagnostic}")
    if not result.ok:
        raise typer.Exit(code=1)


def run_git_post_ship_reconcile(*, as_json: bool = False, max_items: int = 20) -> None:
    if max_items < 1:
        raise typer.BadParameter("max_items must be >= 1")
    manager = PostShipManager.create(Path.cwd())
    stats = reconcile_pending_post_ship(manager, max_items=max_items)
    payload = {
        "ok": True,
        "code": "POST_SHIP_RECONCILED",
        "message": "post-ship pending queue reconciled",
        "context": {k: str(v) for k, v in stats.items()},
    }
    # Explicit reconcile invocation is treated as a manual compensation action.
    audit_ok = True
    audit_error = ""
    try:
        ok = record_intervention_event(
            Path.cwd(),
            event_type="manual_compensation",
            command="git-post-ship-reconcile",
            summary="manual reconciliation command invoked",
            metadata={"max_items": max_items, "processed": stats.get("processed", 0)},
        )
        if not ok:
            audit_ok = False
            audit_error = "task_dir_unresolved_or_invalid_event_type"
    except Exception:
        audit_ok = False
        audit_error = "audit_write_failed"

    payload["context"]["audit_write"] = "ok" if audit_ok else "failed"
    if audit_error:
        payload["context"]["audit_error"] = audit_error
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"[{payload['code']}] {payload['message']}")
        if not audit_ok:
            typer.echo(f"[WARN] intervention audit not written ({audit_error})")


def run_git_post_ship_reconcile_background(*, max_items: int = 20) -> None:
    """Best-effort background reconciliation; intentionally silent."""
    if max_items < 1:
        return
    if not has_pending_post_ship(Path.cwd()):
        return
    manager = PostShipManager.create(Path.cwd())
    reconcile_pending_post_ship(manager, max_items=max_items)


def run_git_post_ship_watch_start(
    *,
    task_key: str = "",
    pr: Optional[int] = None,
    branch: str = "",
    timeout_sec: int = 86400,
    poll_interval_sec: int = 10,
    as_json: bool = False,
) -> None:
    """Start a detached post-ship watcher process.

    The spawned watcher polls every `poll_interval_sec` and self-terminates
    when merge cleanup finishes, PR is closed-unmerged, or timeout is reached.
    """
    manager = PostShipManager.create(Path.cwd())
    inferred_from_branch = manager.infer_task_key_from_branch(branch or None) if branch else None
    if not task_key and inferred_from_branch:
        task_key = inferred_from_branch
    if not task_key:
        raise typer.BadParameter("task key is required (provide --task-key or run from task branch)")
    if pr is None and not branch:
        raise typer.BadParameter("either --pr or --branch is required for PR lookup")
    if branch and inferred_from_branch and task_key != inferred_from_branch:
        raise typer.BadParameter("task key does not match provided branch")
    if pr is not None and pr < 1:
        raise typer.BadParameter("pr must be a positive integer")
    if timeout_sec < 1:
        raise typer.BadParameter("timeout_sec must be >= 1")
    if poll_interval_sec < 1:
        raise typer.BadParameter("poll_interval_sec must be >= 1")

    runtime_dir = Path.cwd() / ".harness-flow" / "post-ship-watchers"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    selector = f"pr{pr}" if pr is not None else "branch"
    log_path = runtime_dir / f"watch-{task_key}-{selector}-{stamp}.log"

    cmd = [
        sys.executable,
        "-m",
        "harness",
        "git-post-ship",
        "--task-key",
        task_key,
        "--wait-merge",
        "--timeout-sec",
        str(timeout_sec),
        "--poll-interval-sec",
        str(poll_interval_sec),
        "--json",
    ]
    if pr is not None:
        cmd.extend(["--pr", str(pr)])
    if branch:
        cmd.extend(["--branch", branch])

    with log_path.open("a", encoding="utf-8") as log_handle:
        proc = subprocess.Popen(  # noqa: S603,S607 - internal self-invocation
            cmd,
            cwd=str(Path.cwd()),
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
        )

    payload = {
        "ok": True,
        "code": "PR_WATCH_STARTED",
        "message": "detached post-ship watcher started",
        "context": {
            "task_key": task_key,
            "pr": str(pr or ""),
            "branch": branch,
            "pid": str(proc.pid),
            "timeout_sec": str(timeout_sec),
            "poll_interval_sec": str(poll_interval_sec),
            "log_path": str(log_path),
        },
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"[{payload['code']}] {payload['message']}")

