"""Role constants for native harness.

Exports used by config validation, skill generation, and templates.
Orchestrator role registry has been removed; ``ALL_ROLES`` is empty for
backward compatibility with ``KNOWN_MODEL_ROLES`` in config.
"""

from __future__ import annotations

# No orchestrator-routed roles in native-only mode.
ALL_ROLES: frozenset[str] = frozenset()

# Cursor-native five review subagents (template / native.role_models keys).
NATIVE_REVIEW_ROLES: frozenset[str] = frozenset(
    ("architect", "product_owner", "engineer", "qa", "project_manager")
)

SCORING_DIMENSIONS: tuple[str, ...] = (
    "completeness",
    "quality",
    "regression",
    "design",
)
