"""Gate threshold configuration and rendering tests."""

from pathlib import Path

import pydantic
import pytest

from harness.core.config import HarnessConfig, NativeModeConfig
from harness.native.skill_gen import _build_full_context, generate_native_artifacts


# ── config validation ──────────────────────────────────────────


def test_gate_thresholds_default():
    cfg = NativeModeConfig()
    assert cfg.gate_full_review_min == 5
    assert cfg.gate_summary_confirm_min == 3


def test_gate_thresholds_custom():
    cfg = NativeModeConfig(gate_full_review_min=7, gate_summary_confirm_min=4)
    assert cfg.gate_full_review_min == 7
    assert cfg.gate_summary_confirm_min == 4


def test_gate_thresholds_rejects_invalid_order():
    with pytest.raises(pydantic.ValidationError, match="gate_summary_confirm_min"):
        NativeModeConfig(gate_full_review_min=3, gate_summary_confirm_min=5)


def test_gate_thresholds_rejects_equal():
    with pytest.raises(pydantic.ValidationError, match="gate_summary_confirm_min"):
        NativeModeConfig(gate_full_review_min=5, gate_summary_confirm_min=5)


def test_gate_thresholds_from_toml(tmp_path: Path):
    agents_dir = tmp_path / ".harness-flow"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n'
        '[native]\ngate_full_review_min = 8\ngate_summary_confirm_min = 4\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    assert cfg.native.gate_full_review_min == 8
    assert cfg.native.gate_summary_confirm_min == 4


def test_harness_config_default_gate_thresholds():
    cfg = HarnessConfig()
    assert cfg.native.gate_full_review_min == 5
    assert cfg.native.gate_summary_confirm_min == 3


# ── template context ───────────────────────────────────────────


def test_build_context_has_gate_thresholds(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_full_context(cfg)
    assert "gate_full_review_min" in ctx
    assert "gate_summary_confirm_min" in ctx
    assert ctx["gate_full_review_min"] == "5"
    assert ctx["gate_summary_confirm_min"] == "3"


def test_build_context_gate_thresholds_custom(tmp_path: Path):
    cfg = HarnessConfig(native=NativeModeConfig(gate_full_review_min=8, gate_summary_confirm_min=4))
    cfg.project_root = tmp_path
    ctx = _build_full_context(cfg)
    assert ctx["gate_full_review_min"] == "8"
    assert ctx["gate_summary_confirm_min"] == "4"


# ── rendered artifacts ─────────────────────────────────────────


def _make_cfg(tmp_path: Path) -> HarnessConfig:
    agents_dir = tmp_path / ".harness-flow"
    agents_dir.mkdir(exist_ok=True)
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )
    return HarnessConfig.load(tmp_path)


def test_role_agents_have_strictly_prohibited(tmp_path: Path):
    """Each role agent contains a Strictly Prohibited section."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    for name in ("harness-architect", "harness-product-owner", "harness-engineer",
                 "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "Strictly Prohibited" in content, f"{name} missing Strictly Prohibited section"
        assert "CROSS-ROLE" in content, f"{name} missing CROSS-ROLE escape hatch"


def test_synthesis_has_out_of_scope_filtering(tmp_path: Path):
    """Plan and code review synthesis sections contain out-of-scope filtering rules."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    skills_base = tmp_path / ".cursor" / "skills" / "harness"
    plan_skill = (skills_base / "harness-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "OUT-OF-SCOPE" in plan_skill
    assert "CROSS-ROLE" in plan_skill
    assert "Must NOT report" in plan_skill

    ship_skill = (skills_base / "harness-ship" / "SKILL.md").read_text(encoding="utf-8")
    assert "OUT-OF-SCOPE" in ship_skill
    assert "CROSS-ROLE" in ship_skill


def test_review_gate_uses_config_thresholds(tmp_path: Path):
    """Review gate uses parameterized thresholds from config, not hardcoded."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan_skill.read_text(encoding="utf-8")
    assert "Score >= 5" in content
    assert "Score 3\u20134" in content
    assert "Score < 3" in content


def test_review_gate_custom_thresholds(tmp_path: Path):
    """Review gate uses custom thresholds when configured."""
    cfg = _make_cfg(tmp_path)
    cfg = HarnessConfig(
        native=NativeModeConfig(gate_full_review_min=8, gate_summary_confirm_min=4),
        project=cfg.project,
        ci=cfg.ci,
    )
    cfg.project_root = tmp_path
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan_skill.read_text(encoding="utf-8")
    assert "Score >= 8" in content
    assert "Score 4\u20137" in content
    assert "Score < 4" in content



# Note: status.py threshold tests removed — _render_recent_result and
# SessionState were removed in task-045.
