"""迭代合同引擎 — 解析、验证、交付物检查、JSON sidecar"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Deliverable:
    description: str
    done: bool = False


@dataclass
class Contract:
    iteration: int = 0
    deliverables: list[Deliverable] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    technical_summary: str = ""
    complexity: str = "medium"  # simple / medium / complex

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "deliverables": [{"text": d.description, "done": d.done} for d in self.deliverables],
            "acceptance_criteria": self.acceptance_criteria,
            "technical_summary": self.technical_summary,
            "complexity": self.complexity,
        }


def parse_contract(markdown: str) -> Contract:
    """从 Markdown 文本解析合同"""
    contract = Contract()

    # 解析迭代号
    m = re.search(r"Iteration\s+(\d+)", markdown)
    if m:
        contract.iteration = int(m.group(1))

    # 解析交付物
    for match in re.finditer(r"-\s*\[([ xX])\]\s*(.+)", markdown):
        done = match.group(1).strip().lower() == "x"
        contract.deliverables.append(Deliverable(
            description=match.group(2).strip(),
            done=done,
        ))

    # 解析验收标准（数字列表）
    in_criteria = False
    for line in markdown.split("\n"):
        stripped = line.strip()
        if "验收标准" in stripped or "acceptance" in stripped.lower():
            in_criteria = True
            continue
        if in_criteria:
            if stripped.startswith("#"):
                in_criteria = False
                continue
            m = re.match(r"\d+\.\s+(.+)", stripped)
            if m:
                contract.acceptance_criteria.append(m.group(1).strip())

    # 解析技术摘要
    m = re.search(r"技术摘要\s*\n+(.+?)(?=\n##|\n#|\Z)", markdown, re.DOTALL)
    if m:
        contract.technical_summary = m.group(1).strip()

    # 解析复杂度
    m = re.search(r"复杂度\s*\n+\s*(simple|medium|complex)", markdown, re.IGNORECASE)
    if m:
        contract.complexity = m.group(1).lower()

    return contract


def write_contract_sidecar(contract: Contract, md_path: Path) -> Path:
    """Write a JSON sidecar alongside the markdown contract file."""
    json_path = md_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(contract.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return json_path


def verify_deliverables(contract: Contract) -> tuple[int, int]:
    """返回 (已完成数, 总数)"""
    done = sum(1 for d in contract.deliverables if d.done)
    return done, len(contract.deliverables)
