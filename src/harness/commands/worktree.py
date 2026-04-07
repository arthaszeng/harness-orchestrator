"""CLI sub-commands for worktree lifecycle management."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def _resolve_project_root() -> Path:
    """Walk up from cwd to find the git repo root."""
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".git").exists() or (parent / ".git").is_file():
            return parent
    return cur

worktree_cli = typer.Typer(help="Manage parallel-agent worktrees")


@worktree_cli.command("create")
def worktree_create(
    task_key: str = typer.Argument(..., help="Task key (e.g. task-034)"),
    desc: str = typer.Option("", "--desc", "-d", help="Short branch description"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
) -> None:
    """Create a new worktree with isolated branch and task directory."""
    from harness.core.worktree_lifecycle import WorktreeLifecycleManager

    mgr = WorktreeLifecycleManager(_resolve_project_root())
    result = mgr.create_worktree(task_key, short_desc=desc)

    if as_json:
        typer.echo(json.dumps({
            "ok": result.ok,
            "path": result.path,
            "branch": result.branch,
            "task_key": result.task_key,
            "message": result.message,
        }, indent=2))
    elif result.ok:
        console.print(f"[green]✓[/green] Worktree created: [bold]{result.path}[/bold]")
        console.print(f"  Branch: {result.branch}")
        console.print(f"  Task:   {result.task_key}")
    else:
        console.print(f"[red]✗[/red] {result.message}")

    raise typer.Exit(code=0 if result.ok else 1)


@worktree_cli.command("list")
def worktree_list(
    as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
) -> None:
    """List all worktrees (managed, stale, and unmanaged)."""
    from harness.core.worktree_lifecycle import WorktreeLifecycleManager

    mgr = WorktreeLifecycleManager(_resolve_project_root())
    entries = mgr.list_worktrees()

    if as_json:
        typer.echo(json.dumps(
            [asdict(e) for e in entries],
            indent=2,
        ))
        return

    if not entries:
        console.print("[dim]No worktrees found.[/dim]")
        return

    table = Table(title="Worktrees")
    table.add_column("Task", style="bold")
    table.add_column("Branch")
    table.add_column("Path")
    table.add_column("Status")
    table.add_column("Created")

    status_style = {"active": "green", "stale": "yellow", "unmanaged": "dim"}
    for e in entries:
        table.add_row(
            e.task_key or "—",
            e.branch or "—",
            e.path,
            f"[{status_style.get(e.status, '')}]{e.status}[/{status_style.get(e.status, '')}]",
            e.created_at or "—",
        )

    console.print(table)


@worktree_cli.command("remove")
def worktree_remove(
    identifier: str = typer.Argument(..., help="Task key or worktree path"),
    prune_branch: bool = typer.Option(False, "--prune-branch", help="Also delete the local branch"),
    force: bool = typer.Option(False, "--force", help="Force removal even with uncommitted changes"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
) -> None:
    """Remove a worktree and clean up its registry entry."""
    from harness.core.worktree_lifecycle import WorktreeLifecycleManager

    mgr = WorktreeLifecycleManager(_resolve_project_root())
    result = mgr.remove_worktree(identifier, prune_branch=prune_branch, force=force)

    if as_json:
        typer.echo(json.dumps({
            "ok": result.ok,
            "message": result.message,
            "branch_pruned": result.branch_pruned,
        }, indent=2))
    elif result.ok:
        console.print(f"[green]✓[/green] {result.message}")
        if result.branch_pruned:
            console.print("  Branch also deleted.")
    else:
        console.print(f"[red]✗[/red] {result.message}")

    raise typer.Exit(code=0 if result.ok else 1)
