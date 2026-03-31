"""Tests for evaluation parsing, feedback extraction, and iteration prompt."""

from pathlib import Path

from harness.methodology.evaluation import (
    _extract_feedback_section,
    parse_evaluation,
)
from harness.orchestrator.workflow import _build_iterate_prompt


_EVAL_MARKDOWN = """\
# Evaluation — Iteration 1

## 评分
| 维度 | 分数 | 说明 |
|------|------|------|
| completeness | 3.5 | done |
| quality | 2.0 | bad |
| regression | 1.5 | deleted tests |
| design | 3.5 | ok |

## 加权得分
2.2 (短板加权)

## 判定
ITERATE

## 反馈
- P0: Restore Registry normalization.
- P1: Add init test coverage.
- P1: Add workflow assertion for model passthrough.
"""

_EVAL_ENGLISH = """\
# Evaluation — Iteration 2

## Scores
| dimension | score | notes |
|-----------|-------|-------|
| completeness | 4.0 | good |
| quality | 3.5 | clean |
| regression | 4.0 | safe |
| design | 3.0 | minor concern |

## Weighted Score
3.4

## Verdict
ITERATE

## Feedback
1. Fix the minor design concern in config loading.
2. Add one more edge-case test.
"""


def test_extract_feedback_section_chinese():
    result = _extract_feedback_section(_EVAL_MARKDOWN)
    assert "P0: Restore Registry normalization." in result
    assert "P1: Add init test coverage." in result
    assert "加权得分" not in result
    assert "completeness | 3.5" not in result


def test_extract_feedback_section_english():
    result = _extract_feedback_section(_EVAL_ENGLISH)
    assert "Fix the minor design concern" in result
    assert "Add one more edge-case test" in result
    assert "Weighted Score" not in result
    assert "completeness | 4.0" not in result


def test_extract_feedback_section_no_marker():
    raw = "Some plain text without any feedback section header."
    result = _extract_feedback_section(raw)
    assert result == raw


def test_parse_evaluation_returns_extracted_feedback():
    result = parse_evaluation(_EVAL_MARKDOWN)
    assert result.verdict == "ITERATE"
    assert result.scores is not None
    assert result.scores.completeness == 3.5
    assert result.scores.regression == 1.5
    assert "P0: Restore Registry normalization." in result.feedback
    assert "加权得分" not in result.feedback
    assert result.raw_output == _EVAL_MARKDOWN


def test_parse_evaluation_pass_threshold():
    high_score = (
        "| completeness | 4.0 |\n"
        "| quality | 4.0 |\n"
        "| regression | 4.0 |\n"
        "| design | 4.0 |\n"
    )
    result = parse_evaluation(high_score, threshold=3.5)
    assert result.verdict == "PASS"


def test_build_iterate_prompt_includes_previous_contract():
    prompt = _build_iterate_prompt(
        "add feature X",
        "fix the bug in Y",
        Path("/fake/root"),
        previous_contract="# Contract — Iteration 1\n- [ ] do thing",
    )
    assert "Contract — Iteration 1" in prompt
    assert "do thing" in prompt
    assert "fix the bug in Y" in prompt
    assert "add feature X" in prompt


def test_build_iterate_prompt_empty_contract():
    prompt = _build_iterate_prompt(
        "add feature X",
        "feedback text",
        Path("/fake/root"),
        previous_contract="",
    )
    assert "(none)" in prompt
    assert "feedback text" in prompt
