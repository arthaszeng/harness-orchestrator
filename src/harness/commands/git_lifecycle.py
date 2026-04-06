"""harness git lifecycle helper commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.core.post_ship import PostShipManager
from harness.core.post_ship_pending import enqueue_pending_post_ship, reconcile_pending_post_ship
from harness.core.post_ship_watcher import PostShipWatcher
from harness.integrations.git_ops import GitOperationResult


def run_git_preflight(*, as_json: bool = False) -> None:
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
    poll_interval_sec: int = 15,
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
        if result.code == "PR_WAIT_TIMEOUT":
            queued = enqueue_pending_post_ship(
                Path.cwd(),
                task_key=task_key,
                pr_number=pr,
                branch=branch or None,
            )
            status = "queued" if queued else "already_queued"
            result = GitOperationResult(
                ok=True,
                code="PR_WATCH_DEFERRED",
                message="merge watcher timed out; registered fallback reconciliation",
                context={
                    "task_key": task_key,
                    "timeout_sec": str(timeout_sec),
                    "fallback_status": status,
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
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"[{payload['code']}] {payload['message']}")


def run_git_post_ship_reconcile_background(*, max_items: int = 20) -> None:
    """Best-effort background reconciliation; intentionally silent."""
    if max_items < 1:
        return
    manager = PostShipManager.create(Path.cwd())
    reconcile_pending_post_ship(manager, max_items=max_items)

