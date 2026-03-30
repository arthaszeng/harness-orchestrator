"""四维评分 + 短板加权算法 + JSON sidecar"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Scores:
    completeness: float = 0.0
    quality: float = 0.0
    regression: float = 0.0
    design: float = 0.0

    @property
    def values(self) -> list[float]:
        return [self.completeness, self.quality, self.regression, self.design]

    @property
    def weighted(self) -> float:
        """短板加权：最低分权重 2x，其余 1x"""
        vals = self.values
        if not vals or all(v == 0 for v in vals):
            return 0.0
        min_val = min(vals)
        weights = [2.0 if v == min_val else 1.0 for v in vals]
        return sum(v * w for v, w in zip(vals, weights)) / sum(weights)

    @property
    def min_score(self) -> float:
        return min(self.values) if self.values else 0.0

    def verdict(self, threshold: float = 3.5) -> str:
        """PASS / ITERATE 判定"""
        if self.weighted >= threshold and self.min_score > 1.0:
            return "PASS"
        return "ITERATE"

    def to_dict(self) -> dict[str, float]:
        return {
            "completeness": self.completeness,
            "quality": self.quality,
            "regression": self.regression,
            "design": self.design,
        }


def parse_scores(markdown: str) -> Scores:
    """从 Evaluator 输出的 Markdown 中解析评分"""
    scores = Scores()

    patterns = {
        "completeness": r"completeness\s*\|\s*([\d.]+)",
        "quality": r"quality\s*\|\s*([\d.]+)",
        "regression": r"regression\s*\|\s*([\d.]+)",
        "design": r"design\s*\|\s*([\d.]+)",
    }

    for dim, pattern in patterns.items():
        m = re.search(pattern, markdown, re.IGNORECASE)
        if m:
            setattr(scores, dim, float(m.group(1)))

    return scores


def write_evaluation_sidecar(
    scores: Scores,
    verdict: str,
    feedback: str,
    iteration: int,
    md_path: Path,
) -> Path:
    """Write a JSON sidecar alongside the markdown evaluation file."""
    data: dict[str, Any] = {
        "iteration": iteration,
        "scores": scores.to_dict(),
        "weighted": round(scores.weighted, 2),
        "verdict": verdict,
        "feedback": [line.strip() for line in feedback.split("\n") if line.strip()][:20],
    }
    json_path = md_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return json_path
