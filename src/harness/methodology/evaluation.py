"""Two-stage evaluation orchestration."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from harness.i18n import t
from harness.methodology.scoring import Scores, parse_scores

_CI_PREFIX = "    │ "


@dataclass
class EvalResult:
    verdict: str  # PASS / ITERATE / CI_FAIL
    stage: int  # 1 = CI gate, 2 = deep review
    scores: Scores | None = None
    feedback: str = ""
    raw_output: str = ""


def run_ci_check(
    ci_command: str,
    cwd: Path,
    on_output: Callable[[str], None] | None = None,
) -> EvalResult:
    """Stage 1: run CI command; stream via on_output or stderr."""
    if not ci_command.strip():
        return EvalResult(verdict="PASS", stage=1, feedback="No CI command configured")

    try:
        proc = subprocess.Popen(
            shlex.split(ci_command),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as e:
        return EvalResult(
            verdict="CI_FAIL", stage=1,
            feedback=t("eval.ci_not_found", error=str(e)),
        )

    start = time.monotonic()
    lines: list[str] = []

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if on_output:
                on_output(line)
            else:
                sys.stderr.write(f"{_CI_PREFIX}{line}")
                sys.stderr.flush()

        proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return EvalResult(
            verdict="CI_FAIL", stage=1,
            feedback=t("eval.ci_timeout"),
        )

    elapsed = time.monotonic() - start
    output = "".join(lines)

    if proc.returncode != 0:
        if not on_output:
            sys.stderr.write(f"{_CI_PREFIX}{t('eval.ci_fail_stderr', elapsed=elapsed)}\n")
            sys.stderr.flush()
        return EvalResult(
            verdict="CI_FAIL", stage=1,
            feedback=output[-2000:],
            raw_output=output,
        )

    if not on_output:
        sys.stderr.write(f"{_CI_PREFIX}{t('eval.ci_pass_stderr', elapsed=elapsed)}\n")
        sys.stderr.flush()
    return EvalResult(verdict="PASS", stage=1, feedback=t("eval.ci_pass"))


_FEEDBACK_SECTION_RE = re.compile(
    r"^##\s*(?:反馈|Feedback)\s*\n(.*)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _extract_feedback_section(raw_output: str) -> str:
    """Extract the ## Feedback / ## 反馈 section from evaluator markdown.

    Returns only the actionable feedback items, not the full scoring table.
    Falls back to the complete output if no section marker is found.
    """
    m = _FEEDBACK_SECTION_RE.search(raw_output)
    if not m:
        return raw_output
    body = m.group(1).strip()
    return body if body else raw_output


def parse_evaluation(raw_output: str, threshold: float = 3.5) -> EvalResult:
    """Stage 2: parse evaluator agent output."""
    scores = parse_scores(raw_output)
    verdict = scores.verdict(threshold)
    feedback = _extract_feedback_section(raw_output)

    return EvalResult(
        verdict=verdict,
        stage=2,
        scores=scores,
        feedback=feedback,
        raw_output=raw_output,
    )
