"""Git branch operations."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitOperationResult:
    ok: bool
    code: str
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    context: dict[str, str] = field(default_factory=dict)

    @property
    def diagnostic(self) -> str:
        if self.message:
            return self.message
        text = self.stderr.strip() or self.stdout.strip()
        return text[:300]


def run_git_result(
    args: list[str],
    cwd: Path,
    *,
    timeout: int = 30,
    code_on_error: str = "GIT_COMMAND_FAILED",
    message: str = "",
    env: dict[str, str] | None = None,
) -> GitOperationResult:
    """Run git command and return structured result."""
    try:
        completed = run_git(args, cwd, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        return GitOperationResult(
            ok=False,
            code="GIT_TIMEOUT",
            message=f"git {' '.join(args)} timed out",
            stderr=str(exc),
            context={"args": " ".join(args)},
        )
    except OSError as exc:
        return GitOperationResult(
            ok=False,
            code="GIT_IO_ERROR",
            message=f"unable to execute git {' '.join(args)}",
            stderr=str(exc),
            context={"args": " ".join(args)},
        )
    if completed.returncode != 0:
        return GitOperationResult(
            ok=False,
            code=code_on_error,
            message=message or f"git {' '.join(args)} failed",
            stdout=completed.stdout,
            stderr=completed.stderr,
            context={"args": " ".join(args), "returncode": str(completed.returncode)},
        )
    return GitOperationResult(
        ok=True,
        code="OK",
        message=message or f"git {' '.join(args)} succeeded",
        stdout=completed.stdout,
        stderr=completed.stderr,
        context={"args": " ".join(args)},
    )


def run_git(
    args: list[str], cwd: Path, *, timeout: int = 30, env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the completed process."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


_run_git = run_git


def current_branch(cwd: Path) -> str | None:
    """Return current branch name, ``""`` for detached HEAD, ``None`` on git failure."""
    result = _run_git(["branch", "--show-current"], cwd)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def create_branch(branch: str, cwd: Path) -> bool:
    """Create and switch to a new branch, or switch if it already exists."""
    result = _run_git(["checkout", "-b", branch], cwd)
    if result.returncode != 0:
        result = _run_git(["checkout", branch], cwd)
    return result.returncode == 0


def switch_branch(branch: str, cwd: Path) -> bool:
    result = _run_git(["checkout", branch], cwd)
    return result.returncode == 0


def merge_branch(source: str, target: str, cwd: Path) -> bool:
    """Merge source into target."""
    _run_git(["checkout", target], cwd)
    result = _run_git(["merge", source, "--no-ff", "-m", f"merge: {source} → {target}"], cwd)
    return result.returncode == 0


def has_changes(cwd: Path) -> bool:
    """Return True if the working tree has uncommitted changes."""
    result = _run_git(["status", "--porcelain"], cwd)
    return bool(result.stdout.strip())


def get_diff_stat(cwd: Path) -> str:
    """Get diff stat for the current branch relative to main."""
    result = _run_git(["diff", "--stat", "HEAD~1"], cwd)
    return result.stdout.strip() if result.returncode == 0 else ""


def _find_repo_root(start: Path) -> Optional[Path]:
    """Walk up from *start* to find the git repository root.

    Returns ``None`` if no ``.git`` directory is found.
    """
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".git").exists() or (parent / ".git").is_file():
            return parent
    return None


def get_head_commit_epoch(cwd: Path) -> Optional[float]:
    """Return the author-date epoch of HEAD, or None on failure.

    Resolves the git repo root from *cwd* before running the command so that
    callers inside ``.harness-flow/tasks/task-NNN/`` still work correctly.
    """
    repo = _find_repo_root(cwd)
    if repo is None:
        return None
    try:
        result = _run_git(["log", "-1", "--format=%at", "HEAD"], repo, timeout=10)
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


def stash_save(cwd: Path) -> bool:
    result = _run_git(["stash", "save", "harness-autosave"], cwd)
    return result.returncode == 0


def stash_pop(cwd: Path) -> bool:
    result = _run_git(["stash", "pop"], cwd)
    return result.returncode == 0


# ── Branch lifecycle operations ──────────────────────────────────


class DirtyWorkingTreeError(RuntimeError):
    """Raised when the working tree has uncommitted changes at task start."""



def ensure_clean(cwd: Path) -> None:
    """Raise DirtyWorkingTreeError if the working tree is dirty."""
    if has_changes(cwd):
        raise DirtyWorkingTreeError(
            "Working tree has uncommitted changes. "
            "Commit or stash them before starting a task."
        )


def ensure_clean_result(cwd: Path) -> GitOperationResult:
    """Structured variant of clean check."""
    if has_changes(cwd):
        return GitOperationResult(
            ok=False,
            code="DIRTY_WORKING_TREE",
            message="working tree has uncommitted changes",
        )
    return GitOperationResult(ok=True, code="OK", message="working tree is clean")


def rebase_and_merge(source: str, target: str, cwd: Path) -> bool:
    """Rebase *source* onto *target*, fast-forward merge, then delete the source branch.

    Returns True on success, False if any step fails (branch is preserved).
    """
    r = _run_git(["checkout", source], cwd)
    if r.returncode != 0:
        log.warning("rebase_and_merge: checkout %s failed: %s", source, r.stderr.strip())
        return False

    r = _run_git(["rebase", target], cwd, timeout=120)
    if r.returncode != 0:
        log.warning("rebase_and_merge: rebase onto %s failed: %s", target, r.stderr.strip())
        _run_git(["rebase", "--abort"], cwd)
        _run_git(["checkout", target], cwd)
        return False

    r = _run_git(["checkout", target], cwd)
    if r.returncode != 0:
        log.warning("rebase_and_merge: checkout %s failed: %s", target, r.stderr.strip())
        return False

    r = _run_git(["merge", "--ff-only", source], cwd)
    if r.returncode != 0:
        log.warning("rebase_and_merge: ff-merge failed: %s", r.stderr.strip())
        return False

    _run_git(["branch", "-d", source], cwd)
    return True


def safe_cleanup(target_branch: str, cwd: Path) -> None:
    """Best-effort cleanup: stash dirty changes and switch back to *target_branch*.

    Called on task failure, interruption, or exception to leave the repo
    in a clean state on the trunk branch. Never raises.
    """
    try:
        if has_changes(cwd):
            _run_git(["add", "-A"], cwd)
            _run_git(["stash", "save", "harness-autosave"], cwd)
            log.info("safe_cleanup: stashed dirty changes")

        cur = current_branch(cwd)
        if cur != target_branch:
            r = _run_git(["checkout", target_branch], cwd)
            if r.returncode != 0:
                log.warning("safe_cleanup: checkout %s failed: %s", target_branch, r.stderr.strip())
    except Exception:
        log.exception("safe_cleanup: unexpected error during cleanup")
