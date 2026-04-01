"""配置合并链环境变量覆盖测试"""

import os
from pathlib import Path

from harness.core.config import HarnessConfig, _env_overrides


def test_env_overrides_empty_when_no_vars(monkeypatch):
    for key in list(os.environ):
        if key.startswith("HARNESS_"):
            monkeypatch.delenv(key, raising=False)
    result = _env_overrides()
    assert result == {}


def test_env_overrides_parses_two_segment(monkeypatch):
    monkeypatch.setenv("HARNESS_CI_COMMAND", "pytest -v")
    monkeypatch.setenv("HARNESS_WORKFLOW_PROFILE", "lite")
    result = _env_overrides()
    assert result["ci"]["command"] == "pytest -v"
    assert result["workflow"]["profile"] == "lite"


def test_env_overrides_ignores_empty_values(monkeypatch):
    monkeypatch.setenv("HARNESS_CI_COMMAND", "")
    result = _env_overrides()
    assert "ci" not in result


def test_env_overrides_single_segment(monkeypatch):
    monkeypatch.setenv("HARNESS_DEBUG", "true")
    result = _env_overrides()
    assert result.get("debug") == "true"


def test_load_with_env_override(tmp_path: Path, monkeypatch):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "fromfile"\n[ci]\ncommand = "make test"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESS_CI_COMMAND", "pytest -xvs")
    cfg = HarnessConfig.load(tmp_path)
    assert cfg.ci.command == "pytest -xvs"
    assert cfg.project.name == "fromfile"


def test_load_without_env_is_unchanged(tmp_path: Path, monkeypatch):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[ci]\ncommand = "make test"\n',
        encoding="utf-8",
    )
    for key in list(os.environ):
        if key.startswith("HARNESS_"):
            monkeypatch.delenv(key, raising=False)
    cfg = HarnessConfig.load(tmp_path)
    assert cfg.ci.command == "make test"
