"""Barrier mechanism for async sidecar task tracking.

Inspired by Claude Code's per-task JSON file pattern:
- Each barrier is an independent JSON file (no concurrent write conflicts)
- Atomic write via write-to-tmp + os.replace
- Directory-level readdir for completion checks
- Gate integration via required_for_gate flag
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class BarrierStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class BarrierRecord(BaseModel):
    """Schema for a single barrier file."""

    model_config = ConfigDict(extra="ignore")

    id: str
    phase: str
    status: BarrierStatus = BarrierStatus.PENDING
    required_for_gate: bool = False
    registered_at: str = ""
    completed_at: str | None = None
    error: str | None = None
    result_ref: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _barriers_dir(task_dir: Path) -> Path:
    return task_dir / "barriers"


def _barrier_path(task_dir: Path, barrier_id: str) -> Path:
    safe_id = barrier_id.replace("/", "_").replace("\\", "_")
    return _barriers_dir(task_dir) / f"{safe_id}.json"


def _write_atomic(path: Path, content: str) -> None:
    """Write content to path atomically via tmp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}.",
        suffix=".tmp",
    )
    closed = False
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        closed = True
        os.replace(tmp_path_str, str(path))
    except BaseException:
        if not closed:
            os.close(fd)
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        raise


def register_barrier(
    task_dir: Path,
    *,
    barrier_id: str,
    phase: str,
    required: bool = False,
) -> BarrierRecord:
    """Create a new barrier file in pending state."""
    record = BarrierRecord(
        id=barrier_id,
        phase=phase,
        status=BarrierStatus.PENDING,
        required_for_gate=required,
        registered_at=_now_iso(),
    )
    path = _barrier_path(task_dir, barrier_id)
    _write_atomic(path, record.model_dump_json(indent=2))
    return record


def complete_barrier(
    task_dir: Path,
    *,
    barrier_id: str,
    status: BarrierStatus = BarrierStatus.DONE,
    error: str | None = None,
    result_ref: str | None = None,
) -> BarrierRecord:
    """Update an existing barrier to a terminal state (idempotent)."""
    path = _barrier_path(task_dir, barrier_id)

    if path.exists():
        try:
            existing = BarrierRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            existing = BarrierRecord(id=barrier_id, phase="unknown", registered_at=_now_iso())
    else:
        existing = BarrierRecord(id=barrier_id, phase="unknown", registered_at=_now_iso())

    existing.status = status
    existing.completed_at = _now_iso()
    if error is not None:
        existing.error = error
    if result_ref is not None:
        existing.result_ref = result_ref

    _write_atomic(path, existing.model_dump_json(indent=2))
    return existing


def load_barrier(task_dir: Path, barrier_id: str) -> BarrierRecord | None:
    """Load a single barrier record, returns None if not found."""
    path = _barrier_path(task_dir, barrier_id)
    if not path.exists():
        return None
    try:
        return BarrierRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@dataclass
class BarrierCheckResult:
    all_required_done: bool
    total: int = 0
    done: int = 0
    failed: int = 0
    pending: int = 0
    running: int = 0
    skipped: int = 0
    unknown: int = 0
    required_not_done: list[str] = field(default_factory=list)
    barriers: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "all_required_done": self.all_required_done,
            "total": self.total,
            "done": self.done,
            "failed": self.failed,
            "pending": self.pending,
            "running": self.running,
            "skipped": self.skipped,
            "unknown": self.unknown,
            "required_not_done": self.required_not_done,
            "barriers": self.barriers,
        }


def check_barriers(
    task_dir: Path,
    *,
    phase: str | None = None,
    required_only: bool = False,
) -> BarrierCheckResult:
    """Scan barriers directory and compute aggregate status."""
    bdir = _barriers_dir(task_dir)
    if not bdir.exists():
        return BarrierCheckResult(all_required_done=True)

    result = BarrierCheckResult(all_required_done=True)

    for f in sorted(bdir.iterdir()):
        if not f.suffix == ".json":
            continue
        try:
            record = BarrierRecord.model_validate_json(f.read_text(encoding="utf-8"))
        except Exception:
            result.unknown += 1
            result.total += 1
            result.barriers.append({"id": f.stem, "status": "unknown", "file": f.name})
            result.all_required_done = False
            continue

        if phase and record.phase != phase:
            continue

        if required_only and not record.required_for_gate:
            continue

        result.total += 1
        status_counts = {
            BarrierStatus.DONE: "done",
            BarrierStatus.FAILED: "failed",
            BarrierStatus.PENDING: "pending",
            BarrierStatus.RUNNING: "running",
            BarrierStatus.SKIPPED: "skipped",
        }

        count_attr = status_counts.get(record.status, "unknown")
        setattr(result, count_attr, getattr(result, count_attr) + 1)

        result.barriers.append({
            "id": record.id,
            "status": record.status.value,
            "phase": record.phase,
            "required": record.required_for_gate,
            "error": record.error,
        })

        if record.required_for_gate and record.status != BarrierStatus.DONE:
            result.all_required_done = False
            result.required_not_done.append(record.id)

    return result


def list_barriers(task_dir: Path) -> list[BarrierRecord]:
    """List all barrier records for a task."""
    bdir = _barriers_dir(task_dir)
    if not bdir.exists():
        return []

    records: list[BarrierRecord] = []
    for f in sorted(bdir.iterdir()):
        if not f.suffix == ".json":
            continue
        try:
            records.append(BarrierRecord.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return records
