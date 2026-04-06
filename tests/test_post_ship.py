"""Tests for post-ship lifecycle orchestration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from harness.core.post_ship import PostShipManager
from harness.integrations.git_ops import GitOperationResult


class _Resolver:
    def extract_from_branch(self, branch: str, *, branch_prefix: str = "agent") -> str | None:
        prefix = f"{branch_prefix}/"
        if not branch.startswith(prefix):
            return None
        remainder = branch[len(prefix):]
        return remainder.split("-", 1)[0]


class _BranchManager:
    trunk_branch = "main"
    branch_prefix = "agent"
    resolver = _Resolver()


def _manager(tmp_path: Path) -> PostShipManager:
    return PostShipManager(project_root=tmp_path, branch_manager=_BranchManager())


def test_check_pr_state_reports_open(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    payload = {"number": 64, "state": "OPEN", "url": "https://example/pr/64", "mergedAt": None}

    monkeypatch.setattr(
        "harness.core.post_ship.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""),
    )
    result = manager.check_pr_state(pr_number=64, branch=None)
    assert result.ok is False
    assert result.code == "PR_NOT_MERGED"


def test_check_pr_state_reports_closed_unmerged(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    payload = {"number": 64, "state": "CLOSED", "url": "https://example/pr/64", "mergedAt": None}
    monkeypatch.setattr(
        "harness.core.post_ship.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""),
    )
    result = manager.check_pr_state(pr_number=64, branch=None)
    assert result.ok is False
    assert result.code == "PR_CLOSED_UNMERGED"


def test_load_pr_payload_prefers_pr_number_over_branch(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    captured: list[list[str]] = []

    def _run(args, **kwargs):
        captured.append(args)
        payload = {"number": 77, "state": "OPEN", "url": "https://example/pr/77", "mergedAt": None}
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    monkeypatch.setattr("harness.core.post_ship.subprocess.run", _run)
    result = manager.check_pr_state(pr_number=77, branch="agent/task-006-any")
    assert result.code == "PR_NOT_MERGED"
    assert captured
    assert captured[0][:4] == ["gh", "pr", "view", "77"]
    assert "--head" not in captured[0]


def test_check_pr_state_parse_failure(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.post_ship.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "{bad json", ""),
    )
    result = manager.check_pr_state(pr_number=64, branch=None)
    assert result.ok is False
    assert result.code == "PR_LOOKUP_PARSE_FAILED"


def test_finalize_after_merge_happy_path(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.post_ship.PostShipManager.check_pr_state",
        lambda self, **kwargs: GitOperationResult(
            ok=True,
            code="PR_MERGED",
            message="merged",
            context={"pr": "64", "url": "https://example/pr/64"},
        ),
    )
    monkeypatch.setattr(
        "harness.core.post_ship.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK", message="clean"),
    )
    monkeypatch.setattr(
        "harness.core.post_ship.current_branch",
        lambda _cwd: "main",
    )
    monkeypatch.setattr(
        "harness.core.post_ship.PostShipManager._resolve_task_branch",
        lambda self, **kwargs: "agent/task-006-post-ship-cleanup",
    )

    calls: list[list[str]] = []

    def _run_git(args, *_args, **_kwargs):
        calls.append(args)
        return GitOperationResult(ok=True, code="OK", message="ok")

    monkeypatch.setattr("harness.core.post_ship.run_git_result", _run_git)
    result = manager.finalize_after_merge(task_key="task-006", pr_number=64)

    assert result.ok is True
    assert result.code == "POST_SHIP_DONE"
    assert calls == [
        ["checkout", "main"],
        ["pull", "--ff-only", "origin", "main"],
        ["branch", "-d", "agent/task-006-post-ship-cleanup"],
    ]


def test_finalize_after_merge_rejects_protected_branch(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.post_ship.PostShipManager.check_pr_state",
        lambda self, **kwargs: GitOperationResult(ok=True, code="PR_MERGED", message="merged"),
    )
    monkeypatch.setattr(
        "harness.core.post_ship.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK", message="clean"),
    )
    monkeypatch.setattr(
        "harness.core.post_ship.PostShipManager._resolve_task_branch",
        lambda self, **kwargs: "main",
    )
    result = manager.finalize_after_merge(task_key="task-006", pr_number=64)
    assert result.ok is False
    assert result.code == "PROTECTED_BRANCH"


def test_finalize_after_merge_rejects_ambiguous_branch_resolution(tmp_path: Path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        "harness.core.post_ship.PostShipManager.check_pr_state",
        lambda self, **kwargs: GitOperationResult(ok=True, code="PR_MERGED", message="merged"),
    )
    monkeypatch.setattr(
        "harness.core.post_ship.ensure_clean_result",
        lambda _cwd: GitOperationResult(ok=True, code="OK", message="clean"),
    )
    monkeypatch.setattr(
        "harness.core.post_ship.current_branch",
        lambda _cwd: "main",
    )
    monkeypatch.setattr(
        "harness.core.post_ship.run_git_result",
        lambda args, *_a, **_k: GitOperationResult(
            ok=True,
            code="OK",
            stdout="  agent/task-006-a\n  agent/task-006-b\n" if args[:2] == ["branch", "--list"] else "",
        ),
    )
    result = manager.finalize_after_merge(task_key="task-006", pr_number=64)
    assert result.ok is False
    assert result.code == "TASK_BRANCH_RESOLUTION_FAILED"
