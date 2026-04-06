"""Tests for post-ship merge watcher."""

from __future__ import annotations

from harness.core.post_ship_watcher import PostShipWatcher
from harness.integrations.git_ops import GitOperationResult


class _Manager:
    def __init__(self):
        self.check_calls = 0
        self.finalize_calls = 0

    def check_pr_state(self, *, pr_number, branch):
        self.check_calls += 1
        if self.check_calls < 3:
            return GitOperationResult(ok=False, code="PR_NOT_MERGED", message="open")
        return GitOperationResult(ok=True, code="PR_MERGED", message="merged")

    def finalize_after_merge(self, *, task_key, pr_number, branch):
        self.finalize_calls += 1
        return GitOperationResult(ok=True, code="POST_SHIP_DONE", message="done", context={"task_key": task_key})


def test_wait_and_finalize_auto_triggers_on_merge(monkeypatch):
    manager = _Manager()
    watcher = PostShipWatcher(manager=manager)
    monkeypatch.setattr("harness.core.post_ship_watcher.time.sleep", lambda _v: None)

    ticks = iter([0, 1, 2, 3, 4, 5])
    monkeypatch.setattr("harness.core.post_ship_watcher.time.time", lambda: next(ticks))

    result = watcher.wait_and_finalize(task_key="task-006", pr_number=64, timeout_sec=10, poll_interval_sec=1)
    assert result.ok is True
    assert result.code == "POST_SHIP_DONE"
    assert manager.finalize_calls == 1


def test_wait_and_finalize_timeout(monkeypatch):
    class _NeverMerged:
        def check_pr_state(self, *, pr_number, branch):
            return GitOperationResult(ok=False, code="PR_NOT_MERGED", message="open")

        def finalize_after_merge(self, *, task_key, pr_number, branch):
            return GitOperationResult(ok=True, code="POST_SHIP_DONE", message="done")

    watcher = PostShipWatcher(manager=_NeverMerged())
    monkeypatch.setattr("harness.core.post_ship_watcher.time.sleep", lambda _v: None)
    ticks = iter([0, 1, 2, 3, 4, 5, 6])
    monkeypatch.setattr("harness.core.post_ship_watcher.time.time", lambda: next(ticks))

    result = watcher.wait_and_finalize(task_key="task-006", pr_number=64, timeout_sec=3, poll_interval_sec=1)
    assert result.ok is False
    assert result.code == "PR_WAIT_TIMEOUT"


def test_wait_and_finalize_stops_on_closed_unmerged(monkeypatch):
    class _Closed:
        def __init__(self):
            self.finalize_calls = 0

        def check_pr_state(self, *, pr_number, branch):
            return GitOperationResult(ok=False, code="PR_CLOSED_UNMERGED", message="closed")

        def finalize_after_merge(self, *, task_key, pr_number, branch):
            self.finalize_calls += 1
            return GitOperationResult(ok=True, code="POST_SHIP_DONE", message="done")

    manager = _Closed()
    watcher = PostShipWatcher(manager=manager)
    monkeypatch.setattr("harness.core.post_ship_watcher.time.sleep", lambda _v: None)
    result = watcher.wait_and_finalize(task_key="task-006", pr_number=64, timeout_sec=10, poll_interval_sec=1)
    assert result.ok is False
    assert result.code == "PR_CLOSED_UNMERGED"
    assert manager.finalize_calls == 0


def test_wait_and_finalize_retries_unknown_state(monkeypatch):
    class _UnknownThenMerged:
        def __init__(self):
            self.calls = 0

        def check_pr_state(self, *, pr_number, branch):
            self.calls += 1
            if self.calls < 3:
                return GitOperationResult(ok=False, code="PR_STATE_UNKNOWN", message="temporary")
            return GitOperationResult(ok=True, code="PR_MERGED", message="merged")

        def finalize_after_merge(self, *, task_key, pr_number, branch):
            return GitOperationResult(ok=True, code="POST_SHIP_DONE", message="done")

    watcher = PostShipWatcher(manager=_UnknownThenMerged())
    monkeypatch.setattr("harness.core.post_ship_watcher.time.sleep", lambda _v: None)
    ticks = iter([0, 1, 2, 3, 4, 5])
    monkeypatch.setattr("harness.core.post_ship_watcher.time.time", lambda: next(ticks))

    result = watcher.wait_and_finalize(task_key="task-006", pr_number=64, timeout_sec=10, poll_interval_sec=1)
    assert result.ok is True
    assert result.code == "POST_SHIP_DONE"
