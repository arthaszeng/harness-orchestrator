"""Tests for persistent post-ship pending fallback queue."""

from __future__ import annotations

from pathlib import Path

from harness.core.post_ship_pending import (
    enqueue_pending_post_ship,
    has_pending_post_ship,
    is_auto_reconcile_eligible_subcommand,
    reconcile_pending_post_ship,
)
from harness.integrations.git_ops import GitOperationResult


class _Manager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.finalize_calls = 0

    def check_pr_state(self, *, pr_number, branch):
        _ = (pr_number, branch)
        return GitOperationResult(ok=False, code="PR_NOT_MERGED", message="open")

    def finalize_after_merge(self, *, task_key, pr_number, branch):
        _ = (task_key, pr_number, branch)
        self.finalize_calls += 1
        return GitOperationResult(ok=True, code="POST_SHIP_DONE", message="done")


def test_enqueue_pending_dedupes(tmp_path: Path):
    added = enqueue_pending_post_ship(tmp_path, task_key="task-009", pr_number=99, branch="agent/task-009-a")
    added_dup = enqueue_pending_post_ship(tmp_path, task_key="task-009", pr_number=99, branch="agent/task-009-a")
    assert added is True
    assert added_dup is False


def test_has_pending_post_ship_false_when_queue_missing(tmp_path: Path):
    assert has_pending_post_ship(tmp_path) is False


def test_has_pending_post_ship_true_when_queue_non_empty(tmp_path: Path):
    queue = tmp_path / ".harness-flow" / "post-ship-pending.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text('{"task_key":"task-009"}\n', encoding="utf-8")
    assert has_pending_post_ship(tmp_path) is True


def test_has_pending_post_ship_false_when_queue_empty(tmp_path: Path):
    queue = tmp_path / ".harness-flow" / "post-ship-pending.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("", encoding="utf-8")
    assert has_pending_post_ship(tmp_path) is False


def test_auto_reconcile_eligible_subcommand_matrix():
    assert is_auto_reconcile_eligible_subcommand("init") is True
    assert is_auto_reconcile_eligible_subcommand("status") is True
    assert is_auto_reconcile_eligible_subcommand("gate") is True
    assert is_auto_reconcile_eligible_subcommand("update") is True
    assert is_auto_reconcile_eligible_subcommand("save-build-log") is False
    assert is_auto_reconcile_eligible_subcommand("save-ship-metrics") is False
    assert is_auto_reconcile_eligible_subcommand("save-feedback-ledger") is False
    assert is_auto_reconcile_eligible_subcommand("save-intervention-audit") is False


def test_reconcile_pending_keeps_open_entries(tmp_path: Path):
    enqueue_pending_post_ship(tmp_path, task_key="task-009", pr_number=99, branch="agent/task-009-a")
    stats = reconcile_pending_post_ship(_Manager(tmp_path), max_items=20)
    assert stats["processed"] == 1
    assert stats["retained"] == 1
    assert stats["merged"] == 0


def test_reconcile_pending_merged_entry_removed(tmp_path: Path):
    class _MergedManager(_Manager):
        def check_pr_state(self, *, pr_number, branch):
            _ = (pr_number, branch)
            return GitOperationResult(ok=True, code="PR_MERGED", message="merged")

    manager = _MergedManager(tmp_path)
    enqueue_pending_post_ship(tmp_path, task_key="task-009", pr_number=99, branch="agent/task-009-a")
    stats = reconcile_pending_post_ship(manager, max_items=20)
    assert stats["processed"] == 1
    assert stats["merged"] == 1
    assert manager.finalize_calls == 1


def test_reconcile_pending_closed_unmerged_removed_without_finalize(tmp_path: Path):
    class _ClosedManager(_Manager):
        def check_pr_state(self, *, pr_number, branch):
            _ = (pr_number, branch)
            return GitOperationResult(ok=False, code="PR_CLOSED_UNMERGED", message="closed")

    manager = _ClosedManager(tmp_path)
    enqueue_pending_post_ship(tmp_path, task_key="task-009", pr_number=99, branch="agent/task-009-a")
    stats = reconcile_pending_post_ship(manager, max_items=20)
    assert stats["processed"] == 1
    assert stats["closed"] == 1
    assert manager.finalize_calls == 0


class TestLoadPendingCorruptLines:
    """D4: corrupt JSONL lines emit warnings instead of silent discard."""

    def test_corrupt_line_warns(self, tmp_path: Path):
        import warnings as _warnings
        from harness.core.post_ship_pending import _load_pending

        path = tmp_path / "pending.jsonl"
        path.write_text(
            '{"task_key": "task-001", "pr_number": 1}\n'
            '{not valid json}\n'
            '{"task_key": "task-002", "pr_number": 2}\n',
            encoding="utf-8",
        )

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            rows = _load_pending(path)

        assert len(rows) == 2
        assert any("corrupt jsonl" in str(w.message).lower() for w in caught)
        assert any("line 2" in str(w.message) for w in caught)

    def test_all_corrupt_returns_empty_with_warnings(self, tmp_path: Path):
        import warnings as _warnings
        from harness.core.post_ship_pending import _load_pending

        path = tmp_path / "pending.jsonl"
        path.write_text("{bad1}\n{bad2}\n", encoding="utf-8")

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            rows = _load_pending(path)

        assert rows == []
        assert len(caught) == 2
