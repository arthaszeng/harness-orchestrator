"""Validate agent definition files stay in sync with code.

Inspired by gstack's skill-validation.test.ts — these are fast static
checks that catch drift between agent definition files and the Python
codebase without running any LLM.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from harness.core.config import KNOWN_MODEL_ROLES
from harness.drivers.resolver import ROLE_AGENT_MAP

_REPO_ROOT = Path(__file__).resolve().parent.parent
_AGENTS_DIR = _REPO_ROOT / "src" / "harness" / "agents"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _codex_agent_files() -> list[Path]:
    d = _AGENTS_DIR / "codex"
    return sorted(d.glob("*.toml")) if d.is_dir() else []


def _cursor_agent_files() -> list[Path]:
    d = _AGENTS_DIR / "cursor"
    return sorted(d.glob("*.md")) if d.is_dir() else []


def _parse_toml_name(path: Path) -> str:
    """Extract the 'name' field from a Codex .toml agent file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^name\s*=\s*"(.+?)"', line)
        if m:
            return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# Registry consistency
# ---------------------------------------------------------------------------

class TestRegistryConsistency:
    """ROLE_AGENT_MAP and KNOWN_MODEL_ROLES must stay aligned."""

    def test_role_agent_map_covers_known_roles(self):
        """Every role in KNOWN_MODEL_ROLES that has an agent should be in ROLE_AGENT_MAP."""
        agent_roles = {
            "planner", "builder", "evaluator",
            "alignment_evaluator", "strategist", "reflector", "advisor",
        }
        for role in agent_roles:
            assert role in ROLE_AGENT_MAP, (
                f"Role '{role}' missing from ROLE_AGENT_MAP"
            )

    def test_role_agent_map_subset_of_known_roles(self):
        """Every role in ROLE_AGENT_MAP should be in KNOWN_MODEL_ROLES."""
        for role in ROLE_AGENT_MAP:
            assert role in KNOWN_MODEL_ROLES, (
                f"ROLE_AGENT_MAP has role '{role}' not in KNOWN_MODEL_ROLES"
            )

    def test_agent_names_follow_convention(self):
        """All agent names should follow the 'harness-<role>' pattern."""
        for role, name in ROLE_AGENT_MAP.items():
            assert name.startswith("harness-"), (
                f"Agent name '{name}' for role '{role}' does not start with 'harness-'"
            )


# ---------------------------------------------------------------------------
# Agent definition file existence
# ---------------------------------------------------------------------------

class TestAgentFileExistence:
    """Every role should have corresponding agent definition files."""

    def test_codex_agents_exist(self):
        codex_dir = _AGENTS_DIR / "codex"
        if not codex_dir.is_dir():
            pytest.skip("agents/codex/ not found")
        files = {f.stem for f in codex_dir.glob("*.toml")}
        roles_needing_codex = {"planner", "evaluator", "strategist", "reflector", "advisor", "alignment_evaluator"}
        for role in roles_needing_codex:
            assert role in files, (
                f"Missing agents/codex/{role}.toml for role '{role}'"
            )

    def test_cursor_agents_exist(self):
        cursor_dir = _AGENTS_DIR / "cursor"
        if not cursor_dir.is_dir():
            pytest.skip("agents/cursor/ not found")
        files = {f.stem for f in cursor_dir.glob("*.md")}
        roles_needing_cursor = {"builder", "reflector"}
        for role in roles_needing_cursor:
            assert role in files, (
                f"Missing agents/cursor/{role}.md for role '{role}'"
            )


# ---------------------------------------------------------------------------
# Agent file content validation
# ---------------------------------------------------------------------------

