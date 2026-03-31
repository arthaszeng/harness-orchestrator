"""Role → driver routing."""

from __future__ import annotations

import sys

from harness.core.config import HarnessConfig
from harness.drivers.base import AgentDriver
from harness.drivers.codex import CodexDriver
from harness.drivers.cursor import CursorDriver

# Role → agent name
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
    """Pick a driver per role from config and availability."""

    def __init__(self, config: HarnessConfig) -> None:
        self._config = config
        self._cursor = CursorDriver()
        self._codex = CodexDriver()

        self._probe_results: dict[str, object] = {}
        self._cursor_ok, self._codex_ok = self._run_probes()

    def _run_probes(self) -> tuple[bool, bool]:
        """Probe drivers at startup; return (cursor_ok, codex_ok) based on functional checks."""
        cursor_ok = False
        codex_ok = False
        for label, driver, binary_found in [
            ("codex", self._codex, self._codex.is_available()),
            ("cursor", self._cursor, self._cursor.is_available()),
        ]:
            if not binary_found:
                continue
            probe = driver.probe()
            self._probe_results[label] = probe
            for w in probe.warnings:
                sys.stderr.write(f"[harness] warning ({label}): {w}\n")
            if label == "cursor":
                cursor_ok = probe.available
            else:
                codex_ok = probe.available
        return cursor_ok, codex_ok

    def resolve(self, role: str) -> AgentDriver:
        """Return the driver for the given role."""
        mode = self._config.drivers.default

        # Per-role override
        role_override = getattr(self._config.drivers.roles, role, "")
        if role_override:
            if role_override == "cursor" and self._cursor_ok:
                return self._cursor
            if role_override == "codex" and self._codex_ok:
                return self._codex

        # Mode-level routing
        if mode == "cursor":
            return self._cursor
        if mode == "codex":
            return self._codex

        # auto: builder → Cursor if both exist; otherwise Codex
        if self._cursor_ok and self._codex_ok:
            return self._cursor if role == "builder" else self._codex
        if self._cursor_ok:
            return self._cursor
        if self._codex_ok:
            return self._codex

        raise RuntimeError("Neither Cursor nor Codex CLI detected")

    def agent_name(self, role: str) -> str:
        """Agent name for a role."""
        return ROLE_AGENT_MAP.get(role, role)

    def get_driver_by_name(self, name: str) -> AgentDriver | None:
        """Resolve by driver name (cursor / codex); None if missing or unavailable."""
        if name == "cursor" and self._cursor_ok:
            return self._cursor
        if name == "codex" and self._codex_ok:
            return self._codex
        return None

    def first_available_driver(self) -> AgentDriver | None:
        """First available driver (codex preferred, then cursor)."""
        if self._codex_ok:
            return self._codex
        if self._cursor_ok:
            return self._cursor
        return None

    @property
    def available_drivers(self) -> dict[str, bool]:
        return {"cursor": self._cursor_ok, "codex": self._codex_ok}
