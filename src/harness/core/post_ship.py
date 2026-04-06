"""Post-ship lifecycle orchestration (PR merge -> trunk sync -> branch cleanup)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from harness.core.branch_lifecycle import BranchLifecycleManager
from harness.integrations.git_ops import GitOperationResult, current_branch, ensure_clean_result, run_git_result


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

        clean = ensure_clean_result(self.project_root)
        if not clean.ok:
            return clean

        task_branch = self._resolve_task_branch(task_key=task_key, branch=branch)
        if not task_branch:
            return GitOperationResult(
                ok=False,
                code="TASK_BRANCH_RESOLUTION_FAILED",
                message=f"unable to uniquely resolve local branch for task '{task_key}'",
            )

        if task_branch == self.trunk_branch:
            return GitOperationResult(
                ok=False,
                code="PROTECTED_BRANCH",
                message=f"refusing to cleanup protected trunk branch '{self.trunk_branch}'",
            )

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
        if active == task_branch:
            return GitOperationResult(
                ok=False,
                code="BRANCH_IN_USE",
                message=f"refusing to delete currently checked out branch '{task_branch}'",
            )

        delete = run_git_result(
            ["branch", "-d", task_branch],
            self.project_root,
            code_on_error="BRANCH_DELETE_FAILED",
            message=f"failed to delete local branch '{task_branch}'",
        )
        if not delete.ok:
            return delete

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

    def _resolve_task_branch(self, *, task_key: str, branch: str | None) -> str | None:
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
            return None

        exact = f"{self.branch_prefix}/{task_key}"
        if exact in branches:
            return exact
        if len(branches) == 1:
            return branches[0]
        return None
