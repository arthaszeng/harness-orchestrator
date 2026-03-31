"""Project configuration model — Pydantic-based."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    name: str = ""
    description: str = ""
    lang: str = "en"  # en / zh


class CIConfig(BaseModel):
    command: str = "make test"
    architecture_check: str = ""
    frontend_dir: str = ""


class DriversRolesConfig(BaseModel):
    planner: str = ""
    builder: str = ""
    evaluator: str = ""
    alignment_evaluator: str = ""
    strategist: str = ""
    reflector: str = ""


class DriversConfig(BaseModel):
    default: str = "auto"  # auto / cursor / codex
    roles: DriversRolesConfig = Field(default_factory=DriversRolesConfig)


class ModelsConfig(BaseModel):
    default: str = ""


class WorkflowConfig(BaseModel):
    profile: str = "standard"  # lite / standard / autonomous
    max_iterations: int = 3
    pass_threshold: float = 3.5
    auto_merge: bool = True
    branch_prefix: str = "agent"
    dual_evaluation: bool = False


class AutonomousConfig(BaseModel):
    enabled: bool = True
    max_tasks_per_session: int = 10
    progress_report_interval: int = 5
    consecutive_block_limit: int = 2


class MemverseConfig(BaseModel):
    enabled: bool = False
    driver: str = "auto"  # auto / cursor / codex
    domain_prefix: str = ""


class IntegrationsConfig(BaseModel):
    memverse: MemverseConfig = Field(default_factory=MemverseConfig)


class HarnessConfig(BaseModel):
    """Complete harness configuration."""
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    ci: CIConfig = Field(default_factory=CIConfig)
    drivers: DriversConfig = Field(default_factory=DriversConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    autonomous: AutonomousConfig = Field(default_factory=AutonomousConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)

    # Runtime-injected, excluded from serialization
    project_root: Path = Field(default_factory=Path.cwd, exclude=True)

    @classmethod
    def load(cls, project_root: Path | None = None) -> HarnessConfig:
        """Load config from .agents/config.toml with cascading merge."""
        root = project_root or Path.cwd()
        config_path = root / ".agents" / "config.toml"

        data: dict[str, Any] = {}
        if config_path.exists():
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))

        # Global config fallback
        global_path = Path.home() / ".harness" / "config.toml"
        if global_path.exists():
            global_data = tomllib.loads(global_path.read_text(encoding="utf-8"))
            # Project config takes priority over global
            data = _deep_merge(global_data, data)

        cfg = cls.model_validate(data)
        cfg.project_root = root
        return cfg


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge: override wins over base."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
