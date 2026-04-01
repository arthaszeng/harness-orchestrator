"""skill_gen.py 扩展功能测试：角色裁剪、项目语言检测、hook"""

from pathlib import Path

from harness.core.config import HarnessConfig
from harness.native.skill_gen import _build_context, _detect_project_lang


def test_detect_project_lang_python(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    assert _detect_project_lang(cfg) == "python"


def test_detect_project_lang_typescript(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    assert _detect_project_lang(cfg) == "typescript"


def test_detect_project_lang_go(tmp_path: Path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    assert _detect_project_lang(cfg) == "go"


def test_detect_project_lang_unknown(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    assert _detect_project_lang(cfg) == "unknown"


def test_build_context_default_has_all_keys(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_context(cfg)
    assert "ci_command" in ctx
    assert "trunk_branch" in ctx
    assert "project_lang" in ctx
    assert "planner_principles" in ctx
    assert "builder_principles" in ctx
    assert "hooks_pre_build" in ctx


def test_build_context_adversarial_strips_keys(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_context(cfg, role="adversarial_reviewer")
    assert "builder_principles" not in ctx
    assert "planner_principles" not in ctx
    assert "ci_command" not in ctx
    assert "trunk_branch" in ctx
    assert "adversarial_model" in ctx


def test_build_context_evaluator_strips_planner_principles(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_context(cfg, role="evaluator")
    assert "planner_principles" not in ctx
    assert "ci_command" in ctx
    assert "builder_principles" in ctx


def test_build_context_planner_strips_builder_principles(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_context(cfg, role="planner")
    assert "builder_principles" not in ctx
    assert "planner_principles" in ctx


def test_build_context_hooks_from_config(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.hooks_pre_build = "scripts/pre.sh"
    cfg.native.hooks_post_eval = "scripts/post.sh"
    ctx = _build_context(cfg)
    assert ctx["hooks_pre_build"] == "scripts/pre.sh"
    assert ctx["hooks_post_eval"] == "scripts/post.sh"
