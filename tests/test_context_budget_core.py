"""Tests for core/context_budget.py — pure function tests for token estimation and budget checking."""

from __future__ import annotations

from pathlib import Path

from harness.core.context_budget import (
    ARTIFACT_GLOBS,
    CHARS_PER_TOKEN,
    BudgetResult,
    check_budget,
    estimate_task_tokens,
    scan_artifacts,
)


class TestScanArtifacts:
    def test_empty_dir(self, tmp_path: Path):
        result = scan_artifacts(tmp_path)
        assert result == []

    def test_matches_plan_md(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text("hello world", encoding="utf-8")
        result = scan_artifacts(tmp_path)
        assert len(result) == 1
        assert result[0].name == "plan.md"
        assert result[0].chars == 11
        assert result[0].tokens == 11 // CHARS_PER_TOKEN

    def test_ignores_non_artifact_files(self, tmp_path: Path):
        (tmp_path / "random.txt").write_text("ignored", encoding="utf-8")
        (tmp_path / "notes.py").write_text("also ignored", encoding="utf-8")
        result = scan_artifacts(tmp_path)
        assert result == []

    def test_matches_multiple_globs(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text("a" * 100, encoding="utf-8")
        (tmp_path / "workflow-state.json").write_text("{}", encoding="utf-8")
        (tmp_path / "build-r1.md").write_text("log", encoding="utf-8")
        result = scan_artifacts(tmp_path)
        names = {f.name for f in result}
        assert names == {"plan.md", "workflow-state.json", "build-r1.md"}

    def test_custom_globs(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text("plan", encoding="utf-8")
        (tmp_path / "custom.txt").write_text("custom", encoding="utf-8")
        result = scan_artifacts(tmp_path, globs=["custom.txt"])
        assert len(result) == 1
        assert result[0].name == "custom.txt"

    def test_skips_unreadable_file(self, tmp_path: Path):
        binary_path = tmp_path / "plan.md"
        binary_path.write_bytes(b"\x80\x81\x82")
        result = scan_artifacts(tmp_path)
        assert result == []


class TestEstimateTaskTokens:
    def test_returns_budget_result(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text("x" * 400, encoding="utf-8")
        result = estimate_task_tokens(tmp_path)
        assert isinstance(result, BudgetResult)
        assert result.total_chars == 400
        assert result.total_tokens == 100
        assert result.budget == 0
        assert result.over_budget is False

    def test_empty_dir(self, tmp_path: Path):
        result = estimate_task_tokens(tmp_path)
        assert result.total_tokens == 0
        assert result.files == []


class TestCheckBudget:
    def test_under_budget(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text("x" * 400, encoding="utf-8")
        result = check_budget(tmp_path, budget=1000)
        assert result.over_budget is False
        assert result.budget == 1000
        assert result.total_tokens == 100

    def test_over_budget(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text("x" * 400, encoding="utf-8")
        result = check_budget(tmp_path, budget=50)
        assert result.over_budget is True
        assert result.total_tokens == 100
        assert result.budget == 50

    def test_exact_boundary(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text("x" * 400, encoding="utf-8")
        result = check_budget(tmp_path, budget=100)
        assert result.over_budget is False

    def test_empty_dir_under_budget(self, tmp_path: Path):
        result = check_budget(tmp_path, budget=50000)
        assert result.over_budget is False
        assert result.total_tokens == 0


class TestConstants:
    def test_chars_per_token(self):
        assert CHARS_PER_TOKEN == 4

    def test_artifact_globs_contains_plan(self):
        assert "plan.md" in ARTIFACT_GLOBS
