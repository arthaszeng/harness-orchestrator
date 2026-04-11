"""Tests for harness.commands.review_score — review score calibration CLI."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from harness.cli import app

runner = CliRunner()


def _make_input(roles, **extra):
    data = {"roles": roles, **extra}
    return json.dumps(data)


class TestReviewScoreCompute:
    def test_plan_pass(self):
        inp = _make_input([
            {"role": "architect", "score": 8.0, "findings": []},
            {"role": "product_owner", "score": 8.0, "findings": []},
            {"role": "engineer", "score": 8.0, "findings": []},
            {"role": "qa", "score": 8.0, "findings": []},
            {"role": "project_manager", "score": 8.0, "findings": []},
        ])
        result = runner.invoke(app, ["review-score", "compute", "--kind", "plan"], input=inp)
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["verdict"] == "PASS"
        assert data["aggregate"] == 8.0

    def test_plan_iterate_low_score(self):
        inp = _make_input([
            {"role": "architect", "score": 5.0, "findings": []},
            {"role": "engineer", "score": 5.0, "findings": []},
        ])
        result = runner.invoke(app, ["review-score", "compute", "--kind", "plan"], input=inp)
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["verdict"] == "ITERATE"

    def test_code_critical_forces_iterate(self):
        inp = _make_input([
            {"role": "engineer", "score": 9.0, "findings": [
                {"severity": "CRITICAL", "text": "SQL injection"}
            ]},
        ])
        result = runner.invoke(app, ["review-score", "compute", "--kind", "code"], input=inp)
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["verdict"] == "ITERATE"
        assert data["has_critical"] is True

    def test_empty_input(self):
        result = runner.invoke(app, ["review-score", "compute", "--kind", "plan"], input="")
        assert result.exit_code == 1

    def test_invalid_json(self):
        result = runner.invoke(app, ["review-score", "compute", "--kind", "plan"], input="not json")
        assert result.exit_code == 1

    def test_missing_roles_field(self):
        result = runner.invoke(app, ["review-score", "compute", "--kind", "plan"], input='{"scores": []}')
        assert result.exit_code == 1

    def test_bad_kind(self):
        inp = _make_input([{"role": "architect", "score": 8.0, "findings": []}])
        result = runner.invoke(app, ["review-score", "compute", "--kind", "banana"], input=inp)
        assert result.exit_code == 1

    def test_repeat_penalty_applied(self):
        inp = _make_input(
            [
                {"role": "architect", "score": 8.0, "findings": [
                    {"severity": "WARN", "text": "Missing error handling"}
                ]},
            ],
            prior_round_findings=[["Missing error handling"]],
        )
        result = runner.invoke(app, ["review-score", "compute", "--kind", "plan"], input=inp)
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["calibration_applied"] > 0

    def test_json_schema_snapshot(self):
        """Pin the output schema."""
        inp = _make_input([
            {"role": "architect", "score": 7.5, "findings": []},
        ])
        result = runner.invoke(app, ["review-score", "compute", "--kind", "plan"], input=inp)
        data = json.loads(result.stdout)
        expected_keys = {
            "dimensions", "aggregate", "calibrated", "verdict",
            "has_critical", "score_band", "calibration_applied", "threshold",
        }
        assert set(data.keys()) == expected_keys
