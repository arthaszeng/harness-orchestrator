"""Project configuration model — Pydantic-based."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from pydantic import BaseModel, Field

from harness.core.roles import ALL_ROLES

KNOWN_MODEL_ROLES: frozenset[str] = ALL_ROLES


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
    advisor: str = ""


class DriversConfig(BaseModel):
    default: str = "auto"  # auto / cursor / codex
    roles: DriversRolesConfig = Field(default_factory=DriversRolesConfig)


class RoleModelConfig(BaseModel):
    """单个角色的模型配置，支持模型和温度覆盖。"""
    model: str | None = None
    temperature: float | None = None


class ModelsConfig(BaseModel):
    default: str = ""
    driver_defaults: dict[str, str] = Field(default_factory=dict)
    role_overrides: dict[str, str] = Field(default_factory=dict)
    role_configs: dict[str, RoleModelConfig] = Field(default_factory=dict)


class NativeModeConfig(BaseModel):
    """Cursor-native mode settings — only used when workflow.mode = cursor-native."""
    adversarial_model: str = "gpt-4.1"
    adversarial_mechanism: Literal["subagent", "cli", "auto"] = "auto"
    review_gate: Literal["eng", "advisory"] = "eng"
    retro_window_days: int = Field(default=14, ge=1, le=365)
    hooks_pre_build: str = ""
    hooks_post_eval: str = ""
    hooks_pre_ship: str = ""


class WorkflowConfig(BaseModel):
    mode: str = "orchestrator"  # orchestrator / cursor-native
    profile: str = "standard"  # lite / standard / autonomous
    max_iterations: int = 3
    pass_threshold: float = 3.5
    auto_merge: bool = True
    branch_prefix: str = "agent"
    trunk_branch: str = "main"
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
    native: NativeModeConfig = Field(default_factory=NativeModeConfig)
    autonomous: AutonomousConfig = Field(default_factory=AutonomousConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)

    # Runtime-injected, excluded from serialization
    project_root: Path = Field(default_factory=Path.cwd, exclude=True)

    @classmethod
    def load(cls, project_root: Path | None = None) -> HarnessConfig:
        """Load config from .agents/config.toml with cascading merge.

        Priority chain (highest wins):
            env vars (HARNESS_*) → project (.agents/) → global (~/.harness/) → defaults
        """
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

        # Environment variable overrides (highest priority)
        env_data = _env_overrides()
        if env_data:
            data = _deep_merge(data, env_data)

        cfg = cls.model_validate(data)
        cfg.project_root = root
        return cfg


def resolve_model(role: str, driver_name: str, models: ModelsConfig) -> str:
    """解析角色对应的模型，按以下优先级 fallback:

    1. ``role_overrides[role]``  — 角色级精确覆盖
    2. ``role_configs[role].model`` — 角色扩展配置中的模型
    3. ``driver_defaults[driver]`` — 驱动级批量配置
    4. ``default`` — 全局默认

    返回空字符串表示"使用 IDE/CLI 自身默认模型"，driver 侧仅在非空时
    附加 ``--model``，因此零配置不改变现有运行路径。
    """
    if role in models.role_overrides:
        return models.role_overrides[role]
    rc = models.role_configs.get(role)
    if rc and rc.model is not None:
        return rc.model
    if driver_name in models.driver_defaults:
        return models.driver_defaults[driver_name]
    return models.default


def resolve_role_temperature(role: str, models: ModelsConfig) -> float | None:
    """解析角色温度配置，无配置时返回 None。"""
    rc = models.role_configs.get(role)
    return rc.temperature if rc else None


def _env_overrides() -> dict[str, Any]:
    """Extract HARNESS_* environment variables as config overrides.

    Mapping convention:
        HARNESS_CI_COMMAND        → {"ci": {"command": "..."}}
        HARNESS_WORKFLOW_PROFILE  → {"workflow": {"profile": "..."}}
        HARNESS_MODELS_DEFAULT    → {"models": {"default": "..."}}

    Only non-empty values are included. Nested keys use underscore separation
    with the first segment as the section name.
    """
    PREFIX = "HARNESS_"
    overrides: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith(PREFIX) or not value:
            continue
        parts = key[len(PREFIX) :].lower().split("_", 1)
        if len(parts) == 2:
            section, field = parts
            overrides.setdefault(section, {})[field] = value
        elif len(parts) == 1:
            overrides[parts[0]] = value
    return overrides


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge: override wins over base."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
