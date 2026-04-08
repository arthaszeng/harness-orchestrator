"""Worktree detection for Cursor parallel agents.

Detects whether the current working directory is inside a git worktree
(as opposed to the main working tree), and provides worktree metadata
for task isolation and status display.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from harness.core.config import HarnessConfig
from harness.core.task_identity import TaskIdentityResolver
from harness.integrations.git_ops import current_branch, run_git

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorktreeInfo:
    """Metadata about the current git worktree."""

    common_dir: Path
    git_dir: Path
    branch: str


def detect_worktree(cwd: Path | None = None) -> WorktreeInfo | None:
    """Detect if *cwd* is inside a Cursor parallel-agent worktree.

    Returns ``WorktreeInfo`` when the git common dir differs from the git dir
    (indicating a linked worktree), or ``None`` for the main working tree or
    when git is unavailable.
    """
    root = cwd or Path.cwd()
    try:
        common_result = run_git(["rev-parse", "--git-common-dir"], root, timeout=5)
        git_result = run_git(["rev-parse", "--git-dir"], root, timeout=5)
    except Exception:
        log.debug("git subprocess failed during worktree detection", exc_info=True)
        return None

    if common_result.returncode != 0 or git_result.returncode != 0:
        return None

    raw_common = Path(common_result.stdout.strip())
    raw_git = Path(git_result.stdout.strip())
    common_dir = (raw_common if raw_common.is_absolute() else (root / raw_common)).resolve()
    git_dir = (raw_git if raw_git.is_absolute() else (root / raw_git)).resolve()

    if common_dir == git_dir:
        return None

    try:
        branch = current_branch(root)
    except Exception:
        branch = ""

    return WorktreeInfo(common_dir=common_dir, git_dir=git_dir, branch=branch)


def resolve_main_worktree_root(cwd: Path | None = None) -> Path | None:
    """Return the root directory of the main working tree.

    For a linked worktree, ``common_dir`` points to the shared ``.git``
    directory inside the main checkout. Its parent is the main worktree root
    in standard git layouts.

    Returns ``None`` when not in a linked worktree or if detection fails.
    """
    wt = detect_worktree(cwd)
    if wt is None:
        return None
    main_root = wt.common_dir.parent
    if not (main_root / ".harness-flow").is_dir():
        log.warning(
            "main worktree root %s does not contain .harness-flow/; "
            "symlink targets may not exist",
            main_root,
        )
    return main_root


def extract_task_key_from_branch(branch: str, *, cwd: Path | None = None) -> str | None:
    """Extract task key from an ``agent/<task-key>-*`` branch name."""
    try:
        cfg = HarnessConfig.load(cwd or Path.cwd())
        resolver = TaskIdentityResolver.from_config(cfg)
        branch_prefix = cfg.workflow.branch_prefix
    except Exception:
        log.debug("failed to load task identity config; using default resolver", exc_info=True)
        resolver = TaskIdentityResolver()
        branch_prefix = "agent"
    return resolver.extract_from_branch(branch, branch_prefix=branch_prefix)


def extract_task_id_from_branch(branch: str) -> str | None:
    """Backward-compatible alias for task-key extraction.

    Historically this function only supported ``task-NNN``. It now delegates
    to the configured task-key resolver and returns ``None`` for non-matching
    branch names.
    """
    return extract_task_key_from_branch(branch)
