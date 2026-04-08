"""status.py unit tests — WorkflowState-based rendering"""

from __future__ import annotations

import io

from rich.console import Console

from harness.commands.status import (
    _render_current,
    _render_task_headline,
)
from harness.core.progress import suggest_next_action
from harness.core.state import TaskState
from harness.core.ui import CYBER_THEME
from harness.core.workflow_state import GateStatus, WorkflowState


def _make_console():
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=True, width=100,
        theme=CYBER_THEME, highlight=False,
    )
    return console, buf


class TestRenderCurrent:
    def test_workflow_state_details(self):
        console, buf = _make_console()
        workflow_state = WorkflowState(
            task_id="task-001",
            branch="agent/task-001-workflow-intelligence",
            phase=TaskState.EVALUATING,
            iteration=3,
        )
        workflow_state.active_plan.title = "Canonical Workflow State Artifact"
        workflow_state.blocker.reason = "missing ship readiness gate"
        workflow_state.artifacts.plan = ".harness-flow/tasks/task-001/plan.md"
        workflow_state.gates.evaluation.reason = "awaiting review"
        workflow_state.gates.evaluation.status = GateStatus.PENDING
        _render_current(console, workflow_state)
        output = buf.getvalue()
        assert "evaluating" in output
        assert "Canonical Workflow State Artifact" in output
        assert "missing ship readiness gate" in output
        assert "plan.md" in output
        assert "awaiting review" in output
        assert "workflow-state.json" in output


class TestRenderTaskHeadline:
    def test_shows_plan_title(self):
        console, buf = _make_console()
        ws = WorkflowState(task_id="task-001")
        ws.active_plan.title = "My Great Plan"
        _render_task_headline(console, ws)
        output = buf.getvalue()
        assert "My Great Plan" in output

    def test_shows_task_id_when_no_title(self):
        console, buf = _make_console()
        ws = WorkflowState(task_id="task-042")
        _render_task_headline(console, ws)
        output = buf.getvalue()
        assert "task-042" in output


class TestSuggestNextActionIntegration:
    @classmethod
    def setup_class(cls):
        from harness.i18n import set_lang
        set_lang("zh")

    @classmethod
    def teardown_class(cls):
        from harness.i18n import set_lang
        set_lang("en")

    def test_fresh_state(self):
        action = suggest_next_action()
        assert "harness 技能" in action

    def test_blocker_shown(self):
        ws = WorkflowState(task_id="task-001")
        ws.blocker.reason = "tests failing"
        action = suggest_next_action(ws)
        assert "阻塞" in action
