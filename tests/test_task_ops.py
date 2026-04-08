"""Unit tests for harness.core.task_ops (mark_task_done / archive_task)."""

from __future__ import annotations

import json
from pathlib import Path

from harness.core.task_ops import archive_task, mark_task_done


def _make_agents_dir(tmp_path: Path) -> Path:
    agents = tmp_path / ".harness-flow"
    agents.mkdir()
    (agents / "tasks").mkdir()
    (agents / "archive").mkdir()
    return agents


def _write_workflow_state(task_dir: Path, phase: str = "done") -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    ws = {
        "schema_version": 1,
        "task_id": task_dir.name,
        "phase": phase,
        "iteration": 0,
    }
    (task_dir / "workflow-state.json").write_text(json.dumps(ws), encoding="utf-8")


# ── mark_task_done ──────────────────────────────────────────────


class TestMarkTaskDone:
    def test_success(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="shipping")

        result = mark_task_done(agents, "task-001")
        assert result.ok
        assert result.code == "MARKED_DONE"

        ws = json.loads((td / "workflow-state.json").read_text())
        assert ws["phase"] == "done"

    def test_already_done(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="done")

        result = mark_task_done(agents, "task-001")
        assert result.ok
        assert result.code == "ALREADY_DONE"

    def test_task_dir_not_found(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        result = mark_task_done(agents, "task-999")
        assert not result.ok
        assert result.code == "TASK_DIR_NOT_FOUND"

    def test_invalid_task_key(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        result = mark_task_done(agents, "../escape")
        assert not result.ok
        assert result.code == "INVALID_TASK_KEY"

    def test_state_transition_failed(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="shipping")

        with patch("harness.core.task_ops.sync_task_state", side_effect=ValueError("bad transition")):
            result = mark_task_done(agents, "task-001")
        assert not result.ok
        assert result.code == "STATE_TRANSITION_FAILED"


# ── archive_task ────────────────────────────────────────────────


class TestArchiveTask:
    def test_success(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="done")
        (td / "plan.md").write_text("# plan", encoding="utf-8")

        result = archive_task(agents, "task-001")
        assert result.ok
        assert result.code == "ARCHIVED"
        assert not td.exists()
        assert (agents / "archive" / "task-001" / "plan.md").exists()

    def test_not_done_without_force(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="shipping")

        result = archive_task(agents, "task-001")
        assert not result.ok
        assert result.code == "NOT_DONE"

    def test_force_skips_phase_check(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="shipping")

        result = archive_task(agents, "task-001", force=True)
        assert result.ok
        assert result.code == "ARCHIVED"

    def test_task_dir_not_found(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        result = archive_task(agents, "task-999")
        assert not result.ok
        assert result.code == "TASK_DIR_NOT_FOUND"

    def test_archive_target_exists(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="done")
        (agents / "archive" / "task-001").mkdir(parents=True)

        result = archive_task(agents, "task-001")
        assert not result.ok
        assert result.code == "ARCHIVE_TARGET_EXISTS"

    def test_no_workflow_state(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        td.mkdir()

        result = archive_task(agents, "task-001")
        assert not result.ok
        assert result.code == "NO_WORKFLOW_STATE"

    def test_no_workflow_state_with_force(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        td.mkdir()

        result = archive_task(agents, "task-001", force=True)
        assert result.ok
        assert result.code == "ARCHIVED"

    def test_invalid_task_key(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        result = archive_task(agents, "../escape")
        assert not result.ok
        assert result.code == "INVALID_TASK_KEY"

    def test_corrupt_workflow_state(self, tmp_path: Path) -> None:
        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        td.mkdir(parents=True)
        (td / "workflow-state.json").write_text("NOT JSON", encoding="utf-8")

        result = archive_task(agents, "task-001")
        assert not result.ok
        assert result.code == "NO_WORKFLOW_STATE"

    def test_archive_move_failed(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        agents = _make_agents_dir(tmp_path)
        td = agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="done")

        with patch("harness.core.task_ops.shutil.move", side_effect=OSError("disk full")):
            result = archive_task(agents, "task-001")
        assert not result.ok
        assert result.code == "ARCHIVE_MOVE_FAILED"

    def test_symlink_agents_dir(self, tmp_path: Path) -> None:
        """archive_task works when agents_dir is a symlink (worktree scenario)."""
        real_agents = tmp_path / "real" / ".harness-flow"
        real_agents.mkdir(parents=True)
        (real_agents / "tasks").mkdir()
        (real_agents / "archive").mkdir()
        td = real_agents / "tasks" / "task-001"
        _write_workflow_state(td, phase="done")

        link = tmp_path / "worktree" / ".harness-flow"
        link.parent.mkdir()
        link.symlink_to(real_agents)

        result = archive_task(link, "task-001")
        assert result.ok
        assert result.code == "ARCHIVED"
        assert (real_agents / "archive" / "task-001").exists()
