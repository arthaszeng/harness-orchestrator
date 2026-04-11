"""workflow_state.py unit tests."""

from __future__ import annotations

import warnings as _warnings
from pathlib import Path

import pytest

from harness.core.state import TaskState
from harness.core.workflow_state import (
    WORKFLOW_STATE_FILENAME,
    _VALID_TRANSITIONS,
    _validate_phase_transition,
    WorkflowState,
    artifact_pairs,
    iter_task_dirs,
    load_current_workflow_state,
    load_workflow_state,
    resolve_task_dir,
    sync_task_state,
)


def test_workflow_state_save_load_roundtrip(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-007"
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
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / WORKFLOW_STATE_FILENAME).write_text("{broken", encoding="utf-8")

    assert load_workflow_state(task_dir) is None


def test_load_workflow_state_unknown_schema_invalid_shape_returns_none(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / WORKFLOW_STATE_FILENAME).write_text(
        '{"schema_version": 999, "task_id": "task-001", "phase": "not-a-real-phase"}',
        encoding="utf-8",
    )

    assert load_workflow_state(task_dir) is None


def test_load_workflow_state_future_schema_loads_when_shape_valid(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / WORKFLOW_STATE_FILENAME).write_text(
        '{"schema_version": 999, "task_id": "task-001", "phase": "building", "iteration": 1}',
        encoding="utf-8",
    )

    loaded = load_workflow_state(task_dir)

    assert loaded is not None
    assert loaded.task_id == "task-001"
    assert loaded.phase == TaskState.BUILDING


def test_load_workflow_state_task_id_directory_mismatch_returns_none(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / WORKFLOW_STATE_FILENAME).write_text(
        '{"schema_version": 1, "task_id": "task-002", "phase": "idle"}',
        encoding="utf-8",
    )

    with _warnings.catch_warnings(record=True) as w:
        _warnings.simplefilter("always")
        assert load_workflow_state(task_dir) is None
    assert any("task_id mismatch" in str(x.message) for x in w)


def test_load_workflow_state_non_utf8_returns_none(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / WORKFLOW_STATE_FILENAME).write_bytes(b"\xff\xfe")

    assert load_workflow_state(task_dir) is None


def test_iter_task_dirs_uses_numeric_sort(tmp_path: Path):
    tasks_dir = tmp_path / ".harness-flow" / "tasks"
    for name in ("task-2", "task-10", "task-9"):
        (tasks_dir / name).mkdir(parents=True)

    ordered = [path.name for path in iter_task_dirs(tmp_path / ".harness-flow")]
    assert ordered == ["task-2", "task-9", "task-10"]


def test_iter_task_dirs_supports_jira_task_keys(tmp_path: Path):
    tasks_dir = tmp_path / ".harness-flow" / "tasks"
    for name in ("task-002", "PROJ-9", "task-010"):
        (tasks_dir / name).mkdir(parents=True)
    ordered = [path.name for path in iter_task_dirs(tmp_path / ".harness-flow")]
    assert ordered == ["task-002", "task-010", "PROJ-9"]


def test_resolve_task_dir_prefers_explicit_then_session_then_numeric_latest(tmp_path: Path):
    tasks_dir = tmp_path / ".harness-flow" / "tasks"
    for name in ("task-001", "task-002", "task-010"):
        (tasks_dir / name).mkdir(parents=True)

    explicit = resolve_task_dir(
        tmp_path / ".harness-flow",
        explicit_task_id="task-002",
        session_task_id="task-001",
    )
    session = resolve_task_dir(tmp_path / ".harness-flow", session_task_id="task-001")
    latest = resolve_task_dir(tmp_path / ".harness-flow")

    assert explicit is not None and explicit.name == "task-002"
    assert session is not None and session.name == "task-001"
    assert latest is not None and latest.name == "task-010"


def test_resolve_task_dir_rejects_path_traversal(tmp_path: Path):
    agents_dir = tmp_path / ".harness-flow"
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
    agents_dir = tmp_path / ".harness-flow"
    task1 = agents_dir / "tasks" / "task-001"
    task2 = agents_dir / "tasks" / "task-002"
    WorkflowState(task_id="task-001", phase=TaskState.PLANNING).save(task1)
    WorkflowState(task_id="task-002", phase=TaskState.BUILDING).save(task2)

    task_dir, state = load_current_workflow_state(agents_dir, session_task_id="task-001")
    assert task_dir is not None and task_dir.name == "task-001"
    assert state is not None and state.phase == TaskState.PLANNING


