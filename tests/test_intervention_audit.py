"""Tests for intervention audit recording."""

from __future__ import annotations

from pathlib import Path

from harness.core.intervention_audit import load_intervention_counts, record_intervention_event
from harness.core.workflow_state import WorkflowState


def _prepare_task(tmp_path: Path, task_id: str = "task-001") -> Path:
    task_dir = tmp_path / ".harness-flow" / "tasks" / task_id
    task_dir.mkdir(parents=True)
    WorkflowState(task_id=task_id).save(task_dir)
    return task_dir


def test_record_intervention_event_writes_counts(tmp_path: Path):
    _prepare_task(tmp_path, "task-010")
    ok = record_intervention_event(
        tmp_path,
        task_id="task-010",
        event_type="manual_compensation",
        command="git-post-ship-reconcile",
        summary="manual recovery",
    )
    assert ok is True
    counts = load_intervention_counts(tmp_path / ".harness-flow" / "tasks" / "task-010")
    assert counts["manual_compensation"] == 1


def test_record_intervention_event_rejects_invalid_type(tmp_path: Path):
    _prepare_task(tmp_path, "task-010")
    ok = record_intervention_event(
        tmp_path,
        task_id="task-010",
        event_type="not-supported",
        command="unknown",
    )
    assert ok is False


def test_record_intervention_event_allows_repeated_writes(tmp_path: Path):
    _prepare_task(tmp_path, "task-010")
    for _ in range(2):
        assert record_intervention_event(
            tmp_path,
            task_id="task-010",
            event_type="manual_retry",
            command="harness eval",
        ) is True
    counts = load_intervention_counts(tmp_path / ".harness-flow" / "tasks" / "task-010")
    assert counts["manual_retry"] == 2


def test_record_intervention_event_returns_false_when_task_dir_missing(tmp_path: Path):
    ok = record_intervention_event(
        tmp_path,
        task_id="task-999",
        event_type="manual_confirmation",
        command="harness gate",
    )
    assert ok is False
