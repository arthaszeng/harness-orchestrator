"""workflow_state.py unit tests."""

from __future__ import annotations

from pathlib import Path

from harness.core.state import TaskState
from harness.core.workflow_state import (
    WORKFLOW_STATE_FILENAME,
    WorkflowState,
    iter_task_dirs,
    load_current_workflow_state,
    load_workflow_state,
    resolve_task_dir,
)


def test_workflow_state_save_load_roundtrip(tmp_path: Path):
    task_dir = tmp_path / ".agents" / "tasks" / "task-007"
    state = WorkflowState(
        task_id="task-007",
        branch="agent/task-007-workflow-intelligence",
        phase=TaskState.BUILDING,
        iteration=2,
    )
    state.active_plan.id = "B1"
    state.active_plan.title = "Canonical Workflow State Artifact"
    state.blocker.reason = "missing evaluation artifact"
    state.save(task_dir)

    loaded = load_workflow_state(task_dir)
    assert loaded is not None
    assert loaded.task_id == "task-007"
    assert loaded.phase == TaskState.BUILDING
    assert loaded.active_plan.title == "Canonical Workflow State Artifact"
    assert loaded.blocker.reason == "missing evaluation artifact"


def test_load_workflow_state_invalid_json_returns_none(tmp_path: Path):
    task_dir = tmp_path / ".agents" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / WORKFLOW_STATE_FILENAME).write_text("{broken", encoding="utf-8")

    assert load_workflow_state(task_dir) is None


def test_load_workflow_state_unknown_schema_returns_none(tmp_path: Path):
    task_dir = tmp_path / ".agents" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / WORKFLOW_STATE_FILENAME).write_text(
        '{"schema_version": 999, "task_id": "task-001"}',
        encoding="utf-8",
    )

    assert load_workflow_state(task_dir) is None


def test_load_workflow_state_task_id_directory_mismatch_returns_none(tmp_path: Path):
    task_dir = tmp_path / ".agents" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / WORKFLOW_STATE_FILENAME).write_text(
        '{"schema_version": 1, "task_id": "task-002", "phase": "idle"}',
        encoding="utf-8",
    )

    assert load_workflow_state(task_dir) is None


def test_iter_task_dirs_uses_numeric_sort(tmp_path: Path):
    tasks_dir = tmp_path / ".agents" / "tasks"
    for name in ("task-2", "task-10", "task-9"):
        (tasks_dir / name).mkdir(parents=True)

    ordered = [path.name for path in iter_task_dirs(tmp_path / ".agents")]
    assert ordered == ["task-2", "task-9", "task-10"]


def test_resolve_task_dir_prefers_explicit_then_session_then_numeric_latest(tmp_path: Path):
    tasks_dir = tmp_path / ".agents" / "tasks"
    for name in ("task-001", "task-002", "task-010"):
        (tasks_dir / name).mkdir(parents=True)

    explicit = resolve_task_dir(
        tmp_path / ".agents",
        explicit_task_id="task-002",
        session_task_id="task-001",
    )
    session = resolve_task_dir(tmp_path / ".agents", session_task_id="task-001")
    latest = resolve_task_dir(tmp_path / ".agents")

    assert explicit is not None and explicit.name == "task-002"
    assert session is not None and session.name == "task-001"
    assert latest is not None and latest.name == "task-010"


def test_resolve_task_dir_rejects_path_traversal(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    tasks_dir = agents_dir / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "task-001").mkdir()

    assert resolve_task_dir(agents_dir, explicit_task_id="../../etc") is None
    assert resolve_task_dir(agents_dir, explicit_task_id="../passwords") is None
    # session_task_id traversal is rejected, but fallback to latest task still kicks in
    result = resolve_task_dir(agents_dir, session_task_id="../../etc")
    assert result is not None and result.name == "task-001"
    assert resolve_task_dir(agents_dir, explicit_task_id="task-001") is not None


def test_load_current_workflow_state_prefers_session_task_dir(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    task1 = agents_dir / "tasks" / "task-001"
    task2 = agents_dir / "tasks" / "task-002"
    WorkflowState(task_id="task-001", phase=TaskState.PLANNING).save(task1)
    WorkflowState(task_id="task-002", phase=TaskState.BUILDING).save(task2)

    task_dir, state = load_current_workflow_state(agents_dir, session_task_id="task-001")
    assert task_dir is not None and task_dir.name == "task-001"
    assert state is not None and state.phase == TaskState.PLANNING


def test_load_current_workflow_state_prefers_explicit_task_id(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    task1 = agents_dir / "tasks" / "task-001"
    task2 = agents_dir / "tasks" / "task-002"
    WorkflowState(task_id="task-001", phase=TaskState.PLANNING).save(task1)
    WorkflowState(task_id="task-002", phase=TaskState.BUILDING).save(task2)

    task_dir, state = load_current_workflow_state(
        agents_dir,
        explicit_task_id="task-002",
        session_task_id="task-001",
    )
    assert task_dir is not None and task_dir.name == "task-002"
    assert state is not None and state.phase == TaskState.BUILDING


def test_load_current_workflow_state_does_not_fallback_when_session_task_missing(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    task2 = agents_dir / "tasks" / "task-002"
    WorkflowState(task_id="task-002", phase=TaskState.BUILDING).save(task2)

    task_dir, state = load_current_workflow_state(agents_dir, session_task_id="task-001")
    assert task_dir is None
    assert state is None
