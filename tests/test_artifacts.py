"""Tests for programmatic artifact writers (core/artifacts.py + CLI commands)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from harness.cli import app
from harness.core.artifacts import (
    next_build_round,
    next_eval_round,
    save_build_log,
    save_evaluation,
    save_ship_metrics,
)
from harness.core.workflow_state import load_workflow_state

runner = CliRunner()


class TestNextRound:
    def test_empty_dir(self, tmp_path: Path):
        assert next_eval_round(tmp_path) == 1
        assert next_build_round(tmp_path) == 1

    def test_single_round(self, tmp_path: Path):
        (tmp_path / "evaluation-r1.md").write_text("x")
        (tmp_path / "build-r1.log").write_text("x")
        assert next_eval_round(tmp_path) == 2
        assert next_build_round(tmp_path) == 2

    def test_multiple_rounds(self, tmp_path: Path):
        for i in (1, 2, 3):
            (tmp_path / f"evaluation-r{i}.md").write_text("x")
        assert next_eval_round(tmp_path) == 4

    def test_nonexistent_dir(self, tmp_path: Path):
        missing = tmp_path / "nope"
        assert next_eval_round(missing) == 1

    def test_ignores_unrelated_files(self, tmp_path: Path):
        (tmp_path / "evaluation-summary.md").write_text("x")
        (tmp_path / "build-notes.txt").write_text("x")
        assert next_eval_round(tmp_path) == 1
        assert next_build_round(tmp_path) == 1


class TestSaveEvaluation:
    def test_creates_file(self, tmp_path: Path):
        path = save_evaluation(tmp_path, verdict="PASS")
        assert path.exists()
        assert path.name == "evaluation-r1.md"

    def test_auto_increments(self, tmp_path: Path):
        save_evaluation(tmp_path, round_num=1, verdict="ITERATE")
        path = save_evaluation(tmp_path, verdict="PASS")
        assert path.name == "evaluation-r2.md"

    def test_verdict_line(self, tmp_path: Path):
        path = save_evaluation(tmp_path, verdict="PASS")
        text = path.read_text()
        assert "## Verdict: PASS" in text

    def test_scores_in_table(self, tmp_path: Path):
        scores = {
            "Design": {"role": "architect", "score": 8},
            "Quality": {"role": "engineer", "score": 9},
        }
        path = save_evaluation(tmp_path, scores=scores, verdict="PASS")
        text = path.read_text()
        assert "architect" in text
        assert "8/10" in text
        assert "9/10" in text
        assert "8.5/10" in text  # average

    def test_findings_listed(self, tmp_path: Path):
        path = save_evaluation(
            tmp_path,
            findings=["SQL injection in views.py", "Unused import"],
            verdict="ITERATE",
        )
        text = path.read_text()
        assert "SQL injection" in text
        assert "Unused import" in text

    def test_creates_parent_dirs(self, tmp_path: Path):
        deep = tmp_path / "a" / "b" / "c"
        path = save_evaluation(deep, verdict="PASS")
        assert path.exists()

    def test_explicit_round(self, tmp_path: Path):
        path = save_evaluation(tmp_path, round_num=5, verdict="PASS")
        assert path.name == "evaluation-r5.md"


class TestSaveBuildLog:
    def test_creates_file(self, tmp_path: Path):
        path = save_build_log(tmp_path, "build output here")
        assert path.exists()
        assert path.name == "build-r1.log"
        assert path.read_text() == "build output here"

    def test_auto_increments(self, tmp_path: Path):
        save_build_log(tmp_path, "round 1", round_num=1)
        path = save_build_log(tmp_path, "round 2")
        assert path.name == "build-r2.log"
        assert path.read_text() == "round 2"

    def test_creates_parent_dirs(self, tmp_path: Path):
        deep = tmp_path / "x" / "y"
        path = save_build_log(deep, "log content")
        assert path.exists()


class TestSaveShipMetrics:
    def test_creates_file(self, tmp_path: Path):
        path = save_ship_metrics(
            tmp_path,
            branch="agent/feat-123",
            test_count=42,
            pr_quality_score=8.5,
        )
        assert path.exists()
        assert path.name == "ship-metrics.json"

    def test_valid_json(self, tmp_path: Path):
        path = save_ship_metrics(tmp_path, branch="main")
        data = json.loads(path.read_text())
        assert data["branch"] == "main"
        assert "timestamp" in data
        assert isinstance(data["models_used"], list)

    def test_all_fields_present(self, tmp_path: Path):
        path = save_ship_metrics(
            tmp_path,
            branch="agent/feat",
            pr_quality_score=9.0,
            test_count=100,
            eval_rounds=2,
            findings_critical=1,
            findings_informational=3,
            auto_fixed=2,
            plan_total=5,
            plan_done=4,
            coverage_pct=85,
        )
        data = json.loads(path.read_text())
        assert data["coverage_pct"] == 85
        assert data["plan_total"] == 5
        assert data["plan_done"] == 4
        assert data["eval_rounds"] == 2

    def test_updates_workflow_state_ref(self, tmp_path: Path):
        task_dir = tmp_path / ".agents" / "tasks" / "task-009"
        task_dir.mkdir(parents=True)
        (task_dir / "workflow-state.json").write_text(
            '{"schema_version": 1, "task_id": "task-009", "phase": "idle"}',
            encoding="utf-8",
        )

        save_ship_metrics(task_dir, branch="agent/task-009")
        state = load_workflow_state(task_dir)
        assert state is not None
        assert state.artifacts.ship_metrics == ".agents/tasks/task-009/ship-metrics.json"


class TestSaveEvaluationRawBody:
    def test_raw_body_written_verbatim(self, tmp_path: Path):
        body = "# Custom Eval\n\nCustom content here.\n\n## Verdict: PASS\n"
        path = save_evaluation(tmp_path, raw_body=body, verdict="PASS")
        assert path.read_text() == body

    def test_raw_body_auto_increments(self, tmp_path: Path):
        save_evaluation(tmp_path, round_num=1, verdict="ITERATE")
        path = save_evaluation(tmp_path, raw_body="round 2 content", verdict="PASS")
        assert path.name == "evaluation-r2.md"


class TestCLIPathTraversal:
    def test_rejects_dotdot(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["save-eval", "--task", "..", "--verdict", "PASS"])
        assert result.exit_code != 0

    def test_rejects_arbitrary_name(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["save-eval", "--task", "evil-name", "--verdict", "PASS"])
        assert result.exit_code != 0

    def test_accepts_valid_task_id(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["save-eval", "--task", "task-042", "--verdict", "PASS"])
        assert result.exit_code == 0


class TestCLISaveEval:
    def test_save_eval_with_body(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agents" / "tasks" / "task-001").mkdir(parents=True)

        result = runner.invoke(
            app,
            [
                "save-eval",
                "--task", "task-001",
                "--verdict", "PASS",
                "--score", "8.0",
                "--body", "# Eval\n\n## Verdict: PASS\n",
            ],
        )
        assert result.exit_code == 0
        eval_file = tmp_path / ".agents" / "tasks" / "task-001" / "evaluation-r1.md"
        assert eval_file.exists()
        assert "PASS" in eval_file.read_text()

    def test_save_eval_without_body_generates_template(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agents" / "tasks" / "task-002").mkdir(parents=True)

        result = runner.invoke(
            app,
            [
                "save-eval",
                "--task", "task-002",
                "--verdict", "ITERATE",
                "--score", "5.5",
            ],
        )
        assert result.exit_code == 0
        eval_file = tmp_path / ".agents" / "tasks" / "task-002" / "evaluation-r1.md"
        assert eval_file.exists()
        text = eval_file.read_text()
        assert "## Verdict: ITERATE" in text
        assert "5.5/10" in text

    def test_save_eval_updates_workflow_state_when_present(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".agents" / "tasks" / "task-003"
        task_dir.mkdir(parents=True)
        (task_dir / "workflow-state.json").write_text(
            '{"schema_version": 1, "task_id": "task-003", "phase": "idle"}',
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "save-eval",
                "--task", "task-003",
                "--verdict", "PASS",
                "--score", "8.0",
                "--body", "# Eval\n\n## Verdict: PASS\n",
            ],
        )

        assert result.exit_code == 0
        state = load_workflow_state(task_dir)
        assert state is not None
        assert state.artifacts.evaluation == ".agents/tasks/task-003/evaluation-r1.md"
        assert state.phase.value == "evaluating"
        assert state.gates.evaluation.status.value == "pass"

    def test_save_eval_iterate_sets_pending_gate(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".agents" / "tasks" / "task-013"
        task_dir.mkdir(parents=True)
        (task_dir / "workflow-state.json").write_text(
            '{"schema_version": 1, "task_id": "task-013", "phase": "idle"}',
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            ["save-eval", "--task", "task-013", "--verdict", "ITERATE", "--score", "6.0"],
        )
        assert result.exit_code == 0
        state = load_workflow_state(task_dir)
        assert state is not None
        assert state.gates.evaluation.status.value == "pending"

    def test_save_eval_failure_in_state_sync_keeps_artifact_and_recovers(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".agents" / "tasks" / "task-014"
        task_dir.mkdir(parents=True)
        (task_dir / "workflow-state.json").write_text(
            '{"schema_version": 1, "task_id": "task-014", "phase": "idle", '
            '"artifacts": {"evaluation": ".agents/tasks/task-014/evaluation-r0.md"}}',
            encoding="utf-8",
        )

        import harness.core.workflow_state as ws
        original_sync = ws.sync_task_state

        def fail_sync(*args, **kwargs):
            raise OSError("sync failed")

        monkeypatch.setattr(ws, "sync_task_state", fail_sync)
        failed = runner.invoke(
            app,
            ["save-eval", "--task", "task-014", "--verdict", "PASS", "--body", "# Eval\n\n## Verdict: PASS\n"],
        )
        assert failed.exit_code != 0
        assert (task_dir / "evaluation-r1.md").exists()
        state_after_fail = load_workflow_state(task_dir)
        assert state_after_fail is not None
        assert state_after_fail.artifacts.evaluation == ".agents/tasks/task-014/evaluation-r0.md"

        monkeypatch.setattr(ws, "sync_task_state", original_sync)
        recovered = runner.invoke(
            app,
            ["save-eval", "--task", "task-014", "--verdict", "PASS", "--body", "# Eval\n\n## Verdict: PASS\n"],
        )
        assert recovered.exit_code == 0
        state_after_recover = load_workflow_state(task_dir)
        assert state_after_recover is not None
        assert state_after_recover.artifacts.evaluation == ".agents/tasks/task-014/evaluation-r2.md"


class TestCLISaveBuildLog:
    def test_save_build_log_with_body(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".agents" / "tasks" / "task-001").mkdir(parents=True)

        result = runner.invoke(
            app,
            [
                "save-build-log",
                "--task", "task-001",
                "--body", "# Build Log\n\nAll deliverables complete.\n",
            ],
        )
        assert result.exit_code == 0
        log_file = tmp_path / ".agents" / "tasks" / "task-001" / "build-r1.log"
        assert log_file.exists()
        assert "deliverables" in log_file.read_text()

    def test_save_build_log_updates_workflow_state_when_present(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".agents" / "tasks" / "task-004"
        task_dir.mkdir(parents=True)
        (task_dir / "workflow-state.json").write_text(
            '{"schema_version": 1, "task_id": "task-004", "phase": "idle"}',
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "save-build-log",
                "--task", "task-004",
                "--body", "# Build Log\n\nWave 1 done.\n",
            ],
        )

        assert result.exit_code == 0
        state = load_workflow_state(task_dir)
        assert state is not None
        assert state.artifacts.build_log == ".agents/tasks/task-004/build-r1.log"
        assert state.phase.value == "building"

    def test_save_build_log_failure_in_state_sync_keeps_artifact_and_recovers(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".agents" / "tasks" / "task-015"
        task_dir.mkdir(parents=True)
        (task_dir / "workflow-state.json").write_text(
            '{"schema_version": 1, "task_id": "task-015", "phase": "idle", '
            '"artifacts": {"build_log": ".agents/tasks/task-015/build-r0.log"}}',
            encoding="utf-8",
        )

        import harness.core.workflow_state as ws
        original_sync = ws.sync_task_state

        def fail_sync(*args, **kwargs):
            raise OSError("sync failed")

        monkeypatch.setattr(ws, "sync_task_state", fail_sync)
        failed = runner.invoke(
            app,
            ["save-build-log", "--task", "task-015", "--body", "first"],
        )
        assert failed.exit_code != 0
        assert (task_dir / "build-r1.log").exists()
        state_after_fail = load_workflow_state(task_dir)
        assert state_after_fail is not None
        assert state_after_fail.artifacts.build_log == ".agents/tasks/task-015/build-r0.log"

        monkeypatch.setattr(ws, "sync_task_state", original_sync)
        recovered = runner.invoke(
            app,
            ["save-build-log", "--task", "task-015", "--body", "second"],
        )
        assert recovered.exit_code == 0
        state_after_recover = load_workflow_state(task_dir)
        assert state_after_recover is not None
        assert state_after_recover.artifacts.build_log == ".agents/tasks/task-015/build-r2.log"
