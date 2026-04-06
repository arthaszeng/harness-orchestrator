"""Task-level manual intervention audit events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from harness.core.workflow_state import resolve_task_dir

AUDIT_FILENAME = "intervention-audit.jsonl"
VALID_EVENT_TYPES = {"manual_confirmation", "manual_retry", "manual_compensation"}


class InterventionEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=120)
    # Keep aligned with TaskIdentityResolver strategies (task/jira/hybrid/custom).
    task_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    event_type: str = Field(min_length=1, max_length=64)
    command: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=400)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(min_length=1, max_length=64)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append_line(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload + "\n")


def _resolve_audit_task_dir(project_root: Path, *, explicit_task_id: str | None) -> Path | None:
    agents_dir = project_root / ".harness-flow"
    return resolve_task_dir(agents_dir, explicit_task_id=explicit_task_id)


def record_intervention_event(
    project_root: Path,
    *,
    event_type: str,
    command: str,
    summary: str = "",
    metadata: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> bool:
    """Best-effort append of intervention events.

    Returns False when task directory is unavailable or event type is invalid.
    """
    if event_type not in VALID_EVENT_TYPES:
        return False
    task_dir = _resolve_audit_task_dir(project_root, explicit_task_id=task_id)
    if task_dir is None:
        return False

    event = InterventionEvent(
        id=f"intv-{uuid4().hex[:12]}",
        task_id=task_dir.name,
        event_type=event_type,
        command=command,
        summary=summary,
        metadata=metadata or {},
        created_at=_utc_now(),
    )
    _append_line(task_dir / AUDIT_FILENAME, event.model_dump_json())
    return True


def load_intervention_counts(task_dir: Path) -> dict[str, int]:
    """Load counts grouped by intervention type."""
    path = task_dir / AUDIT_FILENAME
    counts = {name: 0 for name in sorted(VALID_EVENT_TYPES)}
    if not path.exists():
        return counts
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            kind = str(raw.get("event_type", "")).strip()
            if kind in counts:
                counts[kind] += 1
        except Exception:
            continue
    return counts
