"""Progress helpers for workflow state display.

Provides shared summary helpers used by the ``harness status`` command
and progress-line output.
"""

from __future__ import annotations

from harness.core.state import TaskState
from harness.core.workflow_state import WorkflowState


def workflow_phase_user_label(phase: TaskState) -> str:
    """Map persisted workflow phase to a short, user-facing label (i18n)."""
    from harness.i18n import t

    key = f"workflow.phase.{phase.value}"
    label = t(key)
    if label == key:
        return t("workflow.phase.fallback")
    return label


def suggest_next_action(workflow_state: WorkflowState | None = None) -> str:
    """Derive a human-readable next-step suggestion from the current workflow state."""
    from harness.i18n import t

    if workflow_state and workflow_state.blocker.reason:
        return t("progress.blocked", reason=workflow_state.blocker.reason)
    if workflow_state and workflow_state.phase not in {TaskState.IDLE, TaskState.DONE}:
        phase = workflow_phase_user_label(workflow_state.phase)
        if workflow_state.active_plan.title:
            return t("progress.phase_with_plan", phase=phase, title=workflow_state.active_plan.title)
        return t("progress.phase_active", phase=phase)
    return t("progress.fresh")
