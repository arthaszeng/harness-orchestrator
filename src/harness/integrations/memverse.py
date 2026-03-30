"""Memverse 集成 — disabled by default, failure non-blocking, clear fallback.

设计决策：
  Memverse 的实际 search/add 操作通过 reflector agent 的 MCP 工具间接完成，
  Python 端不直接调用 MCP。因此：
  - NullMemverse 始终安全返回空结果
  - SafeMemverse 包装任何实现，确保异常不阻塞主流程
  - 未来如需 Python 直接调用 MCP，在 SafeMemverse 内实现并保持异常隔离
"""

from __future__ import annotations

import sys
from typing import Protocol, runtime_checkable


@runtime_checkable
class MemverseClient(Protocol):
    def search(self, query: str, domain: str) -> list[str]: ...
    def add(self, text: str, domain: str) -> None: ...
    @property
    def enabled(self) -> bool: ...


class NullMemverse:
    """Memverse 关闭时的空实现"""

    @property
    def enabled(self) -> bool:
        return False

    def search(self, query: str, domain: str) -> list[str]:
        return []

    def add(self, text: str, domain: str) -> None:
        pass


class SafeMemverse:
    """Wraps a MemverseClient to ensure all calls are non-blocking on failure.

    Any exception from the inner client is caught, logged to stderr, and
    silently swallowed so that the main workflow is never interrupted.
    """

    def __init__(self, inner: MemverseClient) -> None:
        self._inner = inner

    @property
    def enabled(self) -> bool:
        return self._inner.enabled

    def search(self, query: str, domain: str) -> list[str]:
        try:
            return self._inner.search(query, domain)
        except Exception as exc:
            sys.stderr.write(f"[harness] memverse search failed (non-blocking): {exc}\n")
            return []

    def add(self, text: str, domain: str) -> None:
        try:
            self._inner.add(text, domain)
        except Exception as exc:
            sys.stderr.write(f"[harness] memverse add failed (non-blocking): {exc}\n")


class _PromptMemverse:
    """Memverse enabled but delegated to agent prompts.

    The reflector agent's prompt includes MCP memverse instructions.
    This class marks memverse as "enabled" so the reflector prompt
    includes the memverse write/search directives, but Python-side
    search/add are no-ops (the agent handles it via MCP tools).
    """

    @property
    def enabled(self) -> bool:
        return True

    def search(self, query: str, domain: str) -> list[str]:
        return []

    def add(self, text: str, domain: str) -> None:
        pass


def create_memverse(
    enabled: bool,
    driver: object | None = None,
) -> MemverseClient:
    """Create a Memverse client.

    - disabled → NullMemverse (zero overhead)
    - enabled  → SafeMemverse(_PromptMemverse()) (non-blocking, prompt-based)
    """
    if not enabled:
        return NullMemverse()
    return SafeMemverse(_PromptMemverse())
