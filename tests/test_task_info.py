"""Tests for harness task next-id and harness task resolve commands."""

from __future__ import annotations

import json

from harness.commands.task_info import run_task_next_id, run_task_resolve
from harness.core.workflow_state import WORKFLOW_STATE_FILENAME

import pytest
import typer


class TestTaskNextId:
    def test_empty_tasks_dir(self, tmp_path, monkeypatch, capture_echo):
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        run_task_next_id(as_json=True)
        data = json.loads(capture_echo[0])
        assert data["next_id"] == "task-001"
        assert data["max_existing"] == 0

    def test_with_existing_tasks(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "task-001").mkdir()
        (tasks / "task-005").mkdir()
        (tasks / "task-010").mkdir()
        monkeypatch.chdir(tmp_path)
        run_task_next_id(as_json=True)
        data = json.loads(capture_echo[0])
        assert data["next_id"] == "task-011"
        assert data["max_existing"] == 10

    def test_plain_text_output(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "task-003").mkdir()
        monkeypatch.chdir(tmp_path)
        run_task_next_id(as_json=False)
        assert capture_echo[0].strip() == "task-004"

    def test_no_harness_flow_dir(self, tmp_path, monkeypatch, capture_echo):
        monkeypatch.chdir(tmp_path)
        run_task_next_id(as_json=True)
        data = json.loads(capture_echo[0])
        assert data["next_id"] == "task-001"
        assert data["total_task_dirs"] == 0


class TestTaskResolve:
    def test_resolves_latest_task(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        (tasks / "task-001").mkdir(parents=True)
        (tasks / "task-002").mkdir()
        (tasks / "task-002" / "plan.md").write_text("test plan")
        ws = {
            "schema_version": 1,
            "task_id": "task-002",
            "phase": "building",
            "handoff_summary": "some summary",
        }
        (tasks / "task-002" / WORKFLOW_STATE_FILENAME).write_text(json.dumps(ws))
        monkeypatch.chdir(tmp_path)
        run_task_resolve(as_json=True)
        data = json.loads(capture_echo[0])
        assert data["task_id"] == "task-002"
        assert data["phase"] == "building"
        assert data["has_plan"] is True
        assert data["has_handoff_summary"] is True
        assert data["resolution_source"] == "latest_numeric"

    def test_no_task_exits_1(self, tmp_path, monkeypatch, capture_echo):
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_task_resolve(as_json=True)
        assert exc_info.value.exit_code == 1

    def test_explicit_task(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        (tasks / "task-001").mkdir(parents=True)
        (tasks / "task-002").mkdir()
        monkeypatch.chdir(tmp_path)
        run_task_resolve(task="task-001", as_json=True)
        data = json.loads(capture_echo[0])
        assert data["task_id"] == "task-001"
        assert data["resolution_source"] == "explicit"

    def test_env_variable_resolution(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        (tasks / "task-001").mkdir(parents=True)
        (tasks / "task-002").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HARNESS_TASK_ID", "task-001")
        run_task_resolve(as_json=True)
        data = json.loads(capture_echo[0])
        assert data["task_id"] == "task-001"
        assert data["resolution_source"] == "env"

    def test_phase_unknown_when_no_workflow_state(self, tmp_path, monkeypatch, capture_echo):
        tasks = tmp_path / ".harness-flow" / "tasks"
        (tasks / "task-001").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        run_task_resolve(as_json=True)
        data = json.loads(capture_echo[0])
        assert data["phase"] == "unknown"
        assert data["has_plan"] is False
        assert data["has_handoff_summary"] is False

    def test_env_fallback_to_latest(self, tmp_path, monkeypatch, capture_echo):
        """When HARNESS_TASK_ID points to nonexistent dir, resolution_source should be latest_numeric."""
        tasks = tmp_path / ".harness-flow" / "tasks"
        (tasks / "task-001").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HARNESS_TASK_ID", "task-999")
        run_task_resolve(as_json=True)
        data = json.loads(capture_echo[0])
        assert data["task_id"] == "task-001"
        assert data["resolution_source"] == "latest_numeric"
