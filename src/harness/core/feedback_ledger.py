"""Structured feedback ledger for task-local feedback items."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness.core.task_identity import TASK_ID_STORAGE_PATTERN

LEDGER_FILENAME = "feedback-ledger.jsonl"


class FeedbackItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=120)
    task_id: str = Field(pattern=TASK_ID_STORAGE_PATTERN)
    source_phase: str = Field(min_length=1, max_length=120)
    source_role: str = Field(min_length=1, max_length=120)
    severity: str = Field(min_length=1, max_length=30)
    category: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(default_factory=list)
    status: str = Field(min_length=1, max_length=30)
    decision: str = Field(min_length=1, max_length=30)
    resolution: str = Field(default="", max_length=2000)
    resolved_by: str = Field(default="", max_length=120)
    verified_in: str = Field(default="", max_length=200)
    created_at: str = Field(default="", max_length=64)
    updated_at: str = Field(default="", max_length=64)


class FeedbackLedgerLoadResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str = ""
    items: list[FeedbackItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def save_feedback_ledger(task_dir: Path, items: list[FeedbackItem]) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / LEDGER_FILENAME
    content = "\n".join(item.model_dump_json() for item in items)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(content + ("\n" if content else ""), encoding="utf-8")
    tmp_path.replace(path)

    from harness.core.workflow_state import sync_task_state

    sync_task_state(task_dir, artifact_updates={"feedback_ledger": LEDGER_FILENAME})
    return path


def load_feedback_ledger(task_dir: Path) -> FeedbackLedgerLoadResult:
    path = task_dir / LEDGER_FILENAME
    if not path.exists():
        return FeedbackLedgerLoadResult(path=str(path))

    items: list[FeedbackItem] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return FeedbackLedgerLoadResult(
            path=str(path),
            errors=[f"file: {type(exc).__name__}: {exc}"],
        )

    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            items.append(FeedbackItem.model_validate(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"line {idx}: {type(exc).__name__}: {exc}")

    return FeedbackLedgerLoadResult(path=str(path), items=items, errors=errors)
