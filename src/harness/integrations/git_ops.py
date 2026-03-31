"""Git branch operations."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def _run_git(
    args: list[str], cwd: Path, *, timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def current_branch(cwd: Path) -> str:
    result = _run_git(["branch", "--show-current"], cwd)
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


def stash_save(cwd: Path) -> bool:
    result = _run_git(["stash", "save", "harness-autosave"], cwd)
    return result.returncode == 0


def stash_pop(cwd: Path) -> bool:
    result = _run_git(["stash", "pop"], cwd)
    return result.returncode == 0


# ── Branch lifecycle operations ──────────────────────────────────


class DirtyWorktreeError(RuntimeError):
    """Raised when the working tree has uncommitted changes at task start."""


def ensure_clean(cwd: Path) -> None:
    """Raise DirtyWorktreeError if the working tree is dirty."""
    if has_changes(cwd):
        raise DirtyWorktreeError(
            "Working tree has uncommitted changes. "
            "Commit or stash them before starting a task."
        )


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
