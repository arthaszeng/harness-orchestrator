"""Tests for task identity resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.task_identity import (
    TaskIdentityResolver,
    extract_task_id_from_branch,
    extract_task_key_from_branch,
)


def test_hybrid_strategy_accepts_numeric_and_jira():
    resolver = TaskIdentityResolver(strategy="hybrid")
    assert resolver.is_valid_task_key("task-001")
    assert resolver.is_valid_task_key("PROJ-123")
    assert not resolver.is_valid_task_key("feature-foo")


def test_custom_strategy_validates_pattern():
    resolver = TaskIdentityResolver(strategy="custom", custom_pattern=r"[a-z]{3}-\d+")
    assert resolver.is_valid_task_key("abc-42")
    assert not resolver.is_valid_task_key("ABC-42")


def test_custom_strategy_rejects_unsafe_pattern():
    with pytest.raises(ValueError):
        TaskIdentityResolver(strategy="custom", custom_pattern=r"(?=abc)abc").fullmatch_re


@pytest.mark.parametrize(
    "branch,expected",
    [
        ("agent/task-010-feature", "task-010"),
        ("agent/PROJ-1234-git-governance", "PROJ-1234"),
        ("main", None),
        ("feature/task-010", None),
    ],
)
def test_extract_from_branch_hybrid(branch: str, expected: str | None):
    resolver = TaskIdentityResolver(strategy="hybrid")
    assert resolver.extract_from_branch(branch) == expected


class TestExtractTaskIdFromBranch:
    """Migrated from test_worktree.py after worktree module removal."""

    @pytest.mark.parametrize("branch,expected", [
        ("agent/task-001-feature", "task-001"),
        ("agent/task-42-short", "task-42"),
        ("agent/task-999-long-name-here", "task-999"),
        ("agent/PROJ-123-improve-git", "PROJ-123"),
        ("main", None),
        ("feature/something", None),
        ("agent/no-task-here", None),
        ("", None),
    ])
    def test_patterns(self, branch: str, expected: str | None):
        assert extract_task_id_from_branch(branch) == expected

    def test_uses_configured_branch_prefix(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir(parents=True)
        (agents_dir / "config.toml").write_text(
            "[workflow]\nbranch_prefix = 'feat'\n",
            encoding="utf-8",
        )
        assert extract_task_key_from_branch("feat/task-123-scope", cwd=tmp_path) == "task-123"

