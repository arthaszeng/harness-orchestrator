"""角色 → 驱动路由"""

from __future__ import annotations

import sys

from harness.core.config import HarnessConfig
from harness.drivers.base import AgentDriver
from harness.drivers.codex import CodexDriver
from harness.drivers.cursor import CursorDriver

# 角色 → agent 名称映射
ROLE_AGENT_MAP = {
    "planner": "harness-planner",
    "builder": "harness-builder",
    "evaluator": "harness-evaluator",
    "alignment_evaluator": "harness-alignment-evaluator",
    "strategist": "harness-strategist",
    "reflector": "harness-reflector",
    "advisor": "harness-advisor",
}


class DriverResolver:
    """根据配置为每个角色选择合适的驱动"""

    def __init__(self, config: HarnessConfig) -> None:
        self._config = config
        self._cursor = CursorDriver()
        self._codex = CodexDriver()
        self._cursor_ok = self._cursor.is_available()
        self._codex_ok = self._codex.is_available()

        self._probe_results: dict[str, object] = {}
        self._run_probes()

    def _run_probes(self) -> None:
        """Probe available drivers at startup and emit warnings."""
        for label, driver, ok in [
            ("codex", self._codex, self._codex_ok),
            ("cursor", self._cursor, self._cursor_ok),
        ]:
            if not ok:
                continue
            probe = driver.probe()
            self._probe_results[label] = probe
            for w in probe.warnings:
                sys.stderr.write(f"[harness] warning ({label}): {w}\n")

    def resolve(self, role: str) -> AgentDriver:
        """为指定角色返回合适的驱动"""
        mode = self._config.drivers.default

        # 显式配置的角色覆盖
        role_override = getattr(self._config.drivers.roles, role, "")
        if role_override:
            if role_override == "cursor" and self._cursor_ok:
                return self._cursor
            if role_override == "codex" and self._codex_ok:
                return self._codex

        # 模式级路由
        if mode == "cursor":
            return self._cursor
        if mode == "codex":
            return self._codex

        # auto 模式: Builder→Cursor, 其余→Codex（如果两者都可用）
        if self._cursor_ok and self._codex_ok:
            return self._cursor if role == "builder" else self._codex
        if self._cursor_ok:
            return self._cursor
        if self._codex_ok:
            return self._codex

        raise RuntimeError("未检测到 Cursor 或 Codex CLI")

    def agent_name(self, role: str) -> str:
        """返回角色对应的 agent 名称"""
        return ROLE_AGENT_MAP.get(role, role)

    def get_driver_by_name(self, name: str) -> AgentDriver | None:
        """按驱动名（cursor / codex）直接获取，不存在或不可用返回 None"""
        if name == "cursor" and self._cursor_ok:
            return self._cursor
        if name == "codex" and self._codex_ok:
            return self._codex
        return None

    def first_available_driver(self) -> AgentDriver | None:
        """返回第一个可用的驱动"""
        if self._codex_ok:
            return self._codex
        if self._cursor_ok:
            return self._cursor
        return None

    @property
    def available_drivers(self) -> dict[str, bool]:
        return {"cursor": self._cursor_ok, "codex": self._codex_ok}
