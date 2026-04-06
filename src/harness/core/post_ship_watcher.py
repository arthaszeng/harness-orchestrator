"""PR merge watcher for post-ship auto finalization."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from harness.core.post_ship import PostShipManager
from harness.integrations.git_ops import GitOperationResult


@dataclass
class PostShipWatcher:
    """Poll PR state and trigger post-ship finalization on merge."""

    manager: PostShipManager

    @classmethod
    def create(cls, project_root: Path | None = None) -> "PostShipWatcher":
        return cls(manager=PostShipManager.create(project_root))

    def wait_and_finalize(
        self,
        *,
        task_key: str,
        pr_number: int | None,
        branch: str | None = None,
        timeout_sec: int = 86400,
        poll_interval_sec: int = 30,
    ) -> GitOperationResult:
        start = time.time()
        while (time.time() - start) < timeout_sec:
            state = self.manager.check_pr_state(pr_number=pr_number, branch=branch)
            if state.code == "PR_MERGED":
                return self.manager.finalize_after_merge(
                    task_key=task_key,
                    pr_number=pr_number,
                    branch=branch,
                )
            if state.code == "PR_CLOSED_UNMERGED":
                return state
            if state.code not in {"PR_NOT_MERGED", "PR_LOOKUP_FAILED", "PR_STATE_UNKNOWN"} and not state.code.startswith("PR_LOOKUP_"):
                return state
            time.sleep(max(1, poll_interval_sec))

        return GitOperationResult(
            ok=False,
            code="PR_WAIT_TIMEOUT",
            message="timed out waiting for PR merge; rerun post-ship later",
            context={"task_key": task_key, "timeout_sec": str(timeout_sec)},
        )
