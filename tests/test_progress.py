"""progress.py 单元测试 — 覆盖 helper 函数和 progress.md 结构"""

from __future__ import annotations

from pathlib import Path

from harness.core.progress import (
    get_recent_blocked,
    get_recent_completed,
    is_resumable,
    suggest_next_action,
    update_progress,
)
from harness.core.state import (
    CompletedTask,
    SessionState,
    TaskRecord,
    TaskState,
)
from harness.core.workflow_state import GateStatus, WorkflowState


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestGetRecentCompleted:
    def test_empty(self):
        state = SessionState()
        assert get_recent_completed(state) is None

    def test_returns_last(self):
        state = SessionState(completed=[
            CompletedTask(id="t1", requirement="first", score=3.0, verdict="PASS", iterations=1),
            CompletedTask(id="t2", requirement="second", score=4.0, verdict="PASS", iterations=2),
        ])
        result = get_recent_completed(state)
        assert result is not None
        assert result.id == "t2"


class TestGetRecentBlocked:
    def test_empty(self):
        state = SessionState()
        assert get_recent_blocked(state) is None

    def test_returns_last(self):
        state = SessionState(blocked=[
            CompletedTask(id="t1", requirement="first", score=0.0, verdict="BLOCKED", iterations=3),
            CompletedTask(id="t2", requirement="second", score=1.0, verdict="BLOCKED", iterations=2),
        ])
        result = get_recent_blocked(state)
        assert result is not None
        assert result.id == "t2"


class TestIsResumable:
    def test_idle_no_task(self):
        state = SessionState(mode="idle")
        assert not is_resumable(state)

    def test_run_with_task(self):
        state = SessionState(
            mode="run",
            current_task=TaskRecord(id="t1", requirement="test"),
        )
        assert is_resumable(state)

    def test_auto_with_task(self):
        state = SessionState(
            mode="auto",
            current_task=TaskRecord(id="t1", requirement="test"),
        )
        assert is_resumable(state)

    def test_run_no_task(self):
        """mode=run 但无 current_task 不算可恢复（理论上不应出现）"""
        state = SessionState(mode="run", current_task=None)
        assert not is_resumable(state)

    def test_idle_with_completed(self):
        """已完成会话不应被标记为可恢复"""
        state = SessionState(
            mode="idle",
            completed=[
                CompletedTask(id="t1", requirement="done", score=4.0, verdict="PASS", iterations=1),
            ],
        )
        assert not is_resumable(state)


class TestSuggestNextAction:
    def test_workflow_blocker_takes_precedence(self):
        state = SessionState(mode="idle")
        workflow_state = WorkflowState(task_id="task-001")
        workflow_state.blocker.reason = "missing evaluation artifact"
        action = suggest_next_action(state, workflow_state)
        assert "阻塞" in action
        assert "missing evaluation artifact" in action

    def test_resumable_run(self):
        state = SessionState(
            mode="run",
            current_task=TaskRecord(id="t1", requirement="x"),
        )
        action = suggest_next_action(state)
        assert "会话可恢复" in action
        assert "harness 技能" in action

    def test_resumable_auto(self):
        state = SessionState(
            mode="auto",
            current_task=TaskRecord(id="t1", requirement="x"),
        )
        action = suggest_next_action(state)
        assert "会话可恢复" in action

    def test_idle_with_completed(self):
        state = SessionState(
            mode="idle",
            completed=[CompletedTask(id="t1", requirement="x", score=4.0, verdict="PASS")],
        )
        action = suggest_next_action(state)
        assert "harness 技能" in action

    def test_all_blocked(self):
        state = SessionState(
            mode="idle",
            blocked=[CompletedTask(id="t1", requirement="x", score=0.0, verdict="BLOCKED")],
        )
        action = suggest_next_action(state)
        assert "阻塞" in action

    def test_fresh_state(self):
        state = SessionState()
        action = suggest_next_action(state)
        assert "harness 技能" in action


# ---------------------------------------------------------------------------
# progress.md generation tests
# ---------------------------------------------------------------------------


class TestUpdateProgress:
    def test_creates_file(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        state = SessionState(session_id="s1", mode="run")
        update_progress(agents_dir, state)
        assert (agents_dir / "progress.md").exists()

    def test_contains_session_meta(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        state = SessionState(session_id="2026-01-01T00:00:00", mode="auto")
        update_progress(agents_dir, state)
        content = (agents_dir / "progress.md").read_text(encoding="utf-8")
        assert "2026-01-01T00:00:00" in content
        assert "auto" in content
        assert "active" in content

    def test_contains_current_task(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        state = SessionState(
            session_id="s1",
            mode="run",
            current_task=TaskRecord(
                id="t1",
                requirement="implement API",
                state=TaskState.BUILDING,
                iteration=2,
                branch="agent/api",
            ),
        )
        update_progress(agents_dir, state)
        content = (agents_dir / "progress.md").read_text(encoding="utf-8")
        assert "implement API" in content
        assert "building" in content
        assert "iteration 2" in content
        assert "agent/api" in content

    def test_includes_canonical_workflow_state_details(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        task_dir = agents_dir / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        agents_dir.mkdir(exist_ok=True)
        workflow_state = WorkflowState(
            task_id="task-001",
            phase=TaskState.EVALUATING,
            iteration=3,
        )
        workflow_state.active_plan.title = "Canonical Workflow State Artifact"
        workflow_state.blocker.reason = "awaiting eval gate"
        workflow_state.artifacts.plan = ".agents/tasks/task-001/plan.md"
        workflow_state.gates.ship_readiness.status = GateStatus.PENDING
        workflow_state.gates.ship_readiness.reason = "waiting for evaluation"
        workflow_state.save(task_dir)

        state = SessionState(mode="idle")
        update_progress(agents_dir, state)
        content = (agents_dir / "progress.md").read_text(encoding="utf-8")
        assert "Canonical phase" in content
        assert "evaluating" in content
        assert "awaiting eval gate" in content
        assert "Artifact refs" in content
        assert "plan.md" in content
        assert "ship_readiness=pending" in content
        assert "workflow-state.json" in content

    def test_resumable_section(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        state = SessionState(
            session_id="s1",
            mode="run",
            current_task=TaskRecord(id="t1", requirement="x"),
        )
        update_progress(agents_dir, state)
        content = (agents_dir / "progress.md").read_text(encoding="utf-8")
        assert "会话可恢复" in content
        assert "harness 技能" in content

    def test_idle_not_resumable(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        state = SessionState(session_id="s1", mode="idle")
        update_progress(agents_dir, state)
        content = (agents_dir / "progress.md").read_text(encoding="utf-8")
        assert "无可恢复会话" in content

    def test_contains_next_action(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        state = SessionState(session_id="s1", mode="idle")
        update_progress(agents_dir, state)
        content = (agents_dir / "progress.md").read_text(encoding="utf-8")
        assert "Next Action" in content
