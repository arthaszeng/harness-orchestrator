"""status.py 单元测试"""

from __future__ import annotations

import io

from rich.console import Console

from harness.commands.status import (
    _render_current,
    _render_header,
    _render_next_action,
    _render_recent_result,
    _render_resume,
    _render_stats,
)
from harness.core.state import (
    CompletedTask,
    SessionState,
    SessionStats,
    TaskRecord,
    TaskState,
)
from harness.core.ui import CYBER_THEME


def _make_console():
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=True, width=100,
        theme=CYBER_THEME, highlight=False,
    )
    return console, buf


class TestRenderCurrent:
    def test_no_task(self):
        console, buf = _make_console()
        state = SessionState()
        _render_current(console, state)
        assert buf.getvalue() == ""

    def test_active_task(self):
        console, buf = _make_console()
        state = SessionState(
            current_task=TaskRecord(
                id="t1",
                requirement="build feature",
                state=TaskState.BUILDING,
                iteration=2,
                branch="agent/feat",
            ),
        )
        _render_current(console, state)
        output = buf.getvalue()
        assert "build feature" in output
        assert "building" in output
        assert "2" in output
        assert "agent/feat" in output


class TestRenderRecentResult:
    def test_no_results(self):
        console, buf = _make_console()
        state = SessionState()
        _render_recent_result(console, state)
        assert buf.getvalue() == ""

    def test_completed_result(self):
        console, buf = _make_console()
        state = SessionState(completed=[
            CompletedTask(id="t1", requirement="done task", score=4.0, verdict="PASS", iterations=2),
        ])
        _render_recent_result(console, state)
        output = buf.getvalue()
        assert "done task" in output
        assert "4.0" in output
        assert "PASS" in output

    def test_blocked_result(self):
        console, buf = _make_console()
        state = SessionState(blocked=[
            CompletedTask(id="t1", requirement="stuck task", score=1.0, verdict="BLOCKED", iterations=3),
        ])
        _render_recent_result(console, state)
        output = buf.getvalue()
        assert "stuck task" in output
        assert "1.0" in output

    def test_both_results(self):
        console, buf = _make_console()
        state = SessionState(
            completed=[CompletedTask(id="t1", requirement="good", score=4.0, verdict="PASS")],
            blocked=[CompletedTask(id="t2", requirement="bad", score=0.0, verdict="BLOCKED")],
        )
        _render_recent_result(console, state)
        output = buf.getvalue()
        assert "good" in output
        assert "bad" in output


class TestRenderResume:
    def test_idle_no_resume(self):
        console, buf = _make_console()
        state = SessionState(mode="idle")
        _render_resume(console, state)
        assert buf.getvalue() == ""

    def test_run_resumable(self):
        console, buf = _make_console()
        state = SessionState(
            session_id="s1",
            mode="run",
            current_task=TaskRecord(id="t1", requirement="x"),
        )
        _render_resume(console, state)
        output = buf.getvalue()
        assert "resume" in output.lower()
        assert "harness run --resume" in output

    def test_auto_resumable(self):
        console, buf = _make_console()
        state = SessionState(
            session_id="s1",
            mode="auto",
            current_task=TaskRecord(id="t1", requirement="x"),
        )
        _render_resume(console, state)
        output = buf.getvalue()
        assert "harness auto --resume" in output


class TestRenderNextAction:
    def test_fresh_state(self):
        console, buf = _make_console()
        state = SessionState(mode="idle")
        _render_next_action(console, state)
        output = buf.getvalue()
        assert "Next Action" in output

    def test_resumable_action(self):
        console, buf = _make_console()
        state = SessionState(
            mode="run",
            current_task=TaskRecord(id="t1", requirement="x"),
        )
        _render_next_action(console, state)
        output = buf.getvalue()
        assert "harness run --resume" in output


class TestRunStatusScenarios:
    def test_empty_state_renders_header(self):
        console, buf = _make_console()
        state = SessionState()
        _render_header(console, state)
        output = buf.getvalue()
        assert "HARNESS" in output

    def test_completed_scenario(self):
        console, buf = _make_console()
        state = SessionState(
            session_id="2026-01-01T00:00:00",
            mode="idle",
            completed=[
                CompletedTask(id="t1", requirement="feature A", score=4.5, verdict="PASS", iterations=1),
            ],
            stats=SessionStats(total_tasks=1, completed=1, avg_score=4.5, total_iterations=1),
        )
        _render_header(console, state)
        _render_current(console, state)
        _render_recent_result(console, state)
        _render_resume(console, state)
        _render_next_action(console, state)
        _render_stats(console, state)
        output = buf.getvalue()
        assert "HARNESS" in output
        assert "feature A" in output
        assert "4.5" in output
        assert "Next Action" in output
        assert "harness run --resume" not in output

    def test_resumable_scenario(self):
        console, buf = _make_console()
        state = SessionState(
            session_id="s-resume",
            mode="auto",
            current_task=TaskRecord(
                id="t1",
                requirement="in-flight work",
                state=TaskState.BUILDING,
                iteration=1,
                branch="agent/work",
            ),
        )
        _render_header(console, state)
        _render_current(console, state)
        _render_recent_result(console, state)
        _render_resume(console, state)
        _render_next_action(console, state)
        _render_stats(console, state)
        output = buf.getvalue()
        assert "in-flight work" in output
        assert "building" in output
        assert "harness auto --resume" in output
        assert "s-resume" in output

    def test_blocked_scenario(self):
        console, buf = _make_console()
        state = SessionState(
            session_id="s-blocked",
            mode="idle",
            blocked=[
                CompletedTask(id="t1", requirement="broken thing", score=0.0, verdict="BLOCKED", iterations=3),
            ],
            stats=SessionStats(total_tasks=1, blocked=1),
        )
        _render_header(console, state)
        _render_current(console, state)
        _render_recent_result(console, state)
        _render_resume(console, state)
        _render_next_action(console, state)
        _render_stats(console, state)
        output = buf.getvalue()
        assert "broken thing" in output
