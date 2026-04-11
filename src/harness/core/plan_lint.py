"""Plan.md structural validation (deterministic, no LLM).

Parses a plan.md file and checks for required sections and structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_DELIVERABLE_RE = re.compile(r"^\s*-\s*\[[ x]\]\s*\*?\*?D\d+", re.MULTILINE)
_CHECKBOX_RE = re.compile(r"^\s*-\s*\[[ x]\]", re.MULTILINE)

REQUIRED_SPEC_SECTIONS = {"analysis", "approach", "impact", "risks"}
REQUIRED_CONTRACT_SECTIONS = {"deliverables", "acceptance criteria", "out of scope"}


@dataclass
class PlanLintError:
    code: str
    message: str
    line: int | None = None


@dataclass
class PlanLintResult:
    valid: bool
    errors: list[PlanLintError] = field(default_factory=list)
    has_spec: bool = False
    has_contract: bool = False
    deliverable_count: int = 0
    estimated_files: int | None = None

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [{"code": e.code, "message": e.message, "line": e.line} for e in self.errors],
            "has_spec": self.has_spec,
            "has_contract": self.has_contract,
            "deliverable_count": self.deliverable_count,
            "estimated_files": self.estimated_files,
        }


def _normalize_heading(text: str) -> str:
    return text.strip().lower().rstrip("—–- ")


def lint_plan(plan_path: Path) -> PlanLintResult:
    """Validate plan.md structure and return lint result."""
    errors: list[PlanLintError] = []

    if not plan_path.exists():
        return PlanLintResult(
            valid=False,
            errors=[PlanLintError(code="MISSING", message=f"plan file not found: {plan_path}")],
        )

    content = plan_path.read_text(encoding="utf-8")
    if not content.strip():
        return PlanLintResult(
            valid=False,
            errors=[PlanLintError(code="EMPTY", message="plan file is empty")],
        )

    headings: list[tuple[int, str, int]] = []
    for i, line in enumerate(content.splitlines(), 1):
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = _normalize_heading(m.group(2))
            headings.append((level, title, i))

    heading_titles = {h[1] for h in headings}

    has_spec = "spec" in heading_titles
    has_contract = "contract" in heading_titles

    if not has_spec:
        errors.append(PlanLintError(code="NO_SPEC", message="missing '# Spec' section"))

    if not has_contract:
        errors.append(PlanLintError(code="NO_CONTRACT", message="missing '# Contract' section"))

    for req in REQUIRED_SPEC_SECTIONS:
        if req not in heading_titles:
            errors.append(PlanLintError(
                code="MISSING_SPEC_SECTION",
                message=f"missing Spec sub-section: {req}",
            ))

    for req in REQUIRED_CONTRACT_SECTIONS:
        if req not in heading_titles:
            errors.append(PlanLintError(
                code="MISSING_CONTRACT_SECTION",
                message=f"missing Contract sub-section: {req}",
            ))

    deliverables = _DELIVERABLE_RE.findall(content)
    if not deliverables:
        checkboxes = _CHECKBOX_RE.findall(content)
        deliverable_count = len(checkboxes)
    else:
        deliverable_count = len(deliverables)

    if deliverable_count == 0:
        errors.append(PlanLintError(
            code="NO_DELIVERABLES",
            message="no deliverables found (expected checkbox items in Contract)",
        ))

    estimated_files = _extract_estimated_files(content)

    valid = len(errors) == 0

    return PlanLintResult(
        valid=valid,
        errors=errors,
        has_spec=has_spec,
        has_contract=has_contract,
        deliverable_count=deliverable_count,
        estimated_files=estimated_files,
    )


_FILE_COUNT_RE = re.compile(r"~?(\d+)\s*(?:files?|文件)", re.IGNORECASE)


def _extract_estimated_files(content: str) -> int | None:
    """Best-effort extraction of estimated file count from plan text."""
    matches = _FILE_COUNT_RE.findall(content)
    if not matches:
        return None
    return max(int(m) for m in matches)