def test_load_current_workflow_state_prefers_explicit_task_id(tmp_path: Path):
    agents_dir = tmp_path / ".harness-flow"
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
    agents_dir = tmp_path / ".harness-flow"
    task2 = agents_dir / "tasks" / "task-002"
    WorkflowState(task_id="task-002", phase=TaskState.BUILDING).save(task2)

    task_dir, state = load_current_workflow_state(agents_dir, session_task_id="task-001")
    assert task_dir is None
    assert state is None


def test_handoff_field_round_trip(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    state = WorkflowState(task_id="task-001")
    state.artifacts.handoff = "handoff-build.json"
    state.save(task_dir)

    loaded = load_workflow_state(task_dir)
    assert loaded is not None
    assert loaded.artifacts.handoff == "handoff-build.json"


def test_artifact_pairs_includes_handoff(tmp_path: Path):
    state = WorkflowState(task_id="task-001")
    state.artifacts.plan = "plan.md"
    state.artifacts.handoff = "handoff-plan.json"

    pairs = artifact_pairs(state)
    labels = [label for label, _ in pairs]
    assert "plan" in labels
    assert "handoff" in labels


def test_artifact_pairs_omits_empty_handoff():
    state = WorkflowState(task_id="task-001")
    state.artifacts.plan = "plan.md"

    pairs = artifact_pairs(state)
    labels = [label for label, _ in pairs]
    assert "handoff" not in labels


def test_sync_task_state_updates_artifacts_and_gate(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    WorkflowState(task_id="task-001").save(task_dir)

    sync_task_state(
        task_dir,
        artifact_updates={"build_log": ".harness-flow/tasks/task-001/build-r1.md"},
        gate_updates={"plan_review": {"status": "pass", "reason": "approved"}},
        phase=TaskState.BUILDING,
    )

    loaded = load_workflow_state(task_dir)
    assert loaded is not None
    assert loaded.phase == TaskState.BUILDING
    assert loaded.artifacts.build_log == ".harness-flow/tasks/task-001/build-r1.md"
    assert loaded.gates.plan_review.status.value == "pass"
    assert loaded.gates.plan_review.reason == "approved"


def test_sync_task_state_rebuilds_invalid_existing_state(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    state_path = task_dir / WORKFLOW_STATE_FILENAME
    state_path.write_text("{broken", encoding="utf-8")

    import warnings as _warnings

    with _warnings.catch_warnings(record=True) as w:
        _warnings.simplefilter("always")
        result = sync_task_state(
            task_dir,
            artifact_updates={"build_log": ".harness-flow/tasks/task-001/build-r1.md"},
        )
    rebuild_warnings = [x for x in w if "Rebuilding corrupt" in str(x.message)]
    assert len(rebuild_warnings) >= 1
    assert result.task_id == "task-001"
    assert result.artifacts.build_log == ".harness-flow/tasks/task-001/build-r1.md"


def test_sync_task_state_rejects_artifact_ref_outside_task(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    WorkflowState(task_id="task-001").save(task_dir)

    import pytest

    with pytest.raises(ValueError, match="artifact ref"):
        sync_task_state(
            task_dir,
            artifact_updates={"build_log": "../outside.log"},
        )


def test_sync_task_state_rejects_unknown_artifact_keys(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    WorkflowState(task_id="task-001").save(task_dir)

    import pytest

    with pytest.raises(ValueError, match="unknown artifact_updates keys: not_a_field"):
        sync_task_state(task_dir, artifact_updates={"not_a_field": "x"})


def test_sync_task_state_rejects_unknown_gate_keys(tmp_path: Path):
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    WorkflowState(task_id="task-001").save(task_dir)

    import pytest

    with pytest.raises(ValueError, match="unknown gate_updates keys: not_a_gate"):
        sync_task_state(task_dir, gate_updates={"not_a_gate": {"status": "pass"}})


# --- B6: HARNESS_TASK_ID env support ---


def test_resolve_task_dir_explicit_takes_priority_over_env(tmp_path: Path):
    """explicit_task_id wins over env_task_id."""
    agents_dir = tmp_path / ".harness-flow"
    task3 = agents_dir / "tasks" / "task-003"
    task3.mkdir(parents=True)
    task5 = agents_dir / "tasks" / "task-005"
    task5.mkdir(parents=True)

    result = resolve_task_dir(agents_dir, explicit_task_id="task-003", env_task_id="task-005")
    assert result is not None
    assert result.name == "task-003"


def test_resolve_task_dir_env_takes_priority_over_session(tmp_path: Path):
    """HARNESS_TASK_ID env takes priority over session_task_id."""
    agents_dir = tmp_path / ".harness-flow"
    task5 = agents_dir / "tasks" / "task-005"
    task5.mkdir(parents=True)
    task3 = agents_dir / "tasks" / "task-003"
    task3.mkdir(parents=True)

    result = resolve_task_dir(agents_dir, env_task_id="task-005", session_task_id="task-003")
    assert result is not None
    assert result.name == "task-005"


def test_resolve_task_dir_env_fallback_on_missing(tmp_path: Path):
    """If env task dir doesn't exist, falls back to session."""
    agents_dir = tmp_path / ".harness-flow"
    task3 = agents_dir / "tasks" / "task-003"
    task3.mkdir(parents=True)

    result = resolve_task_dir(agents_dir, env_task_id="task-999", session_task_id="task-003")
    assert result is not None
    assert result.name == "task-003"


def test_resolve_task_dir_env_rejects_traversal(tmp_path: Path):
    """Invalid env task id (traversal) is rejected."""
    agents_dir = tmp_path / ".harness-flow"
    (agents_dir / "tasks" / "task-001").mkdir(parents=True)

    result = resolve_task_dir(agents_dir, env_task_id="../etc", session_task_id="task-001")
    assert result is not None
    assert result.name == "task-001"


def test_resolve_task_dir_env_rejects_non_task_format(tmp_path: Path):
    """Non task-NNN format env value is rejected."""
    agents_dir = tmp_path / ".harness-flow"
    (agents_dir / "tasks" / "task-001").mkdir(parents=True)

    result = resolve_task_dir(agents_dir, env_task_id="not-a-task")
    assert result is not None
    assert result.name == "task-001"


def test_resolve_task_dir_reads_env_var(tmp_path: Path, monkeypatch):
    """os.environ HARNESS_TASK_ID is read when env_task_id is None."""
    agents_dir = tmp_path / ".harness-flow"
    (agents_dir / "tasks" / "task-007").mkdir(parents=True)
    (agents_dir / "tasks" / "task-001").mkdir(parents=True)

    monkeypatch.setenv("HARNESS_TASK_ID", "task-007")
    result = resolve_task_dir(agents_dir)
    assert result is not None
    assert result.name == "task-007"


def test_load_current_workflow_state_env_skips_session_guard(tmp_path: Path):
    """When env_task_id resolves, session mismatch guard is skipped."""
    agents_dir = tmp_path / ".harness-flow"
    task5 = agents_dir / "tasks" / "task-005"
    WorkflowState(task_id="task-005", phase=TaskState.BUILDING).save(task5)

    task_dir, state = load_current_workflow_state(
        agents_dir,
        env_task_id="task-005",
        session_task_id="task-001",
    )
    assert task_dir is not None
    assert task_dir.name == "task-005"
    assert state is not None
    assert state.task_id == "task-005"


def test_load_current_workflow_state_no_env_keeps_session_guard(tmp_path: Path):
    """Without env/explicit, session mismatch guard still triggers."""
    agents_dir = tmp_path / ".harness-flow"
    task5 = agents_dir / "tasks" / "task-005"
    WorkflowState(task_id="task-005", phase=TaskState.BUILDING).save(task5)

    task_dir, state = load_current_workflow_state(
        agents_dir,
        session_task_id="task-001",
    )
    assert task_dir is None
    assert state is None


# ── D4: State transition validation ──────────────────────────────


class TestPhaseTransitionValidation:
    """D4: verify the transition table and validation behavior."""

    @pytest.mark.parametrize("old,new", [
        (TaskState.IDLE, TaskState.PLANNING),
        (TaskState.IDLE, TaskState.BUILDING),
        (TaskState.IDLE, TaskState.EVALUATING),
        (TaskState.PLANNING, TaskState.CONTRACTED),
        (TaskState.PLANNING, TaskState.BUILDING),
        (TaskState.PLANNING, TaskState.EVALUATING),
        (TaskState.CONTRACTED, TaskState.BUILDING),
        (TaskState.CONTRACTED, TaskState.EVALUATING),
        (TaskState.CONTRACTED, TaskState.PLANNING),
        (TaskState.BUILDING, TaskState.EVALUATING),
        (TaskState.BUILDING, TaskState.SHIPPING),
        (TaskState.EVALUATING, TaskState.SHIPPING),
        (TaskState.EVALUATING, TaskState.BUILDING),
        (TaskState.EVALUATING, TaskState.PLANNING),
        (TaskState.SHIPPING, TaskState.DONE),
        (TaskState.SHIPPING, TaskState.EVALUATING),
        (TaskState.SHIPPING, TaskState.BUILDING),
        (TaskState.SHIPPING, TaskState.LANDING),
        (TaskState.LANDING, TaskState.DONE),
        (TaskState.LANDING, TaskState.BLOCKED),
        (TaskState.LANDING, TaskState.SHIPPING),
        (TaskState.DONE, TaskState.IDLE),
        (TaskState.DONE, TaskState.PLANNING),
        (TaskState.DONE, TaskState.BUILDING),
        (TaskState.DONE, TaskState.EVALUATING),
        (TaskState.BLOCKED, TaskState.IDLE),
        (TaskState.BLOCKED, TaskState.BUILDING),
        (TaskState.BLOCKED, TaskState.EVALUATING),
    ])
    def test_valid_transitions_no_warning(self, old, new):
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            _validate_phase_transition(old, new)
        assert not caught

    @pytest.mark.parametrize("old,new", [
        (TaskState.IDLE, TaskState.SHIPPING),
        (TaskState.IDLE, TaskState.DONE),
        (TaskState.CONTRACTED, TaskState.SHIPPING),
        (TaskState.DONE, TaskState.SHIPPING),
    ])
    def test_invalid_transitions_warn(self, old, new):
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            _validate_phase_transition(old, new)
        assert any("illegal phase transition" in str(w.message).lower() for w in caught)

    @pytest.mark.parametrize("old,new", [
        (TaskState.IDLE, TaskState.SHIPPING),
        (TaskState.DONE, TaskState.SHIPPING),
    ])
    def test_invalid_transitions_strict_raises(self, old, new):
        with pytest.raises(ValueError, match="illegal phase transition"):
            _validate_phase_transition(old, new, strict=True)

    def test_self_transition_always_allowed(self):
        for state in TaskState:
            with _warnings.catch_warnings(record=True) as caught:
                _warnings.simplefilter("always")
                _validate_phase_transition(state, state)
            assert not caught

    def test_transition_table_covers_all_states(self):
        for state in TaskState:
            assert state in _VALID_TRANSITIONS, f"{state} missing from transition table"


class TestSyncTaskStateWithTransitionValidation:
    """D4: sync_task_state respects strict_transitions parameter."""

    def test_valid_transition_succeeds(self, tmp_path: Path):
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        WorkflowState(task_id="task-001", phase=TaskState.IDLE).save(task_dir)

        result = sync_task_state(task_dir, phase=TaskState.PLANNING)
        assert result.phase == TaskState.PLANNING

    def test_invalid_transition_warns_by_default(self, tmp_path: Path):
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        WorkflowState(task_id="task-001", phase=TaskState.IDLE).save(task_dir)

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            result = sync_task_state(task_dir, phase=TaskState.SHIPPING)
        assert result.phase == TaskState.SHIPPING
        assert any("illegal phase transition" in str(w.message).lower() for w in caught)

    def test_invalid_transition_strict_raises(self, tmp_path: Path):
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        WorkflowState(task_id="task-001", phase=TaskState.IDLE).save(task_dir)

        with pytest.raises(ValueError, match="illegal phase transition"):
            sync_task_state(task_dir, phase=TaskState.SHIPPING, strict_transitions=True)
