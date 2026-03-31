"""state.py 单元测试"""

from pathlib import Path

import pytest

from harness.core.state import (
    SessionState,
    StateMachine,
    TaskRecord,
    TaskState,
)


def test_session_save_load(tmp_path: Path):
    state = SessionState(session_id="test-001", mode="auto")
    agents_dir = tmp_path / ".agents"
    state.save(agents_dir)

    loaded = SessionState.load(agents_dir)
    assert loaded.session_id == "test-001"
    assert loaded.mode == "auto"


def test_detect_incomplete(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    # 空状态 → 无未完成
    assert SessionState.detect_incomplete(agents_dir) is None

    # 有活跃任务
    state = SessionState(
        session_id="test",
        mode="run",
        current_task=TaskRecord(id="t1", requirement="test"),
    )
    state.save(agents_dir)
    incomplete = SessionState.detect_incomplete(agents_dir)
    assert incomplete is not None
    assert incomplete.current_task.id == "t1"


def test_state_machine_transitions(tmp_path: Path):
    sm = StateMachine(tmp_path)
    sm.start_session("run")
    sm.start_task("t1", "do something", "agent/test")

    sm.transition(TaskState.PLANNING)
    assert sm.state.current_task.state == TaskState.PLANNING
    assert sm.state.current_task.iteration == 1

    sm.transition(TaskState.CONTRACTED)
    sm.transition(TaskState.BUILDING)
    sm.transition(TaskState.EVALUATING)
    sm.transition(TaskState.DONE)

    sm.complete_task(score=4.0, verdict="PASS")
    assert len(sm.state.completed) == 1
    assert sm.state.stats.completed == 1


def test_invalid_transition(tmp_path: Path):
    sm = StateMachine(tmp_path)
    sm.start_session("run")
    sm.start_task("t1", "test", "agent/test")

    with pytest.raises(ValueError, match="Illegal transition"):
        sm.transition(TaskState.EVALUATING)  # IDLE → EVALUATING invalid


def test_stop_signal(tmp_path: Path):
    sm = StateMachine(tmp_path)
    sm.start_session("run")  # 确保 .agents 目录存在
    assert not sm.stop_requested()

    (tmp_path / ".agents" / ".stop").write_text("stop", encoding="utf-8")
    assert sm.stop_requested()

    sm.clear_stop_signal()
    assert not sm.stop_requested()


def test_checkpoint_refreshes_progress_md(tmp_path: Path):
    """_checkpoint() 应在每次状态变化后自动刷新 progress.md。"""
    sm = StateMachine(tmp_path)
    progress_path = tmp_path / ".agents" / "progress.md"

    sm.start_session("run")
    assert progress_path.exists(), "progress.md should be created on start_session"

    sm.start_task("t1", "test requirement", "agent/test")
    content = progress_path.read_text(encoding="utf-8")
    assert "test requirement" in content

    sm.transition(TaskState.PLANNING)
    content = progress_path.read_text(encoding="utf-8")
    assert "planning" in content

    sm.transition(TaskState.CONTRACTED)
    content = progress_path.read_text(encoding="utf-8")
    assert "contracted" in content

    sm.transition(TaskState.BUILDING)
    content = progress_path.read_text(encoding="utf-8")
    assert "building" in content


def test_progress_md_reflects_completed_task(tmp_path: Path):
    """complete_task() 后 progress.md 应包含完成结果摘要。"""
    sm = StateMachine(tmp_path)
    sm.start_session("run")
    sm.start_task("t1", "implement feature", "agent/feat")
    sm.transition(TaskState.PLANNING)
    sm.transition(TaskState.CONTRACTED)
    sm.transition(TaskState.BUILDING)
    sm.transition(TaskState.EVALUATING)
    sm.transition(TaskState.DONE)
    sm.complete_task(score=4.2, verdict="PASS")

    content = (tmp_path / ".agents" / "progress.md").read_text(encoding="utf-8")
    assert "implement feature" in content
    assert "4.2" in content
    assert "PASS" in content
    assert "Recent Completed" in content


def test_progress_md_reflects_blocked_task(tmp_path: Path):
    """阻塞任务后 progress.md 应包含阻塞结果摘要。"""
    sm = StateMachine(tmp_path)
    sm.start_session("run")
    sm.start_task("t1", "broken feature", "agent/broken")
    sm.transition(TaskState.PLANNING)
    sm.transition(TaskState.BLOCKED)
    sm.complete_task(score=0.0, verdict="BLOCKED")

    content = (tmp_path / ".agents" / "progress.md").read_text(encoding="utf-8")
    assert "broken feature" in content
    assert "Recent Blocked" in content
    assert "BLOCKED" in content


def test_end_session_not_resumable(tmp_path: Path):
    """end_session() 后 progress.md 不应标记为可恢复。"""
    sm = StateMachine(tmp_path)
    sm.start_session("auto")
    sm.end_session()

    content = (tmp_path / ".agents" / "progress.md").read_text(encoding="utf-8")
    assert "无可恢复会话" in content


def test_active_session_is_resumable_in_progress(tmp_path: Path):
    """有活跃任务时 progress.md 应标记为可恢复。"""
    sm = StateMachine(tmp_path)
    sm.start_session("run")
    sm.start_task("t1", "some work", "agent/work")

    content = (tmp_path / ".agents" / "progress.md").read_text(encoding="utf-8")
    assert "会话可恢复" in content
    assert "harness run --resume" in content


def test_detect_incomplete_idle_not_resumable(tmp_path: Path):
    """idle 模式即使有历史数据也不应被视为未完成。"""
    agents_dir = tmp_path / ".agents"
    state = SessionState(session_id="s1", mode="idle", current_task=None)
    state.save(agents_dir)
    assert SessionState.detect_incomplete(agents_dir) is None
