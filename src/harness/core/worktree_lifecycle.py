"""Worktree lifecycle management for parallel agent isolation.

Creates, lists, and removes git worktrees with integrated branch and
task directory setup.  All managed worktrees are tracked in a JSON
registry at ``.harness-flow/worktrees-registry.json``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from harness.core.config import HarnessConfig
from harness.core.task_identity import TaskIdentityResolver
from harness.integrations.git_ops import run_git_result

log = logging.getLogger(__name__)

REGISTRY_FILENAME = "worktrees-registry.json"
REGISTRY_VERSION = 1

_COPY_WHITELIST_DIRS = [
    ".cursor/skills",
    ".cursor/agents",
    ".cursor/rules",
]
_COPY_WHITELIST_FILES = [
    ".cursor/worktrees.json",
    ".harness-flow/config.toml",
    ".harness-flow/vision.md",
]


@dataclass
class WorktreeEntry:
    task_key: str
    branch: str
    path: str
    created_at: str
    status: Literal["active", "stale", "unmanaged"] = "active"


@dataclass
class WorktreeCreateResult:
    ok: bool
    path: str = ""
    branch: str = ""
    task_key: str = ""
    message: str = ""


@dataclass
class WorktreeRemoveResult:
    ok: bool
    message: str = ""
    branch_pruned: bool = False


def _sanitize_short_desc(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:48]


class WorktreeLifecycleManager:
    """Manage git worktree creation, listing, and removal."""

    def __init__(self, project_root: Path, config: HarnessConfig | None = None):
        self.project_root = project_root.resolve()
        self.config = config or HarnessConfig.load(self.project_root)
        self.resolver = TaskIdentityResolver.from_config(self.config)
        self._registry_path = self.project_root / ".harness-flow" / REGISTRY_FILENAME

    @property
    def trunk_branch(self) -> str:
        return self.config.workflow.trunk_branch

    @property
    def branch_prefix(self) -> str:
        return self.config.workflow.branch_prefix

    def create_worktree(
        self,
        task_key: str,
        short_desc: str = "",
    ) -> WorktreeCreateResult:
        if not self.resolver.is_valid_task_key(task_key):
            return WorktreeCreateResult(
                ok=False,
                message=f"invalid task key '{task_key}' for strategy '{self.resolver.strategy}'",
            )

        branch_name = f"{self.branch_prefix}/{task_key}"
        if short_desc:
            cleaned = _sanitize_short_desc(short_desc)
            if cleaned:
                branch_name = f"{branch_name}-{cleaned}"

        repo_name = self.project_root.name
        wt_path = (self.project_root.parent / f"{repo_name}-wt-{task_key}").resolve()

        if wt_path.exists():
            return WorktreeCreateResult(
                ok=False,
                message=f"worktree path already exists: {wt_path}",
            )

        existing = self._read_registry()
        for entry in existing:
            if entry.get("task_key") == task_key:
                return WorktreeCreateResult(
                    ok=False,
                    message=f"task key '{task_key}' already has a registered worktree",
                )

        fetch = run_git_result(
            ["fetch", "origin", self.trunk_branch],
            self.project_root,
            timeout=120,
            code_on_error="FETCH_FAILED",
            message=f"failed to fetch trunk '{self.trunk_branch}'",
        )
        if not fetch.ok:
            return WorktreeCreateResult(ok=False, message=fetch.diagnostic)

        add_result = run_git_result(
            [
                "worktree", "add",
                "-b", branch_name,
                str(wt_path),
                f"origin/{self.trunk_branch}",
            ],
            self.project_root,
            timeout=60,
            code_on_error="WORKTREE_ADD_FAILED",
            message=f"failed to create worktree at {wt_path}",
        )
        if not add_result.ok:
            return WorktreeCreateResult(ok=False, message=add_result.diagnostic)

        try:
            self._copy_artifacts(wt_path)

            tasks_dir = wt_path / ".harness-flow" / "tasks" / task_key
            tasks_dir.mkdir(parents=True, exist_ok=True)

            entry = {
                "task_key": task_key,
                "branch": branch_name,
                "path": str(wt_path),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "active",
            }
            existing.append(entry)
            self._write_registry(existing)
        except Exception as exc:
            log.warning("post-add setup failed, rolling back worktree: %s", exc)
            run_git_result(
                ["worktree", "remove", "--force", str(wt_path)],
                self.project_root,
                timeout=30,
                code_on_error="ROLLBACK_FAILED",
            )
            return WorktreeCreateResult(
                ok=False,
                message=f"worktree created but setup failed (rolled back): {exc}",
            )

        return WorktreeCreateResult(
            ok=True,
            path=str(wt_path),
            branch=branch_name,
            task_key=task_key,
            message=f"created worktree at {wt_path}",
        )

    def list_worktrees(self) -> list[WorktreeEntry]:
        registry = self._read_registry()
        git_paths = self._git_worktree_paths()

        entries: list[WorktreeEntry] = []
        seen_paths: set[str] = set()

        for rec in registry:
            path = rec.get("path", "")
            resolved = str(Path(path).resolve()) if path else ""
            status: Literal["active", "stale", "unmanaged"] = "active"
            if resolved not in git_paths:
                status = "stale"
            seen_paths.add(resolved)
            entries.append(WorktreeEntry(
                task_key=rec.get("task_key", ""),
                branch=rec.get("branch", ""),
                path=path,
                created_at=rec.get("created_at", ""),
                status=status,
            ))

        main_path = str(self.project_root.resolve())
        for gp in git_paths:
            if gp not in seen_paths and gp != main_path:
                entries.append(WorktreeEntry(
                    task_key="",
                    branch="",
                    path=gp,
                    created_at="",
                    status="unmanaged",
                ))

        return entries

    def remove_worktree(
        self,
        identifier: str,
        *,
        prune_branch: bool = False,
        force: bool = False,
    ) -> WorktreeRemoveResult:
        registry = self._read_registry()
        match_idx: int | None = None
        match_rec: dict | None = None

        for i, rec in enumerate(registry):
            if rec.get("task_key") == identifier or rec.get("path") == identifier:
                match_idx = i
                match_rec = rec
                break

        if match_rec is None:
            resolved = str(Path(identifier).resolve()) if identifier else ""
            for i, rec in enumerate(registry):
                if str(Path(rec.get("path", "")).resolve()) == resolved:
                    match_idx = i
                    match_rec = rec
                    break

        if match_rec is None:
            return WorktreeRemoveResult(
                ok=False,
                message=f"no worktree found for identifier '{identifier}'",
            )

        wt_path = match_rec.get("path", "")
        branch = match_rec.get("branch", "")

        remove_args = ["worktree", "remove"]
        if force:
            remove_args.append("--force")
        remove_args.append(wt_path)

        remove_result = run_git_result(
            remove_args,
            self.project_root,
            timeout=60,
            code_on_error="WORKTREE_REMOVE_FAILED",
            message=f"failed to remove worktree at {wt_path}",
        )
        if not remove_result.ok:
            return WorktreeRemoveResult(ok=False, message=remove_result.diagnostic)

        assert match_idx is not None
        registry.pop(match_idx)
        self._write_registry(registry)

        branch_pruned = False
        if prune_branch and branch:
            delete_flag = "-D" if force else "-d"
            del_result = run_git_result(
                ["branch", delete_flag, branch],
                self.project_root,
                code_on_error="BRANCH_DELETE_FAILED",
                message=f"failed to delete branch '{branch}'",
            )
            branch_pruned = del_result.ok
            if not del_result.ok:
                log.warning("branch deletion failed: %s", del_result.diagnostic)

        return WorktreeRemoveResult(
            ok=True,
            message=f"removed worktree at {wt_path}",
            branch_pruned=branch_pruned,
        )

    def _copy_artifacts(self, target: Path) -> None:
        for dir_rel in _COPY_WHITELIST_DIRS:
            src = self.project_root / dir_rel
            dst = target / dir_rel
            if src.is_dir():
                shutil.copytree(str(src), str(dst), dirs_exist_ok=True)

        for file_rel in _COPY_WHITELIST_FILES:
            src = self.project_root / file_rel
            dst = target / file_rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))

    def _read_registry(self) -> list[dict]:
        if not self._registry_path.is_file():
            return []
        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("worktrees", [])
            return []
        except (json.JSONDecodeError, OSError):
            log.warning("corrupt worktree registry at %s; treating as empty", self._registry_path)
            return []

    def _write_registry(self, entries: list[dict]) -> None:
        payload = {"version": REGISTRY_VERSION, "worktrees": entries}
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp = tempfile.mkstemp(
            dir=str(self._registry_path.parent),
            prefix=".wt-reg-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp, str(self._registry_path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _git_worktree_paths(self) -> set[str]:
        result = run_git_result(
            ["worktree", "list", "--porcelain"],
            self.project_root,
            timeout=10,
            code_on_error="WORKTREE_LIST_FAILED",
        )
        paths: set[str] = set()
        if not result.ok:
            return self._git_worktree_paths_fallback()
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                p = line[len("worktree "):].strip()
                if p:
                    paths.add(str(Path(p).resolve()))
        return paths

    def _git_worktree_paths_fallback(self) -> set[str]:
        result = run_git_result(
            ["worktree", "list"],
            self.project_root,
            timeout=10,
            code_on_error="WORKTREE_LIST_FAILED",
        )
        paths: set[str] = set()
        if not result.ok:
            return paths
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts:
                paths.add(str(Path(parts[0]).resolve()))
        return paths
