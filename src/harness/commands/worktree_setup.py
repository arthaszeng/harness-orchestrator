"""harness worktree-setup — create symlinks in a linked worktree."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from harness.integrations.git_ops import run_git

WORKTREE_SYMLINK_TARGETS: list[str] = [
    ".harness-flow",
    ".cursor/skills/harness",
    ".cursor/agents",
    ".cursor/rules",
]


def _detect_main_worktree_root(cwd: Path) -> Path | None:
    """Return the main worktree root if *cwd* is inside a linked worktree."""
    try:
        common_result = run_git(["rev-parse", "--git-common-dir"], cwd, timeout=5)
        git_result = run_git(["rev-parse", "--git-dir"], cwd, timeout=5)
    except Exception:
        return None

    if common_result.returncode != 0 or git_result.returncode != 0:
        return None

    common_out = common_result.stdout.strip()
    git_out = git_result.stdout.strip()
    if not common_out or not git_out or "\0" in common_out or "\0" in git_out:
        return None

    common_dir = (Path(common_out) if Path(common_out).is_absolute() else (cwd / common_out)).resolve()
    git_dir = (Path(git_out) if Path(git_out).is_absolute() else (cwd / git_out)).resolve()

    if common_dir == git_dir:
        return None

    return common_dir.parent


def run_worktree_setup(*, cwd: Path | None = None) -> None:
    """Create symlinks in a linked worktree pointing to the main tree's artifacts."""
    project_root = cwd or Path.cwd()

    if sys.platform == "win32":
        typer.echo("  ✗ worktree-setup is not supported on Windows")
        raise typer.Exit(1)

    main_root = _detect_main_worktree_root(project_root)
    if main_root is None:
        typer.echo("  ℹ Not a linked worktree — nothing to do.")
        return

    typer.echo(f"  Main worktree: {main_root}")

    created = 0
    skipped = 0
    for rel_path in WORKTREE_SYMLINK_TARGETS:
        source = main_root / rel_path
        target = project_root / rel_path

        if not source.exists():
            typer.echo(f"  ⚠ {rel_path} — source not found in main worktree, skipping")
            skipped += 1
            continue

        if target.is_symlink():
            if target.resolve() == source.resolve():
                typer.echo(f"  ✓ {rel_path} — already linked")
                skipped += 1
                continue
            target.unlink()

        if target.exists():
            typer.echo(f"  ✗ {rel_path} — exists and is not a symlink, skipping")
            skipped += 1
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=source.is_dir())
        typer.echo(f"  ✓ {rel_path} → {source}")
        created += 1

    typer.echo()
    if created > 0:
        typer.echo(f"  Done: {created} symlink(s) created, {skipped} skipped.")
    else:
        typer.echo(f"  Nothing to create ({skipped} already linked or skipped).")
