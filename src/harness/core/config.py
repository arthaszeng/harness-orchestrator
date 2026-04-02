"""Project configuration model — Pydantic-based."""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Any, Literal

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harness.core.model_selection import validate_model_name
from harness.core.roles import NATIVE_REVIEW_ROLES


class ProjectConfig(BaseModel):
    name: str = ""
    description: str = ""
    lang: str = "en"  # en / zh


class CIConfig(BaseModel):
    command: str = "make test"
    architecture_check: str = ""
    frontend_dir: str = ""


class RoleModelConfig(BaseModel):
    """单个角色的模型配置，支持模型和温度覆盖。"""
    model: str | None = None
    temperature: float | None = None


class ModelsConfig(BaseModel):
    default: str = ""
    role_overrides: dict[str, str] = Field(default_factory=dict)
    role_configs: dict[str, RoleModelConfig] = Field(default_factory=dict)


class NativeModeConfig(BaseModel):
    """Native IDE workflow settings (eval, ship, skills)."""
    evaluator_model: str = "inherit"
    adversarial_mechanism: Literal["subagent", "cli", "auto"] = "auto"
    review_gate: Literal["eng", "advisory"] = "eng"
    plan_review_gate: Literal["human", "ai", "auto"] = "auto"
    retro_window_days: int = Field(default=14, ge=1, le=365)
    hooks_pre_build: str = ""
    hooks_post_eval: str = ""
    hooks_pre_ship: str = ""
    gate_full_review_min: int = Field(
        default=5, ge=1,
        description="Escalation score threshold for FULL REVIEW (human must review).",
    )
    gate_summary_confirm_min: int = Field(
        default=3, ge=1,
        description="Escalation score threshold for SUMMARY CONFIRM (brief confirmation).",
    )
    role_models: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-role model overrides for the 5 review roles. "
            'Keys: architect, product_owner, engineer, qa, project_manager. '
            'Empty string or absent = use IDE default model.'
        ),
    )
    rule_activation: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-rule activation mode. "
            'Keys: rule template names (e.g. harness-trust-boundary). '
            'Values: "always" (default), "phase_match", "disabled".'
        ),
    )

    _VALID_RULE_NAMES: frozenset[str] = frozenset({
        "harness-trust-boundary",
        "harness-workflow",
        "harness-fix-first",
        "harness-safety-guardrails",
    })
    _VALID_ACTIVATIONS: frozenset[str] = frozenset({"always", "phase_match", "disabled"})

    @model_validator(mode="after")
    def _validate_native_config(self) -> "NativeModeConfig":
        if self.gate_summary_confirm_min >= self.gate_full_review_min:
            raise ValueError(
                f"gate_summary_confirm_min ({self.gate_summary_confirm_min}) "
                f"must be less than gate_full_review_min ({self.gate_full_review_min})"
            )
        unknown = set(self.role_models) - NATIVE_REVIEW_ROLES
        if unknown:
            warnings.warn(
                f"Unknown native.role_models keys: {sorted(unknown)}. "
                f"Valid keys: {sorted(NATIVE_REVIEW_ROLES)}",
                UserWarning,
                stacklevel=2,
            )
        if not validate_model_name(self.evaluator_model):
            warnings.warn(
                "Invalid native.evaluator_model; generated review agents will fall back "
                "to the IDE default model.",
                UserWarning,
                stacklevel=2,
            )
        for role_name, model in self.role_models.items():
            if model and not validate_model_name(model):
                warnings.warn(
                    f"Invalid native.role_models.{role_name}; generated review agents "
                    "will fall back to the IDE default model for that role.",
                    UserWarning,
                    stacklevel=2,
                )
        unknown_rules = set(self.rule_activation) - self._VALID_RULE_NAMES
        if unknown_rules:
            warnings.warn(
                f"Unknown native.rule_activation keys: {sorted(unknown_rules)}. "
                f"Valid keys: {sorted(self._VALID_RULE_NAMES)}",
                UserWarning,
                stacklevel=2,
            )
        for rule_name, activation in self.rule_activation.items():
            if activation not in self._VALID_ACTIVATIONS:
                warnings.warn(
                    f"Invalid native.rule_activation.{rule_name} value '{activation}'. "
                    f"Valid values: {sorted(self._VALID_ACTIVATIONS)}",
                    UserWarning,
                    stacklevel=2,
                )
        return self


class WorkflowConfig(BaseModel):
    max_iterations: int = 3
    pass_threshold: float = 7.0
    auto_merge: bool = True
    branch_prefix: str = "agent"
    trunk_branch: str = "main"


class MemverseConfig(BaseModel):
    enabled: bool = False
    domain_prefix: str = ""


class IntegrationsConfig(BaseModel):
    memverse: MemverseConfig = Field(default_factory=MemverseConfig)


class HarnessConfig(BaseModel):
    """Complete harness configuration."""
    model_config = ConfigDict(extra="ignore")

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    ci: CIConfig = Field(default_factory=CIConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    native: NativeModeConfig = Field(default_factory=NativeModeConfig)
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

        native_data = data.get("native")
        if (
            isinstance(native_data, dict)
            and "evaluator_model" not in native_data
            and "adversarial_model" in native_data
        ):
            native_data["evaluator_model"] = native_data["adversarial_model"]

        cfg = cls.model_validate(data)
        cfg.project_root = root
        return cfg


def _env_overrides() -> dict[str, Any]:
    """Extract HARNESS_* environment variables as config overrides.

    Mapping convention:
        HARNESS_CI_COMMAND        → {"ci": {"command": "..."}}
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
