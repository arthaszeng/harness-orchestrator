"""Task identity resolution for branch names and task keys.

Supports multiple task-key strategies while keeping backward compatibility with
the historical ``task-NNN`` convention.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

TaskIdStrategy = Literal["numeric", "jira", "custom", "hybrid"]

_NUMERIC_PATTERN = r"task-\d+"
_JIRA_PATTERN = r"[A-Z][A-Z0-9]+-\d+"
_SAFE_CUSTOM_MAX_LEN = 128
_SAFE_KEY_MAX_LEN = 96

TASK_ID_STORAGE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$"
"""Storage-layer validation pattern for task IDs persisted in JSON artifacts.

This is intentionally broader than any single identity strategy — it defines
the character set that task directories and JSON fields can safely hold.
Runtime identity validation (numeric vs Jira vs custom) is handled by
``TaskIdentityResolver.is_valid_task_key()``.
"""


@lru_cache(maxsize=16)
def _compiled_pattern(strategy: TaskIdStrategy, custom_pattern: str = "") -> re.Pattern[str]:
    """Compile and cache the regex pattern for a given strategy/custom_pattern pair."""
    return re.compile(_build_pattern(strategy, custom_pattern))


def _build_pattern(strategy: TaskIdStrategy, custom_pattern: str = "") -> str:
    if strategy == "numeric":
        return rf"^{_NUMERIC_PATTERN}$"
    if strategy == "jira":
        return rf"^{_JIRA_PATTERN}$"
    if strategy == "custom":
        _validate_custom_pattern(custom_pattern)
        return rf"^{custom_pattern}$"
    if strategy == "hybrid":
        return rf"^(?:{_NUMERIC_PATTERN}|{_JIRA_PATTERN})$"
    raise ValueError(f"unsupported task id strategy: {strategy}")


def _validate_custom_pattern(pattern: str) -> None:
    if not pattern:
        raise ValueError("custom task id strategy requires a non-empty custom pattern")
    if len(pattern) > _SAFE_CUSTOM_MAX_LEN:
        raise ValueError("custom task id pattern is too long")
    # Keep custom regex within a conservative subset to reduce ReDoS/ambiguity.
    banned_tokens = ("(?=", "(?!", "(?<=", "(?<!", "(?P", "\\1", "\\2", "\\3")
    if any(token in pattern for token in banned_tokens):
        raise ValueError("custom task id pattern contains unsupported advanced regex tokens")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid custom task id pattern: {exc}") from exc


@dataclass(frozen=True)
class TaskIdentityResolver:
    """Validate and extract task keys from branch names."""

    strategy: TaskIdStrategy = "hybrid"
    custom_pattern: str = ""

    @classmethod
    def from_config(cls, cfg) -> "TaskIdentityResolver":
        workflow = getattr(cfg, "workflow", None)
        strategy = getattr(workflow, "task_id_strategy", "hybrid")
        custom_pattern = getattr(workflow, "task_id_custom_pattern", "")
        return cls(strategy=strategy, custom_pattern=custom_pattern)

    @property
    def fullmatch_re(self) -> re.Pattern[str]:
        return _compiled_pattern(self.strategy, self.custom_pattern)

    def is_valid_task_key(self, task_key: str) -> bool:
        if not task_key or len(task_key) > _SAFE_KEY_MAX_LEN:
            return False
        return bool(self.fullmatch_re.fullmatch(task_key))

    def extract_from_branch(self, branch: str, *, branch_prefix: str = "agent") -> str | None:
        prefix = f"{branch_prefix}/"
        if not branch or not branch.startswith(prefix):
            return None
        remainder = branch[len(prefix) :]
        # Support either "<task-key>" or "<task-key>-<short-desc>".
        # Use a prefix match and then validate against the configured strategy.
        for i in range(len(remainder), 0, -1):
            candidate = remainder[:i]
            if self.is_valid_task_key(candidate):
                return candidate
        return None

    def canonical_task_dir(self, task_key: str) -> str:
        if not self.is_valid_task_key(task_key):
            raise ValueError(f"invalid task key: {task_key}")
        return task_key


def extract_task_key_from_branch(branch: str, *, cwd: Path | None = None) -> str | None:
    """Extract task key from an ``agent/<task-key>-*`` branch name."""
    from harness.core.config import HarnessConfig

    try:
        cfg = HarnessConfig.load(cwd or Path.cwd())
        resolver = TaskIdentityResolver.from_config(cfg)
        branch_prefix = cfg.workflow.branch_prefix
    except Exception:
        log.debug("failed to load task identity config; using default resolver", exc_info=True)
        resolver = TaskIdentityResolver()
        branch_prefix = "agent"
    return resolver.extract_from_branch(branch, branch_prefix=branch_prefix)


def extract_task_id_from_branch(branch: str) -> str | None:
    """Backward-compatible alias for task-key extraction.

    Historically this function only supported ``task-NNN``. It now delegates
    to the configured task-key resolver and returns ``None`` for non-matching
    branch names.
    """
    return extract_task_key_from_branch(branch)

