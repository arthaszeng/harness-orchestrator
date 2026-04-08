"""harness worktree-init — symlink shared artifacts from the main worktree."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from harness.core.worktree import resolve_main_worktree_root
from harness.i18n import apply_project_lang_from_cwd, t


_SYMLINK_TARGETS = [
    ".harness-flow",
    ".cursor/skills/harness",
    ".cursor/agents",
    ".cursor/rules",
]


def run_worktree_init(*, force: bool = False) -> None:
    """Create symlinks in a linked worktree pointing to the main tree's artifacts."""
    apply_project_lang_from_cwd()
    console = _get_console()
    project_root = Path.cwd()

    if sys.platform == "win32":
        console.print(f"  [red]✗[/] {t('worktree_init.windows_unsupported')}")
        raise typer.Exit(1)

    main_root = resolve_main_worktree_root(project_root)
    if main_root is None:
        console.print(f"  [red]✗[/] {t('worktree_init.not_worktree')}")
        raise typer.Exit(1)

    created = 0
    skipped = 0
    errors = 0
    for rel_path in _SYMLINK_TARGETS:
        source = main_root / rel_path
        target = project_root / rel_path

        if not source.exists():
            console.print(f"  [yellow]⚠[/] {t('worktree_init.source_missing', path=rel_path)}")
            skipped += 1
            continue

        if target.is_symlink():
            existing_dest = target.resolve()
            if existing_dest == source.resolve():
                console.print(f"  [dim]✓[/] {rel_path} → already linked")
                skipped += 1
                continue
            if not force:
                console.print(
                    f"  [red]✗[/] {t('worktree_init.exists_symlink_mismatch', path=rel_path)}"
                )
                errors += 1
                continue
            target.unlink()

        if target.exists():
            if not force:
                console.print(
                    f"  [red]✗[/] {t('worktree_init.exists_not_symlink', path=rel_path)}"
                )
                errors += 1
                continue
            import shutil
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=source.is_dir())
        console.print(f"  [green]✓[/] {rel_path} → {source}")
        created += 1

    console.print()
    if created > 0:
        console.print(f"  {t('worktree_init.done', created=created, skipped=skipped)}")
    elif skipped > 0:
        console.print(f"  {t('worktree_init.nothing_created', skipped=skipped)}")

    if errors > 0:
        raise typer.Exit(1)


def _get_console() -> Console:
    return Console()
