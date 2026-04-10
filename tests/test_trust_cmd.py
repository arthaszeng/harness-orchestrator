"""Tests for harness trust CLI command."""

from __future__ import annotations

import json

from harness.commands.trust_cmd import run_trust


def test_trust_no_data(tmp_path, monkeypatch, capsys):
    """No outcomes → LOW with reason."""
    harness_dir = tmp_path / ".harness-flow" / "tasks"
    harness_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    run_trust(as_json=True)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["level"] == "LOW"
    assert "insufficient" in data["reason"]


def test_trust_no_data_rich(tmp_path, monkeypatch, capsys):
    """No outcomes → Rich output mentions LOW."""
    harness_dir = tmp_path / ".harness-flow" / "tasks"
    harness_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    run_trust(as_json=False)
    out = capsys.readouterr().out
    assert "LOW" in out


def test_trust_with_data_json(tmp_path, monkeypatch, capsys):
    """Sufficient data → JSON profile with fields."""
    _create_outcomes(tmp_path, count=12, ci_passed=True)
    monkeypatch.chdir(tmp_path)

    run_trust(as_json=True)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "level" in data
    assert "escalation_adjustment" in data
    assert "threshold_adjustment" in data
    assert "prediction_accuracy" in data
    assert "paired_samples" in data
    assert "calibration" in data


def test_trust_with_data_rich(tmp_path, monkeypatch, capsys):
    """Sufficient data → Rich output contains TRUST PROFILE."""
    _create_outcomes(tmp_path, count=12, ci_passed=True)
    monkeypatch.chdir(tmp_path)

    run_trust(as_json=False)
    out = capsys.readouterr().out
    assert "TRUST PROFILE" in out
    assert "ADJUSTMENTS" in out


def _create_outcomes(root, count=12, ci_passed=True):
    """Create review-outcome.json files for testing."""
    tasks_dir = root / ".harness-flow" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        task_dir = tasks_dir / f"task-{i + 1:03d}"
        task_dir.mkdir(exist_ok=True)
        outcome = {
            "task_id": f"task-{i + 1:03d}",
            "prediction": {
                "eval_aggregate": 8.0,
                "verdict": "PASS" if ci_passed else "ITERATE",
            },
            "outcome": {
                "ci_passed": ci_passed,
                "has_revert": False,
            },
            "updated_at": f"2026-04-{i + 1:02d}T00:00:00Z",
        }
        (task_dir / "review-outcome.json").write_text(
            json.dumps(outcome, indent=2)
        )