class TestAgentFileContent:
    """Agent definition files must have correct structure and naming."""

    @pytest.mark.parametrize("path", _codex_agent_files(), ids=lambda p: p.name)
    def test_codex_name_matches_role_map(self, path: Path):
        """Codex .toml 'name' field must match ROLE_AGENT_MAP."""
        role = path.stem
        expected_name = ROLE_AGENT_MAP.get(role)
        if expected_name is None:
            pytest.skip(f"Role '{role}' not in ROLE_AGENT_MAP")
        actual = _parse_toml_name(path)
        assert actual == expected_name, (
            f"{path.name}: name='{actual}' but ROLE_AGENT_MAP expects '{expected_name}'"
        )

    @pytest.mark.parametrize("path", _codex_agent_files(), ids=lambda p: p.name)
    def test_codex_has_developer_instructions(self, path: Path):
        content = path.read_text(encoding="utf-8")
        assert "developer_instructions" in content, (
            f"{path.name} missing developer_instructions field"
        )

    @pytest.mark.parametrize("path", _cursor_agent_files(), ids=lambda p: p.name)
    def test_cursor_has_heading(self, path: Path):
        content = path.read_text(encoding="utf-8")
        assert content.startswith("# "), (
            f"{path.name} should start with a markdown heading"
        )

    @pytest.mark.parametrize("path", _codex_agent_files(), ids=lambda p: p.name)
    def test_codex_has_output_format(self, path: Path):
        """Codex agents should document their expected output format."""
        content = path.read_text(encoding="utf-8")
        content_lower = content.lower()
        has_format = (
            "output format" in content_lower
            or "## verdict" in content_lower
        )
        assert has_format, (
            f"{path.name} missing output format documentation"
        )


# ---------------------------------------------------------------------------
# Install mapping coverage
# ---------------------------------------------------------------------------

class TestInstallMappings:
    """install.py mappings must cover all agent definition files."""

    def test_cursor_install_map_covers_files(self):
        from harness.commands.install import _CURSOR_AGENTS
        cursor_dir = _AGENTS_DIR / "cursor"
        if not cursor_dir.is_dir():
            pytest.skip("agents/cursor/ not found")
        actual_files = {f.name for f in cursor_dir.glob("*.md")}
        mapped_files = set(_CURSOR_AGENTS.keys())
        missing = actual_files - mapped_files
        assert not missing, (
            f"Agent files not in _CURSOR_AGENTS install mapping: {missing}"
        )

    def test_codex_install_map_covers_files(self):
        from harness.commands.install import _CODEX_AGENTS
        codex_dir = _AGENTS_DIR / "codex"
        if not codex_dir.is_dir():
            pytest.skip("agents/codex/ not found")
        actual_files = {f.name for f in codex_dir.glob("*.toml")}
        mapped_files = set(_CODEX_AGENTS.keys())
        missing = actual_files - mapped_files
        assert not missing, (
            f"Agent files not in _CODEX_AGENTS install mapping: {missing}"
        )


# ---------------------------------------------------------------------------
# Localization parity
# ---------------------------------------------------------------------------

class TestLocalizationParity:
    """zh/ subdirectories should mirror the main agent files."""

    def test_codex_zh_parity(self):
        codex_dir = _AGENTS_DIR / "codex"
        zh_dir = codex_dir / "zh"
        if not zh_dir.is_dir():
            pytest.skip("agents/codex/zh/ not found")
        main_files = {f.name for f in codex_dir.glob("*.toml")}
        zh_files = {f.name for f in zh_dir.glob("*.toml")}
        missing = main_files - zh_files
        assert not missing, (
            f"zh/ missing translations for: {missing}"
        )

    def test_cursor_zh_parity(self):
        cursor_dir = _AGENTS_DIR / "cursor"
        zh_dir = cursor_dir / "zh"
        if not zh_dir.is_dir():
            pytest.skip("agents/cursor/zh/ not found")
        main_files = {f.name for f in cursor_dir.glob("*.md")}
        zh_files = {f.name for f in zh_dir.glob("*.md")}
        missing = main_files - zh_files
        assert not missing, (
            f"zh/ missing translations for: {missing}"
        )
