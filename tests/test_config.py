"""config.py 单元测试"""

from pathlib import Path

from harness.core.config import (
    HarnessConfig,
    ModelsConfig,
    RoleModelConfig,
    _deep_merge,
)


def test_default_config():
    cfg = HarnessConfig()
    assert cfg.workflow.max_iterations == 3
    assert cfg.workflow.pass_threshold == 7.0
    assert not hasattr(cfg, "drivers")
    assert cfg.integrations.memverse.enabled is False
    assert cfg.integrations.memverse.domain_prefix == ""


def test_load_from_toml(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test-proj"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    assert cfg.project.name == "test-proj"
    assert cfg.ci.command == "pytest"
    assert cfg.workflow.max_iterations == 3  # 默认值


def test_deep_merge():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}, "e": 5}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 99, "d": 3}, "e": 5}


def test_models_config_from_toml(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[models]\ndefault = "gpt-4o"\n\n'
        '[models.role_overrides]\nplanner = "o3-pro"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    assert cfg.models.default == "gpt-4o"
    assert cfg.models.role_overrides == {"planner": "o3-pro"}


def test_legacy_drivers_section_ignored(tmp_path: Path):
    """[drivers] and nested keys are ignored (extra='ignore') without error."""
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[drivers]\ndefault = "codex"\n\n[drivers.roles]\nplanner = "x"\n'
        '[project]\nname = "legacy"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    assert cfg.project.name == "legacy"


def test_workflow_strips_removed_fields_from_toml(tmp_path: Path):
    """Removed workflow fields in TOML must not break load (ignored as extra)."""
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[workflow]\nmode = "orchestrator"\nprofile = "standard"\n'
        'dual_evaluation = true\nmax_iterations = 5\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    assert cfg.workflow.max_iterations == 5
    assert cfg.workflow.pass_threshold == 7.0


def test_native_adversarial_model_aliases_to_evaluator_model(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[native]\nadversarial_model = "gpt-4.1"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    assert cfg.native.evaluator_model == "gpt-4.1"


def test_role_model_config_roundtrip():
    m = RoleModelConfig(model="m", temperature=0.5)
    assert m.model == "m"
    assert m.temperature == 0.5


def test_models_empty():
    models = ModelsConfig()
    assert models.default == ""
    assert models.role_overrides == {}
    assert models.role_configs == {}
