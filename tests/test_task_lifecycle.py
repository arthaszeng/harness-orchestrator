"""Tests for harness task list / archive / done lifecycle commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from harness.commands.task_lifecycle import (
    iter_archive_dirs,
    run_task_archive,
    run_task_done,
    run_task_list,
)
from harness.core.workflow_state import WORKFLOW_STATE_FILENAME


def _write_ws(task_dir: Path, phase: str = "done", task_id: str | None = None) -> None:
    """Helper: write a minimal workflow-state.json."""
    tid = task_id or task_dir.name
    ws = {
        "schema_version": 1,
        "task_id": tid,
        "phase": phase,
    }
    (task_dir / WORKFLOW_STATE_FILENAME).write_text(json.dumps(ws), encoding="utf-8")


# ────────────────────────────────────────────────────────────
# task list
# ────────────────────────────────────────────────────────────


class TestTaskList:
    def test_empty_tasks_dir(self, tmp_path, monkeypatch, capture_echo):
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        run_task_list(as_json=True)
        assert capture_echo[0] == "[]"

    def test_lists_active_tasks(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="building")
        (t1 / "plan.md").write_text("plan")

        t2 = tasks / "task-002"
        t2.mkdir()
        _write_ws(t2, phase="done")

        monkeypatch.chdir(tmp_path)
        run_task_list(as_json=True)
        data = json.loads(capture_echo[0])
        assert len(data) == 2
        assert data[0]["task_id"] == "task-001"
        assert data[0]["phase"] == "building"
        assert data[0]["source"] == "tasks"
        assert data[1]["task_id"] == "task-002"
        assert data[1]["phase"] == "done"

    def test_phase_filter(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="building")

        t2 = tasks / "task-002"
        t2.mkdir()
        _write_ws(t2, phase="done")

        monkeypatch.chdir(tmp_path)
        run_task_list(phase_filter="done", as_json=True)
        data = json.loads(capture_echo[0])
        assert len(data) == 1
        assert data[0]["task_id"] == "task-002"

    def test_include_archived(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-002"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="building")

        archive = tmp_path / ".harness-flow" / "archive"
        a1 = archive / "task-001"
        a1.mkdir(parents=True)
        _write_ws(a1, phase="done")

        monkeypatch.chdir(tmp_path)
        run_task_list(include_archived=True, as_json=True)
        data = json.loads(capture_echo[0])
        assert len(data) == 2
        sources = {e["task_id"]: e["source"] for e in data}
        assert sources["task-002"] == "tasks"
        assert sources["task-001"] == "archive"

    def test_missing_workflow_state_shows_unknown(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        (tasks / "task-001").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        run_task_list(as_json=True)
        data = json.loads(capture_echo[0])
        assert data[0]["phase"] == "unknown"

    def test_artifact_count(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="done")
        (t1 / "plan.md").write_text("plan")
        (t1 / "build-r1.md").write_text("log")

        monkeypatch.chdir(tmp_path)
        run_task_list(as_json=True)
        data = json.loads(capture_echo[0])
        assert data[0]["artifact_count"] == 3  # ws + plan + build

    def test_rich_table_output_no_error(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="done")
        monkeypatch.chdir(tmp_path)
        run_task_list(as_json=False)


# ────────────────────────────────────────────────────────────
# task archive
# ────────────────────────────────────────────────────────────


class TestTaskArchive:
    def test_archive_done_task(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="done")
        (t1 / "plan.md").write_text("plan")

        monkeypatch.chdir(tmp_path)
        run_task_archive(task="task-001")

        assert not (tasks / "task-001").exists()
        assert (tmp_path / ".harness-flow" / "archive" / "task-001").is_dir()
        assert (tmp_path / ".harness-flow" / "archive" / "task-001" / "plan.md").exists()

    def test_reject_non_done(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="building")

        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_task_archive(task="task-001")
        assert exc_info.value.exit_code == 1

    def test_force_skips_phase_check(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="building")
        (t1 / "plan.md").write_text("plan")

        monkeypatch.chdir(tmp_path)
        run_task_archive(task="task-001", force=True)
        assert (tmp_path / ".harness-flow" / "archive" / "task-001").is_dir()

    def test_target_already_exists(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="done")

        archive = tmp_path / ".harness-flow" / "archive" / "task-001"
        archive.mkdir(parents=True)

        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_task_archive(task="task-001")
        assert exc_info.value.exit_code == 1

    def test_nonexistent_task(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_task_archive(task="task-999")
        assert exc_info.value.exit_code == 1

    def test_invalid_task_id(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_task_archive(task="../escape")
        assert exc_info.value.exit_code == 1

    def test_missing_plan_md_warns(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="done")

        monkeypatch.chdir(tmp_path)
        run_task_archive(task="task-001")
        assert (tmp_path / ".harness-flow" / "archive" / "task-001").is_dir()

    def test_no_workflow_state_without_force(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        (tasks / "task-001").mkdir(parents=True)

        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_task_archive(task="task-001")
        assert exc_info.value.exit_code == 1


# ────────────────────────────────────────────────────────────
# task done
# ────────────────────────────────────────────────────────────


class TestTaskDone:
    def test_mark_done(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="evaluating")

        monkeypatch.chdir(tmp_path)
        run_task_done(task="task-001")

        ws_data = json.loads((t1 / WORKFLOW_STATE_FILENAME).read_text())
        assert ws_data["phase"] == "done"

    def test_already_done_idempotent(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        _write_ws(t1, phase="done")

        monkeypatch.chdir(tmp_path)
        run_task_done(task="task-001")  # should not raise

    def test_clears_blocker(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        t1 = tasks / "task-001"
        t1.mkdir(parents=True)
        ws = {
            "schema_version": 1,
            "task_id": "task-001",
            "phase": "blocked",
            "blocker": {"kind": "ci_failure", "reason": "tests fail"},
        }
        (t1 / WORKFLOW_STATE_FILENAME).write_text(json.dumps(ws), encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        run_task_done(task="task-001")

        ws_data = json.loads((t1 / WORKFLOW_STATE_FILENAME).read_text())
        assert ws_data["phase"] == "done"
        assert ws_data["blocker"]["kind"] == ""
        assert ws_data["blocker"]["reason"] == ""

    def test_nonexistent_task(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_task_done(task="task-999")
        assert exc_info.value.exit_code == 1

    def test_invalid_task_id(self, tmp_path, monkeypatch):
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_task_done(task="../escape")
        assert exc_info.value.exit_code == 1

    def test_no_workflow_state_creates_one(self, tmp_path, monkeypatch):
        tasks = tmp_path / ".harness-flow" / "tasks"
        (tasks / "task-001").mkdir(parents=True)

        monkeypatch.chdir(tmp_path)
        run_task_done(task="task-001")

        ws_data = json.loads((tasks / "task-001" / WORKFLOW_STATE_FILENAME).read_text())
        assert ws_data["phase"] == "done"


# ────────────────────────────────────────────────────────────
# iter_archive_dirs
# ────────────────────────────────────────────────────────────


class TestIterArchiveDirs:
    def test_empty(self, tmp_path):
        agents = tmp_path / ".harness-flow"
        agents.mkdir()
        assert iter_archive_dirs(agents) == []

    def test_returns_valid_dirs(self, tmp_path):
        agents = tmp_path / ".harness-flow"
        archive = agents / "archive"
        (archive / "task-001").mkdir(parents=True)
        (archive / "task-003").mkdir()
        (archive / ".hidden").mkdir()
        result = iter_archive_dirs(agents)
        names = [p.name for p in result]
        assert names == ["task-001", "task-003"]

    def test_sorted_numerically(self, tmp_path):
        agents = tmp_path / ".harness-flow"
        archive = agents / "archive"
        (archive / "task-010").mkdir(parents=True)
        (archive / "task-002").mkdir()
        (archive / "task-001").mkdir()
        result = iter_archive_dirs(agents)
        names = [p.name for p in result]
        assert names == ["task-001", "task-002", "task-010"]
