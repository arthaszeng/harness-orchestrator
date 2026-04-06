"""config.py 单元测试"""

import warnings as _warnings
from pathlib import Path

import pytest

from harness.core.config import (
    HarnessConfig,
    HarnessConfigError,
    ModelsConfig,
    RoleModelConfig,
    _deep_merge,
)


def test_default_config():
    cfg = HarnessConfig()
    assert cfg.workflow.max_iterations == 3
    assert cfg.workflow.pass_threshold == 7.0
    assert cfg.workflow.task_id_strategy == "hybrid"
    assert cfg.workflow.task_id_custom_pattern == ""
    assert not hasattr(cfg, "drivers")
    assert cfg.integrations.memverse.enabled is False
    assert cfg.integrations.memverse.domain_prefix == ""


def test_load_from_toml(tmp_path: Path):
    agents_dir = tmp_path / ".harness-flow"
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
    agents_dir = tmp_path / ".harness-flow"
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
    agents_dir = tmp_path / ".harness-flow"
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
    agents_dir = tmp_path / ".harness-flow"
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
    agents_dir = tmp_path / ".harness-flow"
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


class TestHarnessConfigError:
    """D1: config loading wraps TOML and I/O errors."""

    def test_corrupt_toml_raises_config_error(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text("{invalid toml!!", encoding="utf-8")

        with pytest.raises(HarnessConfigError, match="Invalid TOML"):
            HarnessConfig.load(tmp_path)

    def test_config_error_includes_file_path(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text("[[broken", encoding="utf-8")

        with pytest.raises(HarnessConfigError) as exc_info:
            HarnessConfig.load(tmp_path)
        assert "config.toml" in str(exc_info.value)

    def test_non_utf8_config_raises_config_error(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_bytes(b"\xff\xfe[project]\nname = 'x'\n")

        with pytest.raises(HarnessConfigError, match="Cannot read"):
            HarnessConfig.load(tmp_path)

    def test_global_config_corrupt_warns_and_continues(self, tmp_path: Path, monkeypatch):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir()
        (agents_dir / "config.toml").write_text(
            '[project]\nname = "proj"\n', encoding="utf-8",
        )

        fake_home = tmp_path / "fakehome"
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
        global_dir = fake_home / ".harness"
        global_dir.mkdir(parents=True)
        (global_dir / "config.toml").write_text("{broken!", encoding="utf-8")

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            cfg = HarnessConfig.load(tmp_path)

        assert cfg.project.name == "proj"
        assert any("corrupt global config" in str(w.message).lower() for w in caught)

    def test_missing_config_uses_defaults(self, tmp_path: Path):
        cfg = HarnessConfig.load(tmp_path)
        assert cfg.workflow.max_iterations == 3
