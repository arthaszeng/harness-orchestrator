"""Role registry — single source of truth for all agent roles.

Dependency graph:
    roles.py ──> config.py      (KNOWN_MODEL_ROLES validation, NATIVE_REVIEW_ROLES)
             ──> resolver.py    (ROLE_AGENT_MAP routing)
             ──> install.py     (agent file mapping)
             ──> skill_gen.py   (NATIVE_REVIEW_ROLES → template context)
             ──> workflow.py    (phase orchestration)
             ──> tests          (agent definition validation)

Zero side effects. Safe to import from build scripts, tests, and runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkflowPhase(Enum):
    PLANNING = "planning"
    CONTRACTED = "contracted"
    BUILDING = "building"
    EVALUATING = "evaluating"
    DONE = "done"
    BLOCKED = "blocked"


class RoleCapability(Enum):
    READONLY = "readonly"
    READWRITE = "readwrite"


@dataclass(frozen=True)
class RoleDescriptor:
    name: str
    agent_name: str
    capability: RoleCapability
    description: str
    phases: tuple[WorkflowPhase, ...]
    concurrency_safe: bool = False
    max_retries: int = 1


# Default values for role properties — fail-closed (conservative)
_ROLE_DEFAULTS = {
    "concurrency_safe": False,
    "max_retries": 1,
}


def build_role(
    name: str,
    agent_name: str,
    capability: RoleCapability,
    description: str,
    phases: tuple[WorkflowPhase, ...],
    *,
    concurrency_safe: bool | None = None,
    max_retries: int | None = None,
) -> RoleDescriptor:
    """Factory for RoleDescriptor with fail-closed defaults.

    Inspired by Claude Code's buildTool() pattern: callers only override
    fields they care about; everything else gets a safe default.
    """
    return RoleDescriptor(
        name=name,
        agent_name=agent_name,
        capability=capability,
        description=description,
        phases=phases,
        concurrency_safe=concurrency_safe
        if concurrency_safe is not None
        else _ROLE_DEFAULTS["concurrency_safe"],
        max_retries=max_retries
        if max_retries is not None
        else _ROLE_DEFAULTS["max_retries"],
    )


ROLE_REGISTRY: dict[str, RoleDescriptor] = {
    "planner": build_role(
        name="planner",
        agent_name="harness-planner",
        capability=RoleCapability.READONLY,
        description="Analyzes requirements and produces spec + contract",
        phases=(WorkflowPhase.PLANNING,),
    ),
    "builder": build_role(
        name="builder",
        agent_name="harness-builder",
        capability=RoleCapability.READWRITE,
        description="Implements contract deliverables",
        phases=(WorkflowPhase.BUILDING,),
    ),
    "evaluator": build_role(
        name="evaluator",
        agent_name="harness-evaluator",
        capability=RoleCapability.READONLY,
        description="Reviews builder output and scores on four dimensions",
        phases=(WorkflowPhase.EVALUATING,),
        concurrency_safe=True,
    ),
    "alignment_evaluator": build_role(
        name="alignment_evaluator",
        agent_name="harness-alignment-evaluator",
        capability=RoleCapability.READONLY,
        description="Checks implementation alignment with original requirement",
        phases=(WorkflowPhase.EVALUATING,),
        concurrency_safe=True,
    ),
    "strategist": build_role(
        name="strategist",
        agent_name="harness-strategist",
        capability=RoleCapability.READONLY,
        description="Decides the next task in autonomous mode",
        phases=(),
    ),
    "reflector": build_role(
        name="reflector",
        agent_name="harness-reflector",
        capability=RoleCapability.READONLY,
        description="Summarizes progress and spots patterns",
        phases=(),
    ),
    "advisor": build_role(
        name="advisor",
        agent_name="harness-advisor",
        capability=RoleCapability.READONLY,
        description="Expands user input into structured vision",
        phases=(),
    ),
}

ALL_ROLES: frozenset[str] = frozenset(ROLE_REGISTRY.keys())
ALL_AGENT_NAMES: frozenset[str] = frozenset(
    r.agent_name for r in ROLE_REGISTRY.values()
)

# Cursor-native 5-role review subagents (template-only, not orchestrator-routed).
# Used by NativeModeConfig.role_models validation and skill_gen.py template context.
NATIVE_REVIEW_ROLES: frozenset[str] = frozenset(
    ("architect", "product_owner", "engineer", "qa", "project_manager")
)

SCORING_DIMENSIONS: tuple[str, ...] = (
    "completeness",
    "quality",
    "regression",
    "design",
)

EVALUATION_VERDICTS: frozenset[str] = frozenset({"PASS", "ITERATE", "CI_FAIL"})
ALIGNMENT_VERDICTS: frozenset[str] = frozenset({"ALIGNED", "MISALIGNED", "CONTRACT_ISSUE"})


def get_role(name: str) -> RoleDescriptor:
    """Look up a role descriptor; raises KeyError if unknown."""
    return ROLE_REGISTRY[name]


def get_agent_name(role: str) -> str:
    """Return the agent name for a role."""
    return ROLE_REGISTRY[role].agent_name


# ---------------------------------------------------------------------------
# Load-time consistency checks (fail fast on import if registry drifts)
# ---------------------------------------------------------------------------

def _validate_registry() -> None:
    """Cross-check the registry for internal consistency."""
    names = set()
    agent_names = set()
    for role, desc in ROLE_REGISTRY.items():
        if role != desc.name:
            raise RuntimeError(
                f"ROLE_REGISTRY key '{role}' != descriptor name '{desc.name}'"
            )
        if desc.agent_name in agent_names:
            raise RuntimeError(
                f"Duplicate agent_name '{desc.agent_name}' in ROLE_REGISTRY"
            )
        if not desc.agent_name.startswith("harness-"):
            raise RuntimeError(
                f"Agent name '{desc.agent_name}' does not follow 'harness-' convention"
            )
        names.add(role)
        agent_names.add(desc.agent_name)


_validate_registry()
