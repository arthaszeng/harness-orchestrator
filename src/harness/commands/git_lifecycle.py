"""harness git lifecycle helper commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from harness.commands._cli_helpers import emit_git_result
from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.core.post_ship import PostShipManager


def run_git_preflight(*, as_json: bool = False) -> None:
    manager = BranchLifecycleManager.create(Path.cwd())
    result = manager.preflight_repo_state()
    emit_git_result(result, as_json)


def run_git_prepare_branch(*, task_key: str, short_desc: str = "", as_json: bool = False) -> None:
    manager = BranchLifecycleManager.create(Path.cwd())
    result = manager.prepare_task_branch(task_key, short_desc)
    emit_git_result(result, as_json)


def run_git_sync_trunk(*, as_json: bool = False) -> None:
    manager = BranchLifecycleManager.create(Path.cwd())
    result = manager.sync_feature_with_trunk()
    emit_git_result(result, as_json)


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
    emit_git_result(result, as_json, emit_recovery=False)
