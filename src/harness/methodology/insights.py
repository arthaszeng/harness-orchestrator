"""Task-level learning insights — structured summary generated at task termination."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

_MAX_LEARNING_ITEMS = 5
_STRONG_THRESHOLD = 4.0
_WEAK_THRESHOLD = 3.0


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@dataclass
class TaskMeta:
    task_id: str
    requirement: str
    verdict: str  # PASS / BLOCKED
    iterations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requirement": self.requirement,
            "verdict": self.verdict,
            "iterations": self.iterations,
        }


@dataclass
class QualitySummary:
    final_score: float
    weighted_score: float
    dimension_scores: dict[str, float] = field(default_factory=dict)
    evaluation_verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_score": round(self.final_score, 2),
            "weighted_score": round(self.weighted_score, 2),
            "dimension_scores": {k: round(v, 2) for k, v in self.dimension_scores.items()},
            "evaluation_verdict": self.evaluation_verdict,
        }


@dataclass
class AlignmentSummary:
    has_alignment: bool = False
    aligned: bool | None = None
    misaligned: bool = False
    contract_issue: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_alignment": self.has_alignment,
            "aligned": self.aligned,
            "misaligned": self.misaligned,
            "contract_issue": self.contract_issue,
        }


@dataclass
class LearningSummary:
    strengths: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    next_focus: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strengths": self.strengths[:_MAX_LEARNING_ITEMS],
            "issues": self.issues[:_MAX_LEARNING_ITEMS],
            "next_focus": self.next_focus[:_MAX_LEARNING_ITEMS],
        }


@dataclass
class SourceArtifacts:
    evaluation_json: str | None = None
    evaluation_md: str | None = None
    alignment_md: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_json": self.evaluation_json,
            "evaluation_md": self.evaluation_md,
            "alignment_md": self.alignment_md,
        }


@dataclass
class TaskInsights:
    schema_version: str
    generated_at: str
    task: TaskMeta
    quality_summary: QualitySummary | None
    alignment_summary: AlignmentSummary
    learning_summary: LearningSummary
    source_artifacts: SourceArtifacts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "task": self.task.to_dict(),
            "quality_summary": self.quality_summary.to_dict() if self.quality_summary else None,
            "alignment_summary": self.alignment_summary.to_dict(),
            "learning_summary": self.learning_summary.to_dict(),
            "source_artifacts": self.source_artifacts.to_dict(),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ITER_NUM_RE = re.compile(r"-r(\d+)\.")


def _find_latest_artifact(task_dir: Path, pattern: str) -> Path | None:
    """按迭代号数值选择最新匹配的工件路径（而非字典序）。"""
    matches = list(task_dir.glob(pattern))
    if not matches:
        return None

    def _iter_num(p: Path) -> int:
        m = _ITER_NUM_RE.search(p.name)
        return int(m.group(1)) if m else 0

    return max(matches, key=_iter_num)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _extract_alignment_flags(alignment_text: str) -> AlignmentSummary:
    """从 alignment markdown 中做标记级提取，显式 verdict 驱动。

    只有存在明确 ``ALIGNED`` 关键词（且不含 ``MISALIGNED``）时才记为通过；
    失败输出、空输出或未识别文本稳定降级为 ``aligned=None``。
    """
    summary = AlignmentSummary(has_alignment=True)
    if "MISALIGNED" in alignment_text:
        summary.misaligned = True
        summary.aligned = False
    elif "CONTRACT_ISSUE" in alignment_text:
        summary.contract_issue = True
        summary.aligned = False
    elif "ALIGNED" in alignment_text:
        summary.aligned = True
    else:
        summary.aligned = None
    return summary


def _extract_learning(eval_data: dict[str, Any]) -> LearningSummary:
    """基于 evaluation sidecar 的维度分数派生稳定的学习条目。"""
    summary = LearningSummary()
    scores = eval_data.get("scores", {})

    for dim, score in scores.items():
        if not isinstance(score, (int, float)):
            continue
        if score >= _STRONG_THRESHOLD:
            summary.strengths.append(f"{dim}: {score}")
        elif score < _WEAK_THRESHOLD:
            summary.issues.append(f"{dim}: {score}")
            summary.next_focus.append(f"improve {dim}")

    summary.strengths = summary.strengths[:_MAX_LEARNING_ITEMS]
    summary.issues = summary.issues[:_MAX_LEARNING_ITEMS]
    summary.next_focus = summary.next_focus[:_MAX_LEARNING_ITEMS]
    return summary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_task_insights(
    task_id: str,
    requirement: str,
    verdict: str,
    iterations: int,
    task_dir: Path,
    *,
    feedback: str = "",
) -> TaskInsights:
    """基于任务目录中的 evaluation/alignment 工件生成结构化摘要。

    即使完全缺少 sidecar，也会输出包含基础元数据的降级摘要。
    """
    task_meta = TaskMeta(
        task_id=task_id,
        requirement=requirement,
        verdict=verdict,
        iterations=iterations,
    )

    eval_json_path = _find_latest_artifact(task_dir, "evaluation-r*.json")
    eval_md_path = _find_latest_artifact(task_dir, "evaluation-r*.md")
    alignment_md_path = _find_latest_artifact(task_dir, "alignment-r*.md")

    # --- quality summary ---
    quality_summary: QualitySummary | None = None
    eval_data: dict[str, Any] | None = None
    if eval_json_path:
        eval_data = _load_json(eval_json_path)
        if eval_data:
            quality_summary = QualitySummary(
                final_score=eval_data.get("weighted", 0.0),
                weighted_score=eval_data.get("weighted", 0.0),
                dimension_scores=eval_data.get("scores", {}),
                evaluation_verdict=eval_data.get("verdict", ""),
            )

    # --- alignment summary ---
    alignment_summary = AlignmentSummary()
    if alignment_md_path and alignment_md_path.exists():
        try:
            alignment_text = alignment_md_path.read_text(encoding="utf-8")
            alignment_summary = _extract_alignment_flags(alignment_text)
        except OSError:
            pass

    # --- learning summary ---
    learning_summary = LearningSummary()
    if eval_data:
        learning_summary = _extract_learning(eval_data)
    elif verdict == "BLOCKED" and feedback:
        learning_summary.issues.append(feedback[:200])

    # --- source artifacts (相对文件名) ---
    source_artifacts = SourceArtifacts(
        evaluation_json=eval_json_path.name if eval_json_path else None,
        evaluation_md=eval_md_path.name if eval_md_path else None,
        alignment_md=alignment_md_path.name if alignment_md_path else None,
    )

    return TaskInsights(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        task=task_meta,
        quality_summary=quality_summary,
        alignment_summary=alignment_summary,
        learning_summary=learning_summary,
        source_artifacts=source_artifacts,
    )


def write_task_insights(insights: TaskInsights, task_dir: Path) -> Path:
    """将 insights JSON 写入任务目录。"""
    path = task_dir / "insights.json"
    path.write_text(
        json.dumps(insights.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_task_insights(task_dir: Path) -> TaskInsights | None:
    """从任务目录加载 insights，不存在或解析失败时返回 None。

    为后续 Reflector/Strategist 预留的统一读取入口。
    """
    path = task_dir / "insights.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def _from_dict(data: dict[str, Any]) -> TaskInsights:
    task_d = data["task"]
    quality_d = data.get("quality_summary")
    alignment_d = data.get("alignment_summary", {})
    learning_d = data.get("learning_summary", {})
    source_d = data.get("source_artifacts", {})

    return TaskInsights(
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        generated_at=data.get("generated_at", ""),
        task=TaskMeta(**task_d),
        quality_summary=QualitySummary(
            final_score=quality_d["final_score"],
            weighted_score=quality_d["weighted_score"],
            dimension_scores=quality_d.get("dimension_scores", {}),
            evaluation_verdict=quality_d.get("evaluation_verdict", ""),
        ) if quality_d else None,
        alignment_summary=AlignmentSummary(
            has_alignment=alignment_d.get("has_alignment", False),
            aligned=alignment_d.get("aligned"),
            misaligned=alignment_d.get("misaligned", False),
            contract_issue=alignment_d.get("contract_issue", False),
        ),
        learning_summary=LearningSummary(
            strengths=learning_d.get("strengths", []),
            issues=learning_d.get("issues", []),
            next_focus=learning_d.get("next_focus", []),
        ),
        source_artifacts=SourceArtifacts(
            evaluation_json=source_d.get("evaluation_json"),
            evaluation_md=source_d.get("evaluation_md"),
            alignment_md=source_d.get("alignment_md"),
        ),
    )
