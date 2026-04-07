"""Post-ship lifecycle orchestration (PR merge -> trunk sync -> branch cleanup)."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.integrations.git_ops import GitOperationResult, current_branch, ensure_clean_result, run_git_result

_log = logging.getLogger(__name__)


@dataclass
class PostShipManager:
    """Handle post-ship finalization with safety guards."""

    project_root: Path
    branch_manager: BranchLifecycleManager

    @classmethod
    def create(cls, project_root: Path | None = None) -> "PostShipManager":
        root = (project_root or Path.cwd()).resolve()
        return cls(project_root=root, branch_manager=BranchLifecycleManager.create(root))

    @property
    def trunk_branch(self) -> str:
        return self.branch_manager.trunk_branch

    @property
    def branch_prefix(self) -> str:
        return self.branch_manager.branch_prefix

    def infer_task_key_from_branch(self, branch: str | None = None) -> str | None:
        candidate = branch or current_branch(self.project_root)
        return self.branch_manager.resolver.extract_from_branch(
            candidate,
            branch_prefix=self.branch_prefix,
        )

    def check_pr_state(
        self,
        *,
        pr_number: int | None,
        branch: str | None,
    ) -> GitOperationResult:
        payload_result = self._load_pr_payload(pr_number=pr_number, branch=branch)
        if not payload_result.ok:
            return payload_result

        try:
            payload = json.loads(payload_result.stdout or "{}")
        except json.JSONDecodeError as exc:
            return GitOperationResult(
                ok=False,
                code="PR_LOOKUP_PARSE_FAILED",
                message="failed to parse PR state from gh output",
                stderr=str(exc),
            )

        state = str(payload.get("state", "")).upper()
        merged_at = payload.get("mergedAt")
        number = payload.get("number")
        url = payload.get("url")
        head_ref = str(payload.get("headRefName", "")).strip()
        context = {
            "pr": str(number or pr_number or ""),
            "url": str(url or ""),
            "state": state,
            "head_ref": head_ref,
        }

        if state == "MERGED" or merged_at:
            return GitOperationResult(
                ok=True,
                code="PR_MERGED",
                message="pull request is merged",
                context=context,
            )
        if state == "OPEN":
            return GitOperationResult(
                ok=False,
                code="PR_NOT_MERGED",
                message="pull request is still open",
                context=context,
            )
        if state == "CLOSED":
            return GitOperationResult(
                ok=False,
                code="PR_CLOSED_UNMERGED",
                message="pull request was closed without merge",
                context=context,
            )
        if not state:
            return GitOperationResult(
                ok=False,
                code="PR_STATE_UNKNOWN",
                message="pull request state is unavailable",
                context=context,
            )
        return GitOperationResult(
            ok=False,
            code="PR_STATE_UNKNOWN",
            message=f"unexpected pull request state '{state}'",
            context=context,
        )

    def finalize_after_merge(
        self,
        *,
        task_key: str,
        pr_number: int | None,
        branch: str | None = None,
    ) -> GitOperationResult:
        merged = self.check_pr_state(pr_number=pr_number, branch=branch)
        if not merged.ok:
            return merged

        task_branch = self._resolve_task_branch(
            task_key=task_key,
            branch=branch,
            pr_head_ref=merged.context.get("head_ref", ""),
        )
        if not task_branch:
            ambiguity = self._has_ambiguous_task_branches(task_key)
            if ambiguity is None:
                return GitOperationResult(
                    ok=False,
                    code="TASK_BRANCH_DISCOVERY_FAILED",
                    message=f"failed to inspect task branches for '{task_key}'",
                )
            if ambiguity:
                return GitOperationResult(
                    ok=False,
                    code="TASK_BRANCH_RESOLUTION_FAILED",
                    message=f"unable to uniquely resolve local branch for task '{task_key}'",
                )
            # Branch may already be deleted by `gh pr merge --delete-branch`.
            task_branch = ""

        if task_branch and task_branch == self.trunk_branch:
            return GitOperationResult(
                ok=False,
                code="PROTECTED_BRANCH",
                message=f"refusing to cleanup protected trunk branch '{self.trunk_branch}'",
            )

        active_before = current_branch(self.project_root)
        allowed = {self.trunk_branch}
        if task_branch:
            allowed.add(task_branch)
        if active_before not in allowed:
            return GitOperationResult(
                ok=False,
                code="POST_SHIP_DEFERRED_BRANCH_CHANGED",
                message="active branch changed during watcher interval; deferred cleanup",
                context={
                    "task_key": task_key,
                    "task_branch": task_branch,
                    "active_branch": active_before,
                    "trunk": self.trunk_branch,
                    "pr": merged.context.get("pr", ""),
                    "url": merged.context.get("url", ""),
                },
            )

        clean = ensure_clean_result(self.project_root)
        if not clean.ok:
            return clean

        checkout = run_git_result(
            ["checkout", self.trunk_branch],
            self.project_root,
            code_on_error="TRUNK_CHECKOUT_FAILED",
            message=f"failed to checkout trunk '{self.trunk_branch}'",
        )
        if not checkout.ok:
            return checkout

        pull = run_git_result(
            ["pull", "--ff-only", "origin", self.trunk_branch],
            self.project_root,
            timeout=120,
            code_on_error="TRUNK_PULL_FAILED",
            message=f"failed to update trunk '{self.trunk_branch}'",
        )
        if not pull.ok:
            return pull

        active = current_branch(self.project_root)
        if task_branch and active == task_branch:
            return GitOperationResult(
                ok=False,
                code="BRANCH_IN_USE",
                message=f"refusing to delete currently checked out branch '{task_branch}'",
            )

        if not task_branch:
            self._cleanup_worktree(task_key)
            return GitOperationResult(
                ok=True,
                code="POST_SHIP_DONE",
                message="post-ship cleanup completed (no local task branch to delete)",
                context={
                    "task_key": task_key,
                    "task_branch": "",
                    "trunk": self.trunk_branch,
                    "pr": merged.context.get("pr", ""),
                    "url": merged.context.get("url", ""),
                },
            )

        branch_exists = self._local_branch_exists(task_branch)
        if branch_exists is False:
            return GitOperationResult(
                ok=True,
                code="POST_SHIP_DONE",
                message=f"post-ship cleanup completed (branch '{task_branch}' already deleted)",
                context={
                    "task_key": task_key,
                    "task_branch": task_branch,
                    "trunk": self.trunk_branch,
                    "pr": merged.context.get("pr", ""),
                    "url": merged.context.get("url", ""),
                },
            )

        delete = run_git_result(
            ["branch", "-d", task_branch],
            self.project_root,
            code_on_error="BRANCH_DELETE_FAILED",
            message=f"failed to delete local branch '{task_branch}'",
        )
        if not delete.ok:
            branch_exists_after = self._local_branch_exists(task_branch)
            if branch_exists_after is False:
                return GitOperationResult(
                    ok=True,
                    code="POST_SHIP_DONE",
                    message=f"post-ship cleanup completed (branch '{task_branch}' already deleted)",
                    context={
                        "task_key": task_key,
                        "task_branch": task_branch,
                        "trunk": self.trunk_branch,
                        "pr": merged.context.get("pr", ""),
                        "url": merged.context.get("url", ""),
                    },
                )
            return delete

        self._cleanup_worktree(task_key)

        return GitOperationResult(
            ok=True,
            code="POST_SHIP_DONE",
            message="post-ship cleanup completed",
            context={
                "task_key": task_key,
                "task_branch": task_branch,
                "trunk": self.trunk_branch,
                "pr": merged.context.get("pr", ""),
                "url": merged.context.get("url", ""),
            },
        )

    def _cleanup_worktree(self, task_key: str) -> None:
        """Best-effort worktree registry and directory cleanup after merge."""
        try:
            from harness.core.worktree_lifecycle import WorktreeLifecycleManager

            common_dir = run_git_result(
                ["rev-parse", "--git-common-dir"],
                self.project_root,
                timeout=10,
            )
            if common_dir.ok and common_dir.stdout:
                root = Path(common_dir.stdout.strip()).resolve()
                if root.name == ".git":
                    root = root.parent
            else:
                root = self.project_root

            mgr = WorktreeLifecycleManager(project_root=root)
            entries = mgr.list_worktrees()
            match = [e for e in entries if e.task_key == task_key]
            if not match:
                return

            for entry in match:
                identifier = entry.task_key or entry.branch
                result = mgr.remove_worktree(identifier, prune_branch=False, force=True)
                if result.ok:
                    _log.info("post-ship: removed worktree for %s", task_key)
                else:
                    _log.warning("post-ship: worktree cleanup failed for %s: %s", task_key, result.message)
        except Exception:
            _log.warning("post-ship: worktree cleanup skipped (error)", exc_info=True)

    def _load_pr_payload(self, *, pr_number: int | None, branch: str | None) -> GitOperationResult:
        if pr_number is None and not (branch and branch.strip()):
            return GitOperationResult(
                ok=False,
                code="PR_SELECTOR_REQUIRED",
                message="either pr_number or branch must be provided to lookup PR state",
            )

        args = ["gh", "pr", "view"]
        if pr_number is not None:
            args.append(str(pr_number))
        else:
            args.extend(["--head", branch.strip()])
        args.extend(["--json", "number,state,url,mergedAt,headRefName"])

        try:
            completed = subprocess.run(
                args,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            return GitOperationResult(
                ok=False,
                code="PR_LOOKUP_TIMEOUT",
                message="timed out while querying pull request state",
                stderr=str(exc),
            )
        except OSError as exc:
            return GitOperationResult(
                ok=False,
                code="PR_LOOKUP_IO_ERROR",
                message="failed to execute gh command for pull request lookup",
                stderr=str(exc),
            )

        if completed.returncode != 0:
            return GitOperationResult(
                ok=False,
                code="PR_LOOKUP_FAILED",
                message="failed to query pull request state",
                stdout=completed.stdout,
                stderr=completed.stderr,
                context={"returncode": str(completed.returncode)},
            )

        return GitOperationResult(ok=True, code="OK", stdout=completed.stdout)

    def _resolve_task_branch(self, *, task_key: str, branch: str | None, pr_head_ref: str | None = None) -> str | None:
        if branch and branch.strip():
            return branch.strip()

        current = current_branch(self.project_root)
        task_from_current = self.infer_task_key_from_branch(current)
        if task_from_current == task_key:
            return current

        pattern = f"{self.branch_prefix}/{task_key}*"
        listed = run_git_result(
            ["branch", "--list", pattern],
            self.project_root,
            code_on_error="TASK_BRANCH_DISCOVERY_FAILED",
            message=f"failed to list branches by pattern '{pattern}'",
        )
        if not listed.ok:
            return None

        branches: list[str] = []
        for raw in listed.stdout.splitlines():
            candidate = raw.strip().lstrip("*").strip()
            if candidate:
                branches.append(candidate)
        if not branches:
            if pr_head_ref:
                inferred = self.infer_task_key_from_branch(pr_head_ref)
                if inferred == task_key:
                    return pr_head_ref
            return None

        exact = f"{self.branch_prefix}/{task_key}"
        if exact in branches:
            return exact
        if len(branches) == 1:
            return branches[0]
        return None

    def _has_ambiguous_task_branches(self, task_key: str) -> bool | None:
        pattern = f"{self.branch_prefix}/{task_key}*"
        listed = run_git_result(
            ["branch", "--list", pattern],
            self.project_root,
            code_on_error="TASK_BRANCH_DISCOVERY_FAILED",
            message=f"failed to list branches by pattern '{pattern}'",
        )
        if not listed.ok:
            return None
        branches = [line.strip().lstrip("*").strip() for line in listed.stdout.splitlines() if line.strip()]
        return len(branches) > 1

    def _local_branch_exists(self, branch: str) -> bool | None:
        listed = run_git_result(
            ["branch", "--list", branch],
            self.project_root,
            code_on_error="BRANCH_LIST_FAILED",
            message=f"failed to inspect branch '{branch}'",
        )
        if not listed.ok:
            return None
        return bool(listed.stdout.strip())
