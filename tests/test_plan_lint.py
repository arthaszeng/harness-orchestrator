"""Tests for harness.core.plan_lint — plan.md structural validation."""

from __future__ import annotations


from harness.core.plan_lint import lint_plan

VALID_PLAN = """\
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

    def test_estimated_files_extraction(self, tmp_path):
        p = tmp_path / "plan.md"
        content = VALID_PLAN + "\n~40 files affected\n"
        p.write_text(content)
        result = lint_plan(p)
        assert result.estimated_files == 40
