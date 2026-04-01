"""Role constants for native harness.

Exports used by native review validation (``NATIVE_REVIEW_ROLES``),
skill generation templates, and scoring dimensions.
``ALL_ROLES`` is empty in native-only mode (no routed roles).
"""

from __future__ import annotations

# No routed roles in native-only mode.
ALL_ROLES: frozenset[str] = frozenset()

# Default runtime label for registry/events/tracker (cursor-native only).
DEFAULT_RUNTIME: str = "cursor"

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
