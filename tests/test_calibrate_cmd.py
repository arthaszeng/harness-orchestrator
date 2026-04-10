"""Tests for harness calibrate CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.review_calibration import (
    ReviewActualOutcome,
    ReviewOutcome,
    ReviewPrediction,
    save_review_outcome,
)

runner = CliRunner()


def _make_outcome(
    task_id: str,
    aggregate: float = 8.0,
    verdict: str = "PASS",
    ci_passed: bool | None = True,
) -> ReviewOutcome:
    return ReviewOutcome(
        task_id=task_id,
        prediction=ReviewPrediction(
            eval_aggregate=aggregate,
            verdict=verdict,
            finding_count=1,
        ),
        outcome=ReviewActualOutcome(
            ci_passed=ci_passed,
            recorded_at="2026-04-10T12:00:00+00:00",
        ),
    )


_CONFIG_TOML = (
    '[project]\nname = "test"\n[ci]\ncommand = "true"\n'
    '[models]\ndefault = ""\n[workflow]\nmax_iterations = 3\n'
    'pass_threshold = 7.0\nauto_merge = true\nbranch_prefix = "agent"\n'
    'trunk_branch = "main"\n[native]\nevaluator_model = ""\n'
    'adversarial_mechanism = "auto"\nreview_gate = "eng"\n'
    'gate_full_review_min = 5\ngate_summary_confirm_min = 3\n'
    '[integrations.memverse]\nenabled = false\ndomain_prefix = "test"\n'
)


def _setup_project(base: Path) -> None:
    cfg_dir = base / ".harness-flow"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.toml").write_text(_CONFIG_TOML)
    (cfg_dir / "tasks").mkdir(exist_ok=True)


def _populate_outcomes(base: Path, count: int, *, ci_passed: bool = True) -> None:
    agents_dir = base / ".harness-flow"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        tid = f"task-{i + 1:03d}"
        task_dir = agents_dir / "tasks" / tid
        task_dir.mkdir(parents=True, exist_ok=True)
        save_review_outcome(task_dir, _make_outcome(tid, aggregate=7.0 + i * 0.3, ci_passed=ci_passed))


class TestCalibrateEmpty:
    def test_no_data_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["calibrate"])
        assert result.exit_code == 0
        assert "No review outcomes found" in result.output

    def test_no_data_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["calibrate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "no_data"


class TestCalibrateWithData:
    def test_below_threshold_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _setup_project(tmp_path)
        _populate_outcomes(tmp_path, 3)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["calibrate"])
        assert result.exit_code == 0
        assert "Insufficient data" in result.output

    def test_sufficient_data_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _setup_project(tmp_path)
        _populate_outcomes(tmp_path, 6)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["calibrate"])
        assert result.exit_code == 0
        assert "REVIEW CALIBRATION REPORT" in result.output
        assert "Prediction accuracy" in result.output

    def test_sufficient_data_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _setup_project(tmp_path)
        _populate_outcomes(tmp_path, 6)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["calibrate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "report" in data
        assert "outcomes" in data
        assert data["report"]["has_sufficient_data"] is True


class TestCalibrateSingleTask:
    def test_single_task_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _setup_project(tmp_path)
        _populate_outcomes(tmp_path, 1)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["calibrate", "--task", "task-001"])
        assert result.exit_code == 0
        assert "task-001" in result.output

    def test_single_task_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["calibrate", "--task", "task-999"])
        assert result.exit_code == 1
