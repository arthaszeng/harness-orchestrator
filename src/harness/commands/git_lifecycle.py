"""harness git lifecycle helper commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.core.post_ship import PostShipManager


def _emit_recovery_hint(code: str) -> None:
    """Emit an i18n recovery hint for the given error code, if available."""
    from harness.i18n import apply_project_lang_from_cwd, t

    apply_project_lang_from_cwd(Path.cwd())
    key = f"git_preflight.recovery.{code}"
    msg = t(key)
    if msg == key:
        msg = t("git_preflight.recovery.generic")
    typer.echo(msg, err=True)


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
        _emit_recovery_hint(result.code)
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
        _emit_recovery_hint(result.code)
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
        _emit_recovery_hint(result.code)
        raise typer.Exit(code=1)


def run_git_post_ship(
    *,
    task_key: str = "",
    pr: Optional[int] = None,
    branch: str = "",
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
