"""Persistent fallback queue for post-ship cleanup retries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.core.post_ship import PostShipManager

PENDING_FILENAME = "post-ship-pending.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pending_path(project_root: Path) -> Path:
    return project_root / ".harness-flow" / PENDING_FILENAME


def has_pending_post_ship(project_root: Path) -> bool:
    """Fast check for whether fallback queue may contain entries."""
    path = _pending_path(project_root)
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _load_pending(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        rows.append(raw)
    return rows


def _write_pending(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
    tmp.replace(path)


def enqueue_pending_post_ship(
    project_root: Path,
    *,
    task_key: str,
    pr_number: int | None,
    branch: str | None,
) -> bool:
    """Persist one post-ship pending item.

    Returns True when added, False when an equivalent item already exists.
    """
    path = _pending_path(project_root)
    rows = _load_pending(path)
    dedupe_key = (task_key, int(pr_number or 0), (branch or "").strip())
    for row in rows:
        key = (
            str(row.get("task_key", "")),
            int(row.get("pr_number", 0) or 0),
            str(row.get("branch", "")).strip(),
        )
        if key == dedupe_key:
            return False

    rows.append(
        {
            "task_key": task_key,
            "pr_number": int(pr_number) if pr_number is not None else None,
            "branch": (branch or "").strip(),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "attempts": 0,
            "last_error": "",
        }
    )
    _write_pending(path, rows)
    return True


def reconcile_pending_post_ship(
    manager: PostShipManager,
    *,
    max_items: int = 20,
) -> dict[str, int]:
    """Best-effort reconciliation for persisted post-ship pending entries."""
    path = _pending_path(manager.project_root)
    rows = _load_pending(path)
    if not rows:
        return {"processed": 0, "merged": 0, "closed": 0, "retained": 0, "failed": 0}

    keep: list[dict[str, Any]] = []
    processed = merged = closed = retained = failed = 0

    for idx, row in enumerate(rows):
        if processed >= max_items:
            keep.extend(rows[idx:])
            break

        task_key = str(row.get("task_key", "")).strip()
        pr_raw = row.get("pr_number")
        pr_number = int(pr_raw) if isinstance(pr_raw, int) else None
        branch = str(row.get("branch", "")).strip() or None
        if not task_key or (pr_number is None and not branch):
            continue

        processed += 1
        state = manager.check_pr_state(pr_number=pr_number, branch=branch)
        if state.code == "PR_MERGED":
            result = manager.finalize_after_merge(
                task_key=task_key,
                pr_number=pr_number,
                branch=branch,
            )
            if result.ok:
                merged += 1
            else:
                row["attempts"] = int(row.get("attempts", 0) or 0) + 1
                row["updated_at"] = _now_iso()
                row["last_error"] = result.code
                keep.append(row)
                failed += 1
            continue

        if state.code == "PR_CLOSED_UNMERGED":
            closed += 1
            continue

        # Keep pending entries for unresolved states.
        row["attempts"] = int(row.get("attempts", 0) or 0) + 1
        row["updated_at"] = _now_iso()
        if not state.ok:
            row["last_error"] = state.code
        keep.append(row)
        retained += 1

    _write_pending(path, keep)
    return {
        "processed": processed,
        "merged": merged,
        "closed": closed,
        "retained": retained,
        "failed": failed,
    }
