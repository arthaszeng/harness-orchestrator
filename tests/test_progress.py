"""progress.py unit tests — workflow-based helpers"""

from __future__ import annotations

import pytest

from harness.core.progress import (
    suggest_next_action,
    workflow_phase_user_label,
)
from harness.core.state import TaskState
from harness.core.workflow_state import WorkflowState


class TestSuggestNextAction:
    @classmethod
    def setup_class(cls):
        from harness.i18n import set_lang
        set_lang("zh")

    @classmethod
    def teardown_class(cls):
        from harness.i18n import set_lang
        set_lang("en")

    def test_workflow_blocker_takes_precedence(self):
        workflow_state = WorkflowState(task_id="task-001")
        workflow_state.blocker.reason = "missing evaluation artifact"
        action = suggest_next_action(workflow_state)
        assert "阻塞" in action
        assert "missing evaluation artifact" in action

    def test_fresh_state(self):
        action = suggest_next_action()
        assert "harness 技能" in action

    def test_none_workflow_state(self):
        action = suggest_next_action(None)
        assert "harness 技能" in action

    def test_workflow_phase_uses_task_language_not_raw_enum(self):
        workflow_state = WorkflowState(task_id="task-001", phase=TaskState.EVALUATING)
        workflow_state.active_plan.title = "Roadmap B2"
        action = suggest_next_action(workflow_state)
        assert "evaluating" not in action.lower()
        assert "代码评审" in action

    def test_workflow_phase_with_plan_title(self):
        workflow_state = WorkflowState(task_id="task-001", phase=TaskState.BUILDING)
        workflow_state.active_plan.title = "Build feature X"
        action = suggest_next_action(workflow_state)
        assert "Build feature X" in action

    @pytest.mark.parametrize("phase", list(TaskState))
    def test_workflow_phase_user_label_en_not_raw_enum_string(self, phase):
        from harness.i18n import set_lang

        set_lang("en")
        label = workflow_phase_user_label(phase)
        assert label != phase.value
