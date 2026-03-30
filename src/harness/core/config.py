"""项目配置模型 — 基于 Pydantic"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    name: str = ""
    description: str = ""


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
    driver: str = "auto"  # auto / cursor / codex — 跟随 drivers.default 或独立指定
    domain_prefix: str = ""


class IntegrationsConfig(BaseModel):
    memverse: MemverseConfig = Field(default_factory=MemverseConfig)


class HarnessConfig(BaseModel):
    """harness 完整配置"""
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    ci: CIConfig = Field(default_factory=CIConfig)
    drivers: DriversConfig = Field(default_factory=DriversConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    autonomous: AutonomousConfig = Field(default_factory=AutonomousConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)

    # 运行时注入，不序列化
    project_root: Path = Field(default_factory=Path.cwd, exclude=True)

    @classmethod
    def load(cls, project_root: Path | None = None) -> HarnessConfig:
        """从 .agents/config.toml 加载配置，逐级合并"""
        root = project_root or Path.cwd()
        config_path = root / ".agents" / "config.toml"

        data: dict[str, Any] = {}
        if config_path.exists():
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))

        # 全局配置兜底
        global_path = Path.home() / ".harness" / "config.toml"
        if global_path.exists():
            global_data = tomllib.loads(global_path.read_text(encoding="utf-8"))
            # 项目配置优先，全局兜底
            data = _deep_merge(global_data, data)

        cfg = cls.model_validate(data)
        cfg.project_root = root
        return cfg


def _deep_merge(base: dict, override: dict) -> dict:
    """深合并：override 覆盖 base"""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
