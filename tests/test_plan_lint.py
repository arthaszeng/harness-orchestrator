"""Tests for harness.core.plan_lint — plan.md structural validation."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from harness.cli import app
from harness.core.plan_lint import lint_plan

runner = CliRunner()

VALID_PLAN = """\
# Spec

## System Design Thinking

### Core Challenges
Async reliability is the core challenge.

### Architectural Constraints
- Testability: injectable time functions

### Design Pitfalls
- Hardcoded sleep calls

## Analysis
Technical analysis here.

## Approach
Implementation approach here.

## Impact
Impact description.

## Risks
Risk list.

---

# Contract

## Design Principles
- [ ] DP1: Injectable sleep
- [ ] DP2: Idempotency lock

## Deliverables
- [ ] **D1: First deliverable**
  - AC: something

## Acceptance Criteria
- All tests pass

## Out of Scope
- Nothing extra
"""

PLAN_WITHOUT_DESIGN_SECTIONS = """\
# Spec

## Analysis
Technical analysis here.

## Approach
Implementation approach here.

## Impact
Impact description.

## Risks
Risk list.

---

# Contract

## Deliverables
- [ ] **D1: First deliverable**
  - AC: something

## Acceptance Criteria
- All tests pass

## Out of Scope
- Nothing extra
"""

MINIMAL_PLAN = "# Just some text"


class TestLintPlan:
    def test_valid_plan(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text(VALID_PLAN)
        result = lint_plan(p)
        assert result.valid is True
        assert result.has_spec is True
        assert result.has_contract is True
        assert result.has_design_thinking is True
        assert result.has_design_principles is True
        assert result.deliverable_count >= 1

    def test_missing_file(self, tmp_path):
        result = lint_plan(tmp_path / "nonexistent.md")
        assert result.valid is False
        assert any(e.code == "MISSING" for e in result.errors)

    def test_empty_file(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text("")
        result = lint_plan(p)
        assert result.valid is False
        assert any(e.code == "EMPTY" for e in result.errors)

    def test_missing_spec(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text("# Contract\n## Deliverables\n- [ ] D1\n## Acceptance Criteria\n- ok\n## Out of Scope\n- none")
        result = lint_plan(p)
        assert result.valid is False
        assert any(e.code == "NO_SPEC" for e in result.errors)

    def test_missing_contract(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text("# Spec\n## Analysis\nx\n## Approach\nx\n## Impact\nx\n## Risks\nx")
        result = lint_plan(p)
        assert result.valid is False
        assert any(e.code == "NO_CONTRACT" for e in result.errors)

    def test_no_deliverables(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text("# Spec\n## Analysis\n## Approach\n## Impact\n## Risks\n# Contract\n## Deliverables\n## Acceptance Criteria\n## Out of Scope")
        result = lint_plan(p)
        assert result.valid is False
        assert any(e.code == "NO_DELIVERABLES" for e in result.errors)

    def test_to_dict(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text(VALID_PLAN)
        result = lint_plan(p)
        d = result.to_dict()
        assert "valid" in d
        assert "errors" in d
        assert "deliverable_count" in d
        assert "plan_mode" in d
        assert d["plan_mode"] in ("small", "medium", "large")

    def test_estimated_files_extraction(self, tmp_path):
        p = tmp_path / "plan.md"
        content = VALID_PLAN + "\n~40 files affected\n"
        p.write_text(content)
        result = lint_plan(p)
        assert result.estimated_files == 40

    def test_missing_design_thinking_is_error(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text(PLAN_WITHOUT_DESIGN_SECTIONS)
        result = lint_plan(p)
        assert result.valid is False
        assert result.has_design_thinking is False
        assert any(e.code == "NO_DESIGN_THINKING" for e in result.errors)

    def test_missing_design_principles_is_error(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text(PLAN_WITHOUT_DESIGN_SECTIONS)
        result = lint_plan(p)
        assert result.valid is False
        assert result.has_design_principles is False
        assert any(e.code == "NO_DESIGN_PRINCIPLES" for e in result.errors)

    def test_valid_plan_has_design_sections(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text(VALID_PLAN)
        result = lint_plan(p)
        d = result.to_dict()
        assert d["has_design_thinking"] is True
        assert d["has_design_principles"] is True
        assert not any(e["code"] == "NO_DESIGN_THINKING" for e in d["errors"])
        assert not any(e["code"] == "NO_DESIGN_PRINCIPLES" for e in d["errors"])


class TestPlanLintCLI:
    """CLI-layer tests for plan-lint command."""

    def test_no_task_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow").mkdir()
        result = runner.invoke(app, ["plan-lint", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert "error" in data

    def test_valid_plan_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text(VALID_PLAN)
        (task_dir / "workflow-state.json").write_text(
            json.dumps({"task_id": "task-001", "phase": "planning"})
        )
        result = runner.invoke(app, ["plan-lint", "--task", "task-001", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert "plan_mode" in data

    def test_invalid_plan_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Just text")
        (task_dir / "workflow-state.json").write_text(
            json.dumps({"task_id": "task-001", "phase": "planning"})
        )
        result = runner.invoke(app, ["plan-lint", "--task", "task-001", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_json_schema_snapshot(self, tmp_path, monkeypatch):
        """Pin the plan-lint output schema keys."""
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text(VALID_PLAN)
        (task_dir / "workflow-state.json").write_text(
            json.dumps({"task_id": "task-001", "phase": "planning"})
        )
        result = runner.invoke(app, ["plan-lint", "--task", "task-001", "--json"])
        data = json.loads(result.stdout)
        required_keys = {
            "valid", "errors", "has_spec", "has_contract",
            "has_design_thinking", "has_design_principles",
            "deliverable_count", "estimated_files", "plan_mode",
        }
        assert required_keys.issubset(set(data.keys()))
