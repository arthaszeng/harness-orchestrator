"""Tests for harness.core.artifact_graph — artifact dependency graph."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.core.artifact_graph import (
    STANDARD_ARTIFACTS,
    ARTIFACT_BY_ID,
    ArtifactInfo,
    ArtifactStatus,
    compute_artifact_report,
    suggest_next_actions,
)


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task-099"
    d.mkdir()
    return d


class TestArtifactDefFindFile:
    def test_simple_file_found(self, task_dir: Path) -> None:
        (task_dir / "plan.md").write_text("# Plan", encoding="utf-8")
        adef = ARTIFACT_BY_ID["plan"]
        found = adef.find_file(task_dir)
        assert found is not None
        assert found.name == "plan.md"

    def test_simple_file_not_found(self, task_dir: Path) -> None:
        adef = ARTIFACT_BY_ID["plan"]
        assert adef.find_file(task_dir) is None

    def test_round_numbered_returns_highest(self, task_dir: Path) -> None:
        (task_dir / "code-eval-r1.md").write_text("round 1", encoding="utf-8")
        (task_dir / "code-eval-r3.md").write_text("round 3", encoding="utf-8")
        (task_dir / "code-eval-r2.md").write_text("round 2", encoding="utf-8")
        adef = ARTIFACT_BY_ID["code-eval"]
        found = adef.find_file(task_dir)
        assert found is not None
        assert found.name == "code-eval-r3.md"

    def test_round_numbered_legacy_format(self, task_dir: Path) -> None:
        (task_dir / "build-r1.md").write_text("build 1", encoding="utf-8")
        (task_dir / "build-r2.log").write_text("build 2 legacy", encoding="utf-8")
        adef = ARTIFACT_BY_ID["build-log"]
        found = adef.find_file(task_dir)
        assert found is not None
        assert "r2" in found.name

    def test_nonexistent_dir(self) -> None:
        adef = ARTIFACT_BY_ID["plan"]
        assert adef.find_file(Path("/nonexistent/dir")) is None


class TestArtifactDefFileExists:
    def test_exists_nonempty(self, task_dir: Path) -> None:
        (task_dir / "plan.md").write_text("# Plan", encoding="utf-8")
        assert ARTIFACT_BY_ID["plan"].file_exists(task_dir) is True

    def test_exists_empty(self, task_dir: Path) -> None:
        (task_dir / "plan.md").write_text("", encoding="utf-8")
        assert ARTIFACT_BY_ID["plan"].file_exists(task_dir) is False

    def test_not_exists(self, task_dir: Path) -> None:
        assert ARTIFACT_BY_ID["plan"].file_exists(task_dir) is False


class TestComputeArtifactReport:
    def test_empty_task_dir(self, task_dir: Path) -> None:
        report = compute_artifact_report(task_dir)
        assert report.task_id == "task-099"
        assert len(report.artifacts) == len(STANDARD_ARTIFACTS)
        plan_info = next(a for a in report.artifacts if a.id == "plan")
        assert plan_info.status == ArtifactStatus.READY
        for a in report.artifacts:
            if a.id != "plan":
                assert a.status in (ArtifactStatus.READY, ArtifactStatus.BLOCKED)

    def test_plan_only(self, task_dir: Path) -> None:
        _write_valid_plan(task_dir)
        report = compute_artifact_report(task_dir)
        plan_info = next(a for a in report.artifacts if a.id == "plan")
        assert plan_info.status == ArtifactStatus.DONE
        assert plan_info.file_path == "plan.md"

        for dep_id in ("plan-eval", "handoff-plan", "build-log"):
            dep = next(a for a in report.artifacts if a.id == dep_id)
            assert dep.status == ArtifactStatus.READY, f"{dep_id} should be ready"

    def test_plan_and_build_log(self, task_dir: Path) -> None:
        _write_valid_plan(task_dir)
        (task_dir / "build-r1.md").write_text("# Build Round 1\ncontent", encoding="utf-8")
        report = compute_artifact_report(task_dir)

        assert next(a for a in report.artifacts if a.id == "plan").status == ArtifactStatus.DONE
        assert next(a for a in report.artifacts if a.id == "build-log").status == ArtifactStatus.DONE

        code_eval = next(a for a in report.artifacts if a.id == "code-eval")
        assert code_eval.status == ArtifactStatus.READY

    def test_full_pipeline(self, task_dir: Path) -> None:
        _write_valid_plan(task_dir)
        (task_dir / "plan-eval-r1.md").write_text("eval\n## Verdict: PASS", encoding="utf-8")
        (task_dir / "handoff-plan.json").write_text("{}", encoding="utf-8")
        (task_dir / "build-r1.md").write_text("build", encoding="utf-8")
        (task_dir / "handoff-build.json").write_text("{}", encoding="utf-8")
        (task_dir / "code-eval-r2.md").write_text("code eval\n## Verdict: PASS", encoding="utf-8")
        (task_dir / "ship-metrics.json").write_text("{}", encoding="utf-8")
        (task_dir / "feedback-ledger.jsonl").write_text("{}\n", encoding="utf-8")
        (task_dir / "failure-patterns.jsonl").write_text("{}\n", encoding="utf-8")

        report = compute_artifact_report(task_dir)
        assert all(a.status == ArtifactStatus.DONE for a in report.artifacts)
        assert len(report.next_actions) == 0

    def test_invalid_plan_detected(self, task_dir: Path) -> None:
        (task_dir / "plan.md").write_text("just text no structure", encoding="utf-8")
        report = compute_artifact_report(task_dir)
        plan_info = next(a for a in report.artifacts if a.id == "plan")
        assert plan_info.status == ArtifactStatus.INVALID
        assert len(plan_info.validation_errors) > 0

    def test_blocked_dependencies(self, task_dir: Path) -> None:
        report = compute_artifact_report(task_dir)
        code_eval = next(a for a in report.artifacts if a.id == "code-eval")
        assert code_eval.status == ArtifactStatus.BLOCKED

    def test_no_validators_skips_validation(self, task_dir: Path) -> None:
        (task_dir / "plan.md").write_text("just text", encoding="utf-8")
        report = compute_artifact_report(task_dir, validators={})
        plan_info = next(a for a in report.artifacts if a.id == "plan")
        assert plan_info.status == ArtifactStatus.DONE


class TestSuggestNextActions:
    def test_empty_ready_plan(self) -> None:
        artifacts = [
            ArtifactInfo(id="plan", status=ArtifactStatus.READY, description=""),
            ArtifactInfo(id="build-log", status=ArtifactStatus.BLOCKED, description=""),
        ]
        actions = suggest_next_actions(artifacts)
        assert len(actions) >= 1
        assert "plan" in actions[0].lower()

    def test_plan_done_build_ready(self) -> None:
        artifacts = [
            ArtifactInfo(id="plan", status=ArtifactStatus.DONE, description=""),
            ArtifactInfo(id="build-log", status=ArtifactStatus.READY, description=""),
            ArtifactInfo(id="code-eval", status=ArtifactStatus.BLOCKED, description=""),
        ]
        actions = suggest_next_actions(artifacts)
        assert any("build" in a.lower() or "implement" in a.lower() for a in actions)

    def test_invalid_shows_fix(self) -> None:
        artifacts = [
            ArtifactInfo(
                id="plan",
                status=ArtifactStatus.INVALID,
                description="",
                validation_errors=["missing Spec section"],
            ),
        ]
        actions = suggest_next_actions(artifacts)
        assert any("fix" in a.lower() for a in actions)

    def test_all_done_no_actions(self) -> None:
        artifacts = [
            ArtifactInfo(id="plan", status=ArtifactStatus.DONE, description=""),
            ArtifactInfo(id="code-eval", status=ArtifactStatus.DONE, description=""),
        ]
        actions = suggest_next_actions(artifacts)
        assert len(actions) == 0


class TestReportSerialization:
    def test_to_dict_structure(self, task_dir: Path) -> None:
        _write_valid_plan(task_dir)
        report = compute_artifact_report(task_dir)
        d = report.to_dict()
        assert "task_id" in d
        assert "artifacts" in d
        assert "summary" in d
        assert "next_actions" in d
        assert isinstance(d["summary"]["done"], list)
        assert isinstance(d["summary"]["ready"], list)
        assert isinstance(d["summary"]["blocked"], list)
        json_str = json.dumps(d)
        assert json.loads(json_str) == d


class TestStandardArtifactDefinitions:
    def test_no_duplicate_ids(self) -> None:
        ids = [a.id for a in STANDARD_ARTIFACTS]
        assert len(ids) == len(set(ids))

    def test_all_requires_reference_valid_ids(self) -> None:
        valid_ids = {a.id for a in STANDARD_ARTIFACTS}
        for a in STANDARD_ARTIFACTS:
            for req in a.requires:
                assert req in valid_ids, f"{a.id} requires unknown artifact {req!r}"

    def test_no_cycles(self) -> None:
        """Verify the dependency graph is acyclic."""
        visited: set[str] = set()
        path: set[str] = set()

        def dfs(node_id: str) -> None:
            if node_id in path:
                raise AssertionError(f"cycle detected involving {node_id}")
            if node_id in visited:
                return
            path.add(node_id)
            adef = ARTIFACT_BY_ID.get(node_id)
            if adef:
                for dep in adef.requires:
                    dfs(dep)
            path.discard(node_id)
            visited.add(node_id)

        for a in STANDARD_ARTIFACTS:
            dfs(a.id)


def _write_valid_plan(task_dir: Path) -> None:
    """Write a plan.md that passes plan-lint."""
    content = """# Spec

## System Design Thinking

### Core Challenge
Test challenge.

### Architecture Constraints
Test constraints.

### Design Pitfalls
Test pitfalls.

## Analysis
Test analysis.

## Approach
Test approach.

## Impact
~3 files affected.

## Risks
Low risk.

---

# Contract

## Design Principles

- [ ] DP1: Test principle

## Deliverables
- [ ] D1: Test deliverable

## Acceptance Criteria
- All tests pass

## Out of Scope
- Nothing
"""
    (task_dir / "plan.md").write_text(content, encoding="utf-8")
