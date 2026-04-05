"""Git branch lifecycle orchestration for harness workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from harness.core.config import HarnessConfig
from harness.core.task_identity import TaskIdentityResolver
from harness.core.worktree import detect_worktree
from harness.integrations.git_ops import (
    GitOperationResult,
    current_branch,
    ensure_clean_result,
    run_git_result,
)


def _sanitize_short_desc(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:48]


@dataclass
class BranchLifecycleManager:
    project_root: Path
    config: HarnessConfig
    resolver: TaskIdentityResolver

    @classmethod
    def create(cls, project_root: Path | None = None) -> "BranchLifecycleManager":
        root = (project_root or Path.cwd()).resolve()
        cfg = HarnessConfig.load(root)
        resolver = TaskIdentityResolver.from_config(cfg)
        return cls(project_root=root, config=cfg, resolver=resolver)

    @property
    def trunk_branch(self) -> str:
        return self.config.workflow.trunk_branch

    @property
    def branch_prefix(self) -> str:
        return self.config.workflow.branch_prefix

    def preflight_repo_state(self) -> GitOperationResult:
        clean = ensure_clean_result(self.project_root)
        if not clean.ok:
            return clean
        branch = current_branch(self.project_root)
        if not branch:
            return GitOperationResult(
                ok=False,
                code="DETACHED_HEAD",
                message="repository is in detached HEAD state",
            )
        wt = detect_worktree(self.project_root)
        return GitOperationResult(
            ok=True,
            code="OK",
            message="preflight checks passed",
            context={
                "branch": branch,
                "trunk": self.trunk_branch,
                "worktree": "true" if wt is not None else "false",
            },
        )

    def prepare_task_branch(self, task_key: str, short_desc: str = "") -> GitOperationResult:
        if not self.resolver.is_valid_task_key(task_key):
            return GitOperationResult(
                ok=False,
                code="INVALID_TASK_KEY",
                message=f"task key '{task_key}' does not match strategy '{self.resolver.strategy}'",
            )
        wt = detect_worktree(self.project_root)
        if wt is not None:
            return GitOperationResult(
                ok=True,
                code="WORKTREE_SKIP",
                message="worktree detected; skip automatic branch preparation",
                context={"branch": wt.branch, "trunk": self.trunk_branch},
            )
        desc = _sanitize_short_desc(short_desc)
        branch_name = f"{self.branch_prefix}/{task_key}"
        if desc:
            branch_name = f"{branch_name}-{desc}"

        checkout_trunk = run_git_result(
            ["checkout", self.trunk_branch],
            self.project_root,
            code_on_error="TRUNK_CHECKOUT_FAILED",
            message=f"failed to checkout trunk '{self.trunk_branch}'",
        )
        if not checkout_trunk.ok:
            return checkout_trunk

        pull = run_git_result(
            ["pull", "--ff-only", "origin", self.trunk_branch],
            self.project_root,
            timeout=120,
            code_on_error="TRUNK_PULL_FAILED",
            message=f"failed to update trunk '{self.trunk_branch}'",
        )
        if not pull.ok:
            return pull

        create = run_git_result(
            ["checkout", "-b", branch_name],
            self.project_root,
            code_on_error="BRANCH_CREATE_FAILED",
            message=f"failed to create branch '{branch_name}'",
        )
        if create.ok:
            return GitOperationResult(
                ok=True,
                code="OK",
                message=f"created branch '{branch_name}'",
                context={"branch": branch_name, "created": "true"},
            )

        resume = run_git_result(
            ["checkout", branch_name],
            self.project_root,
            code_on_error="BRANCH_RESUME_FAILED",
            message=f"failed to resume existing branch '{branch_name}'",
        )
        if not resume.ok:
            return resume
        return GitOperationResult(
            ok=True,
            code="OK",
            message=f"resumed branch '{branch_name}'",
            context={"branch": branch_name, "created": "false"},
        )

    def sync_feature_with_trunk(self) -> GitOperationResult:
        fetch = run_git_result(
            ["fetch", "origin", self.trunk_branch],
            self.project_root,
            timeout=120,
            code_on_error="FETCH_FAILED",
            message=f"failed to fetch trunk '{self.trunk_branch}'",
        )
        if not fetch.ok:
            return fetch
        rebase = run_git_result(
            ["rebase", f"origin/{self.trunk_branch}"],
            self.project_root,
            timeout=120,
            code_on_error="REBASE_CONFLICT",
            message=f"failed to rebase onto '{self.trunk_branch}'",
        )
        if rebase.ok:
            return GitOperationResult(ok=True, code="OK", message="feature branch is synced with trunk")

        abort = run_git_result(
            ["rebase", "--abort"],
            self.project_root,
            code_on_error="REBASE_ABORT_FAILED",
            message="failed to abort rebase after error",
        )
        if not abort.ok:
            return GitOperationResult(
                ok=False,
                code="REBASE_ABORT_FAILED",
                message="rebase failed and abort failed",
                stderr=(abort.stderr or rebase.stderr),
                context={
                    "rebase_code": rebase.code,
                    "abort_code": abort.code,
                },
            )
        return rebase

