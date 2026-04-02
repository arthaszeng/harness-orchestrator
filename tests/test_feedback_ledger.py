"""Tests for structured feedback ledger contract."""

from __future__ import annotations

from pathlib import Path

from harness.core.feedback_ledger import (
    FeedbackItem,
    FeedbackLedgerLoadResult,
    load_feedback_ledger,
    save_feedback_ledger,
)


def _item(**overrides) -> FeedbackItem:
    defaults = dict(
        id="fb-001",
        task_id="task-001",
        source_phase="plan-review",
        source_role="architect",
        severity="critical",
        category="design",
        summary="Missing workflow-state sync helper.",
        evidence=["plan.md#delivery-2"],
        status="open",
        decision="none",
        resolution="",
        resolved_by="",
        verified_in="",
        created_at="2026-04-02T00:00:00Z",
        updated_at="2026-04-02T00:00:00Z",
    )
    defaults.update(overrides)
    return FeedbackItem(**defaults)


def test_save_feedback_ledger_creates_jsonl_file(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    path = save_feedback_ledger(task_dir, [_item()])

    assert path.exists()
    assert path.name == "feedback-ledger.jsonl"


def test_load_feedback_ledger_round_trip(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    save_feedback_ledger(task_dir, [_item(), _item(id="fb-002", severity="warn")])

    result = load_feedback_ledger(task_dir)

    assert isinstance(result, FeedbackLedgerLoadResult)
    assert len(result.items) == 2
    assert result.errors == []
    assert result.items[0].id == "fb-001"
    assert result.items[1].severity == "warn"


def test_load_feedback_ledger_reports_bad_line_without_dropping_good_items(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    ledger = task_dir / "feedback-ledger.jsonl"
    ledger.write_text(
        "\n".join([
            _item().model_dump_json(),
            '{"id":"broken"',
        ]) + "\n",
        encoding="utf-8",
    )

    result = load_feedback_ledger(task_dir)

    assert len(result.items) == 1
    assert result.items[0].id == "fb-001"
    assert result.errors
    assert "line 2" in result.errors[0]


def test_save_feedback_ledger_updates_workflow_state_ref(tmp_path: Path):
    from harness.core.workflow_state import WorkflowState, load_workflow_state

    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    WorkflowState(task_id="task-001").save(task_dir)

    save_feedback_ledger(task_dir, [_item()])

    state = load_workflow_state(task_dir)
    assert state is not None
    assert state.artifacts.feedback_ledger == ".harness-flow/tasks/task-001/feedback-ledger.jsonl"


def test_save_feedback_ledger_keeps_artifact_when_state_sync_fails(tmp_path: Path, monkeypatch):
    from harness.core import workflow_state as workflow_state_module
    from harness.core.workflow_state import WorkflowState

    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    WorkflowState(task_id="task-001").save(task_dir)

    original_save = workflow_state_module.WorkflowState.save

    def fail_after_first_save(self, target_dir: Path) -> None:
        if target_dir == task_dir:
            raise OSError("disk full")
        original_save(self, target_dir)

    monkeypatch.setattr(workflow_state_module.WorkflowState, "save", fail_after_first_save)

    import pytest

    with pytest.raises(OSError, match="disk full"):
        save_feedback_ledger(task_dir, [_item()])

    ledger_path = task_dir / "feedback-ledger.jsonl"
    assert ledger_path.exists()
