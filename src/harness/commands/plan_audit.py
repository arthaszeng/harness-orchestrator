"""harness plan-completion-audit — deliverables vs git diff completion check."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import typer

from harness.core.workflow_state import resolve_task_dir


_DELIVERABLE_RE = re.compile(
    r"^\s*-\s*\[([ x])\]\s*\*?\*?(D\d+)[:\s]*(.+?)(?:\*\*)?$",
    re.MULTILINE,
)

_FILE_REF_RE = re.compile(r"`([^`]+\.\w+)`")


def run_plan_completion_audit(
    *,
    task: str | None = None,
    as_json: bool = True,
) -> None:
    """Audit deliverable completion by comparing plan.md against git diff."""
    from harness.integrations.git_ops import run_git
    from harness.core.config import HarnessConfig

    cwd = Path.cwd()
    agents_dir = cwd / ".harness-flow"
    task_dir = resolve_task_dir(agents_dir, explicit_task_id=task)

    if task_dir is None:
        if as_json:
            typer.echo(json.dumps({"error": "no task directory found"}))
        raise typer.Exit(1)

    plan_path = task_dir / "plan.md"
    if not plan_path.exists():
        if as_json:
            typer.echo(json.dumps({"error": "plan.md not found"}))
        raise typer.Exit(1)

    content = plan_path.read_text(encoding="utf-8")
    deliverables = _parse_deliverables(content)

    try:
        cfg = HarnessConfig.load(cwd)
    except Exception:
        cfg = HarnessConfig()
    trunk = cfg.workflow.trunk_branch
    diff_range = f"origin/{trunk}..HEAD"

    result = run_git(["diff", "--name-only", diff_range], cwd, timeout=10)
    changed_files = set()
    if result.returncode == 0:
        changed_files = {f.strip() for f in result.stdout.strip().splitlines() if f.strip()}

    audit_results: list[dict[str, Any]] = []
    for d in deliverables:
        ref_files = _FILE_REF_RE.findall(d["description"])
        matched = [f for f in ref_files if _file_matches(f, changed_files)]
        status = _classify_completion(d["checked"], ref_files, matched)
        audit_results.append({
            "id": d["id"],
            "description": d["description"][:120],
            "plan_checked": d["checked"],
            "referenced_files": ref_files,
            "matched_in_diff": matched,
            "status": status,
        })

    summary = {
        "total": len(audit_results),
        "done": sum(1 for r in audit_results if r["status"] == "DONE"),
        "partial": sum(1 for r in audit_results if r["status"] == "PARTIAL"),
        "not_done": sum(1 for r in audit_results if r["status"] == "NOT_DONE"),
        "unknown": sum(1 for r in audit_results if r["status"] == "UNKNOWN"),
    }

    output = {
        "task_id": task_dir.name,
        "deliverables": audit_results,
        "summary": summary,
    }

    if as_json:
        typer.echo(json.dumps(output))
    else:
        for r in audit_results:
            icon = {"DONE": "✓", "PARTIAL": "~", "NOT_DONE": "✗", "UNKNOWN": "?"}[r["status"]]
            typer.echo(f"  {icon} {r['id']}: {r['status']} — {r['description'][:80]}")


def _parse_deliverables(content: str) -> list[dict[str, Any]]:
    """Extract deliverables from plan.md."""
    results = []
    for m in _DELIVERABLE_RE.finditer(content):
        checked = m.group(1) == "x"
        d_id = m.group(2)
        desc = m.group(3).strip()
        results.append({"id": d_id, "checked": checked, "description": desc})
    return results


def _file_matches(ref: str, changed_files: set[str]) -> bool:
    """Check if a file reference matches any changed file."""
    ref_norm = ref.lstrip("./")
    for cf in changed_files:
        if cf.endswith(ref_norm) or ref_norm.endswith(cf):
            return True
    return False


def _classify_completion(
    plan_checked: bool,
    ref_files: list[str],
    matched: list[str],
) -> str:
    """Classify deliverable completion status."""
    if not ref_files:
        return "DONE" if plan_checked else "UNKNOWN"
    if plan_checked and len(matched) == len(ref_files):
        return "DONE"
    if len(matched) > 0:
        return "PARTIAL"
    if plan_checked:
        return "DONE"
    return "NOT_DONE"
