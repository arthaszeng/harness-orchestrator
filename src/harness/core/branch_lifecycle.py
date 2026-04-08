"""Git branch lifecycle orchestration for harness workflows."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from harness.core.config import HarnessConfig
from harness.core.task_identity import TaskIdentityResolver, extract_task_key_from_branch
from harness.integrations.git_ops import (
    GitOperationResult,
    current_branch,
    ensure_clean_result,
    run_git_result,
)

log = logging.getLogger(__name__)

_AUTO_RESOLVE_PATTERNS = (
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Pipfile.lock",
    ".cursor/",
)


def _is_auto_resolvable(filepath: str) -> bool:
    """Return True if a conflicted file can be safely auto-resolved (take trunk version)."""
    for pattern in _AUTO_RESOLVE_PATTERNS:
        if pattern.endswith("/"):
            if filepath.startswith(pattern) or ("/" + pattern) in ("/" + filepath):
                return True
        else:
            basename = filepath.rsplit("/", 1)[-1] if "/" in filepath else filepath
            if basename == pattern:
                return True
    return False


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
        task_key = extract_task_key_from_branch(branch, cwd=self.project_root) or ""
        return GitOperationResult(
            ok=True,
            code="OK",
            message="preflight checks passed",
            context={
                "branch": branch,
                "trunk": self.trunk_branch,
                "branch_task_key": task_key,
            },
        )

    def prepare_task_branch(self, task_key: str, short_desc: str = "") -> GitOperationResult:
        clean = ensure_clean_result(self.project_root)
        if not clean.ok:
            return clean
        if not self.resolver.is_valid_task_key(task_key):
            return GitOperationResult(
                ok=False,
                code="INVALID_TASK_KEY",
                message=f"task key '{task_key}' does not match strategy '{self.resolver.strategy}'",
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

        auto_resolved: list[str] = []
        manual_conflicts: list[str] = []

        for iteration in range(50):
            conflict_files = self._get_conflict_files()
            if conflict_files is None:
                self._abort_rebase()
                return GitOperationResult(
                    ok=False,
                    code="REBASE_CONFLICT",
                    message="unable to enumerate conflict files",
                    context={
                        "auto_resolved_files": ",".join(auto_resolved),
                        "manual_conflict_files": "",
                    },
                )
            if not conflict_files:
                break

            resolvable = []
            unresolvable = []
            for f in conflict_files:
                if _is_auto_resolvable(f):
                    resolvable.append(f)
                else:
                    unresolvable.append(f)

            if unresolvable:
                manual_conflicts.extend(unresolvable)
                self._abort_rebase()
                return GitOperationResult(
                    ok=False,
                    code="REBASE_CONFLICT",
                    message=f"rebase conflict in {len(unresolvable)} file(s) requiring manual resolution",
                    stderr=rebase.stderr,
                    context={
                        "auto_resolved_files": ",".join(auto_resolved),
                        "manual_conflict_files": ",".join(manual_conflicts),
                    },
                )

            for f in resolvable:
                co = run_git_result(["checkout", "--ours", f], self.project_root, timeout=10)
                if not co.ok:
                    self._abort_rebase()
                    return GitOperationResult(
                        ok=False,
                        code="REBASE_CONFLICT",
                        message=f"failed to checkout --ours for {f}",
                        stderr=co.stderr,
                        context={
                            "auto_resolved_files": ",".join(auto_resolved),
                            "manual_conflict_files": ",".join(manual_conflicts),
                        },
                    )
                add = run_git_result(["add", "-f", f], self.project_root, timeout=10)
                if not add.ok:
                    self._abort_rebase()
                    return GitOperationResult(
                        ok=False,
                        code="REBASE_CONFLICT",
                        message=f"failed to stage auto-resolved file {f}",
                        stderr=add.stderr,
                        context={
                            "auto_resolved_files": ",".join(auto_resolved),
                            "manual_conflict_files": ",".join(manual_conflicts),
                        },
                    )
                auto_resolved.append(f)

            cont = run_git_result(
                ["rebase", "--continue"],
                self.project_root,
                timeout=120,
                code_on_error="REBASE_CONTINUE_FAILED",
                message="rebase --continue failed",
                env={**os.environ, "GIT_EDITOR": "true"},
            )
            if cont.ok:
                log.info("rebase auto-resolved %d file(s): %s", len(auto_resolved), auto_resolved)
                return GitOperationResult(
                    ok=True,
                    code="REBASE_AUTO_RESOLVED",
                    message=f"rebase completed with {len(auto_resolved)} auto-resolved file(s)",
                    context={"auto_resolved_files": ",".join(auto_resolved)},
                )

            status = run_git_result(["status", "--porcelain"], self.project_root, timeout=10)
            _conflict_prefixes = ("UU", "AA", "DU", "UD", "AU", "UA", "DD")
            has_new_conflicts = any(
                any(line.startswith(p) for p in _conflict_prefixes)
                for line in (status.stdout or "").splitlines()
            )
            if not has_new_conflicts:
                self._abort_rebase()
                return GitOperationResult(
                    ok=False,
                    code="REBASE_CONTINUE_FAILED",
                    message="rebase --continue failed for non-conflict reason",
                    stderr=cont.stderr,
                    context={"auto_resolved_files": ",".join(auto_resolved)},
                )

        else:
            self._abort_rebase()
            return GitOperationResult(
                ok=False,
                code="REBASE_CONFLICT",
                message="rebase auto-resolve exceeded iteration limit",
                context={
                    "auto_resolved_files": ",".join(auto_resolved),
                    "manual_conflict_files": ",".join(manual_conflicts),
                },
            )

        log.info("rebase auto-resolved %d file(s): %s", len(auto_resolved), auto_resolved)
        return GitOperationResult(
            ok=True,
            code="REBASE_AUTO_RESOLVED",
            message=f"rebase completed with {len(auto_resolved)} auto-resolved file(s)",
            context={"auto_resolved_files": ",".join(auto_resolved)},
        )

    def _get_conflict_files(self) -> list[str] | None:
        """Return conflicted file list, or None if the command fails."""
        result = run_git_result(
            ["diff", "--name-only", "--diff-filter=U"],
            self.project_root,
            timeout=10,
        )
        if not result.ok:
            return None
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]

    def _abort_rebase(self) -> None:
        result = run_git_result(
            ["rebase", "--abort"],
            self.project_root,
            code_on_error="REBASE_ABORT_FAILED",
            message="failed to abort rebase",
        )
        if not result.ok:
            log.error("rebase --abort failed: %s", result.message)

