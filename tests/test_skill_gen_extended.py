"""skill_gen.py 扩展功能测试：角色裁剪、项目语言检测、hook、资源部署、递归组合、5 角色系统"""

import json
from pathlib import Path
from unittest.mock import patch

from harness.core.config import HarnessConfig
from harness.native.skill_gen import (
    _build_full_context,
    _detect_project_lang,
    generate_native_artifacts,
    resolve_native_lang,
)


# --- Project language detection ---


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


# --- _build_full_context ---


def test_build_context_default_has_all_keys(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_full_context(cfg)
    assert "ci_command" in ctx
    assert "trunk_branch" in ctx
    assert "project_lang" in ctx
    assert "planner_principles" in ctx
    assert "builder_principles" in ctx
    assert "hooks_pre_build" in ctx


def test_build_context_hooks_from_config(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.hooks_pre_build = "scripts/pre.sh"
    cfg.native.hooks_post_eval = "scripts/post.sh"
    ctx = _build_full_context(cfg)
    assert ctx["hooks_pre_build"] == "scripts/pre.sh"
    assert ctx["hooks_post_eval"] == "scripts/post.sh"


def test_build_context_has_review_gate(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_full_context(cfg)
    assert "review_gate" in ctx
    assert ctx["review_gate"] == "eng"


def test_build_context_review_gate_custom(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.review_gate = "advisory"
    ctx = _build_full_context(cfg)
    assert ctx["review_gate"] == "advisory"


def test_build_context_has_plan_review_gate(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_full_context(cfg)
    assert "plan_review_gate" in ctx
    assert ctx["plan_review_gate"] == "auto"


def test_build_context_has_role_models(tmp_path: Path):
    """_build_full_context includes role_models_* for all 5 roles."""
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    with patch("harness.native.skill_gen.detect_cursor_recent_models", return_value=[]):
        ctx = _build_full_context(cfg)
    for role in ("architect", "product_owner", "engineer", "qa", "project_manager"):
        assert f"role_models_{role}" in ctx
        assert ctx[f"role_models_{role}"] == ""


def test_build_context_role_models_from_config(tmp_path: Path):
    """_build_full_context passes per-role model overrides from config."""
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.role_models = {"architect": "gpt-4.1", "qa": "o3-mini"}
    with patch(
        "harness.native.skill_gen.detect_cursor_recent_models",
        return_value=["gpt-4.1", "o3-mini"],
    ):
        ctx = _build_full_context(cfg)
    assert ctx["role_models_architect"] == "gpt-4.1"
    assert ctx["role_models_qa"] == "o3-mini"
    assert ctx["role_models_engineer"] == ""


def test_build_context_uses_evaluator_model_as_default_role_model(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.evaluator_model = "gpt-4.1"
    with patch("harness.native.skill_gen.detect_cursor_recent_models", return_value=["gpt-4.1"]):
        ctx = _build_full_context(cfg)
    assert ctx["role_models_architect"] == "gpt-4.1"
    assert ctx["role_models_engineer"] == "gpt-4.1"
    assert ctx["role_models_qa"] == "gpt-4.1"


def test_build_context_keeps_valid_evaluator_model_when_discovery_unavailable(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.evaluator_model = "gpt-4.1"
    with patch("harness.native.skill_gen.detect_cursor_recent_models", return_value=[]):
        ctx = _build_full_context(cfg)
    assert ctx["evaluator_model"] == "gpt-4.1"
    assert ctx["role_models_architect"] == "gpt-4.1"


def test_build_context_role_override_beats_evaluator_model(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.evaluator_model = "gpt-4.1"
    cfg.native.role_models = {"architect": "o3-mini"}
    with patch(
        "harness.native.skill_gen.detect_cursor_recent_models",
        return_value=["gpt-4.1", "o3-mini"],
    ):
        ctx = _build_full_context(cfg)
    assert ctx["role_models_architect"] == "o3-mini"
    assert ctx["role_models_engineer"] == "gpt-4.1"


def test_build_context_keeps_valid_role_override_when_discovery_unavailable(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.role_models = {"architect": "o3-mini"}
    with patch("harness.native.skill_gen.detect_cursor_recent_models", return_value=[]):
        ctx = _build_full_context(cfg)
    assert ctx["role_models_architect"] == "o3-mini"


def test_build_context_invalid_evaluator_model_falls_back_to_default(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.evaluator_model = "bad model"
    with patch("harness.native.skill_gen.detect_cursor_recent_models", return_value=["gpt-4.1"]):
        ctx = _build_full_context(cfg)
    assert ctx["evaluator_model"] == "IDE default"
    assert ctx["role_models_architect"] == ""


def test_build_context_unavailable_evaluator_model_falls_back_to_default(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.evaluator_model = "gpt-4.1"
    with patch(
        "harness.native.skill_gen.detect_cursor_recent_models",
        return_value=["claude-4.6-opus-high-thinking"],
    ):
        ctx = _build_full_context(cfg)
    assert ctx["evaluator_model"] == "IDE default"
    assert ctx["role_models_architect"] == ""


# --- Resource deployment ---


def _make_cfg(tmp_path: Path) -> HarnessConfig:
    """Helper: create a minimal config for generation tests."""
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir(exist_ok=True)
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )
    return HarnessConfig.load(tmp_path)


def test_generate_deploys_resource_files(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "make test"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    count = generate_native_artifacts(tmp_path, cfg=cfg)
    # 10 skills + 5 agents + 4 rules + 5 resources + 1 worktrees.json = 25
    assert count >= 25

    eval_dir = tmp_path / ".cursor" / "skills" / "harness" / "harness-eval"
    assert (eval_dir / "review-checklist.md").exists()
    assert (eval_dir / "specialists" / "testing.md").exists()
    assert (eval_dir / "specialists" / "security.md").exists()
    assert (eval_dir / "specialists" / "performance.md").exists()
    assert (eval_dir / "specialists" / "red-team.md").exists()


# --- Build / Eval / Ship skill content ---


def test_generated_skill_contains_project_lang_section(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    cfg = HarnessConfig.load(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    build_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md")
    content = build_skill.read_text(encoding="utf-8")
    assert "Python-Specific Guidance" in content
    assert "ruff check" in content


def test_generated_skill_includes_error_recovery(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    build_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md")
    content = build_skill.read_text(encoding="utf-8")
    assert "Error Recovery Matrix" in content
    assert "Import error" in content


def test_generated_eval_includes_trust_boundary(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    eval_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = eval_skill.read_text(encoding="utf-8")
    assert "Trust Boundaries" in content
    assert "UNTRUSTED" in content


def test_generated_plan_build_eval_ship_reference_workflow_state(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    skills_base = tmp_path / ".cursor" / "skills" / "harness"
    for name in ("harness-plan", "harness-build", "harness-eval", "harness-ship"):
        content = (skills_base / name / "SKILL.md").read_text(encoding="utf-8")
        assert "workflow-state.json" in content, f"{name} missing workflow-state reference"


def test_generated_ship_includes_bypass_immunity(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    ship_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship_skill.read_text(encoding="utf-8")
    assert "Bypass-Immune" in content
    assert "Safety Rules" in content


def test_fix_first_llm_output_is_ask():
    """fix-first template classifies LLM→DB as ASK (not AUTO-FIX)."""
    from harness.native.skill_gen import _get_template_dir, _render_template

    tmpl_dir = _get_template_dir()
    ctx = {"ci_command": "pytest", "trunk_branch": "main"}
    content = _render_template(tmpl_dir, "rule-fix-first.mdc.j2", ctx)
    assert "LLM output written to DB without validation | ASK" in content


def test_generated_ship_has_single_test_step(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "Step 3: Run Tests" in content
    assert "CI Verification" not in content


def test_generated_eval_includes_hook_points_when_configured(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    cfg.native.hooks_post_eval = "scripts/post-eval.sh"
    generate_native_artifacts(tmp_path, cfg=cfg)
    eval_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = eval_skill.read_text(encoding="utf-8")
    assert "Post-Eval Hook" in content
    assert "scripts/post-eval.sh" in content


def test_generated_eval_no_hook_residue_when_empty(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    eval_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = eval_skill.read_text(encoding="utf-8")
    assert "Post-Eval Hook" not in content


def test_generated_ship_advisory_mode(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    cfg.native.review_gate = "advisory"
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "advisory" in content.lower()
    assert "does not block" in content


def test_generated_build_no_hook_residue_when_empty(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    build = (tmp_path / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md")
    content = build.read_text(encoding="utf-8")
    assert "Pre-Build Hook" not in content
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == "## Step 6: Commit":
            prev_non_empty = ""
            for j in range(i - 1, -1, -1):
                if lines[j].strip():
                    prev_non_empty = lines[j].strip()
                    break
            assert prev_non_empty != "---", "Orphan --- before Step 6 when hooks empty"
            break


def test_review_checklist_uses_main_not_origin(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    checklist = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "review-checklist.md")
    content = checklist.read_text(encoding="utf-8")
    assert "git diff main..HEAD" in content
    assert "origin/main" not in content


def test_retro_uses_real_template_path(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    retro = (tmp_path / ".cursor" / "skills" / "harness" / "harness-retro" / "SKILL.md")
    content = retro.read_text(encoding="utf-8")
    assert "src/harness/templates/ship.j2" not in content
    assert "skill-ship.md.j2" in content


def test_ship_has_eval_artifact_gate(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "Eval Artifact Gate" in content
    assert "harness gate" in content
    gate_pos = content.index("Eval Artifact Gate")
    step6_pos = content.index("## Step 6:")
    assert gate_pos < step6_pos, "Eval gate must appear before Step 6"


def test_ship_has_eval_readiness_in_preflight(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "Eval Readiness Reminder" in content
    assert "EVAL — MANDATORY" in content
    reminder_pos = content.index("Eval Readiness Reminder")
    step2_pos = content.index("## Step 2:")
    assert reminder_pos < step2_pos, "Eval reminder must appear in pre-flight (before Step 2)"


def test_ship_important_rules_prioritize_eval(tmp_path: Path):
    import re

    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    rules_pos = content.index("## Important Rules")
    rules_section = content[rules_pos:]
    bullets = re.findall(r"^- \*\*Never skip.*", rules_section, re.MULTILINE)
    assert len(bullets) >= 2, "Expected multiple 'Never skip' rules"
    assert "eval" in bullets[0].lower(), \
        f"First 'Never skip' rule must be about eval, got: {bullets[0]}"


def test_no_claude_references_in_templates(tmp_path: Path):
    """No 'Claude' (capital C) references remain in generated skills or agents."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    cursor_dir = tmp_path / ".cursor"
    for md_file in cursor_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        assert "Claude" not in content, f"Found 'Claude' in {md_file.relative_to(tmp_path)}"


def test_error_recovery_no_test_overlap(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    build = (tmp_path / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md")
    content = build.read_text(encoding="utf-8")
    assert "Error Recovery Matrix" in content
    matrix_start = content.index("Error Recovery Matrix")
    matrix_section = content[matrix_start:matrix_start + 500]
    assert "CI failure (test)" not in matrix_section


def test_jinja_env_cache_shared(tmp_path: Path):
    from harness.native.skill_gen import _get_jinja_env
    tmpl_dir = str(tmp_path.resolve())
    (tmp_path / "dummy.j2").write_text("hello", encoding="utf-8")
    env1 = _get_jinja_env(tmpl_dir)
    env2 = _get_jinja_env(tmpl_dir)
    assert env1 is env2


# --- Config validation ---


def test_config_rejects_invalid_mechanism(tmp_path: Path):
    import pydantic
    from harness.core.config import NativeModeConfig
    with __import__("pytest").raises(pydantic.ValidationError):
        NativeModeConfig(adversarial_mechanism="invalid_value")


def test_config_rejects_invalid_review_gate(tmp_path: Path):
    import pydantic
    from harness.core.config import NativeModeConfig
    with __import__("pytest").raises(pydantic.ValidationError):
        NativeModeConfig(review_gate="invalid_value")


def test_config_plan_review_gate_literal(tmp_path: Path):
    import pydantic
    from harness.core.config import NativeModeConfig
    with __import__("pytest").raises(pydantic.ValidationError):
        NativeModeConfig(plan_review_gate="invalid_value")


def test_config_plan_review_gate_defaults_to_auto():
    from harness.core.config import NativeModeConfig
    cfg = NativeModeConfig()
    assert cfg.plan_review_gate == "auto"


def test_config_role_models_defaults_to_empty():
    """role_models defaults to empty dict."""
    from harness.core.config import NativeModeConfig
    cfg = NativeModeConfig()
    assert cfg.role_models == {}


def test_config_role_models_accepts_valid_values():
    """role_models accepts per-role model strings."""
    from harness.core.config import NativeModeConfig
    cfg = NativeModeConfig(role_models={"architect": "gpt-4.1", "qa": "o3-mini"})
    assert cfg.role_models["architect"] == "gpt-4.1"
    assert cfg.role_models["qa"] == "o3-mini"


def test_config_role_models_warns_on_unknown_keys():
    """role_models validator warns on unknown keys."""
    import warnings as _w
    from harness.core.config import NativeModeConfig
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        cfg = NativeModeConfig(role_models={"architect": "gpt-4.1", "product-owner": "o3"})
    assert any("product-owner" in str(w.message) for w in caught), (
        "Expected warning about unknown key 'product-owner'"
    )
    assert cfg.role_models["architect"] == "gpt-4.1"


def test_config_invalid_evaluator_model_warns():
    import warnings as _w
    from harness.core.config import NativeModeConfig

    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        NativeModeConfig(evaluator_model="bad model")
    assert any("native.evaluator_model" in str(w.message) for w in caught)


def test_config_invalid_role_model_warns():
    import warnings as _w
    from harness.core.config import NativeModeConfig

    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        NativeModeConfig(role_models={"architect": "bad model"})
    assert any("native.role_models.architect" in str(w.message) for w in caught)


# --- StrictUndefined template validation ---


def test_templates_have_no_undefined_variables(tmp_path: Path):
    """All templates render without UndefinedError when given the full context."""
    import jinja2
    from harness.native.skill_gen import _build_full_context as _bfc, _get_template_dir

    cfg = _make_cfg(tmp_path)
    tmpl_dir = _get_template_dir()
    context = _bfc(cfg)

    strict_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tmpl_dir)),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )

    for tmpl_name in strict_env.loader.list_templates():
        if not tmpl_name.endswith(".j2"):
            continue
        tmpl = strict_env.get_template(tmpl_name)
        try:
            tmpl.render(**context)
        except jinja2.UndefinedError as exc:
            __import__("pytest").fail(
                f"Undefined variable in {tmpl_name}: {exc}"
            )


# --- v3.0: Three entry points + review gate ---


def test_brainstorm_has_divergent_phase(tmp_path: Path):
    """brainstorm template includes Socratic exploration and approach options."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "Divergent Exploration" in content
    assert "APPROACH OPTIONS" in content
    assert "From Idea to Iteration Loop" in content
    assert "Continuous Loop Controller" in content


def test_brainstorm_updates_vision(tmp_path: Path):
    """brainstorm template includes vision.md update step via _vision-core."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "vision.md" in content
    assert "Update Vision" in content
    assert "Success Signals" in content


def test_vision_has_clarification_phase(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    vs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-vision" / "SKILL.md")
    content = vs.read_text(encoding="utf-8")
    assert "Vision Clarification" in content
    assert "From Direction to PR" in content


def test_all_three_entry_points_include_review_gate(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    skills_base = tmp_path / ".cursor" / "skills" / "harness"
    for name in ("harness-brainstorm", "harness-vision", "harness-plan"):
        content = (skills_base / name / "SKILL.md").read_text(encoding="utf-8")
        assert "Review Gate" in content, f"Missing Review Gate in {name}"


def test_review_gate_auto_has_scoring_table(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "escalation score" in content
    assert "FULL REVIEW" in content
    assert "SUMMARY CONFIRM" in content
    assert "AUTO PROCEED" in content


def test_review_gate_auto_has_interaction_depth(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    skills_base = tmp_path / ".cursor" / "skills" / "harness"

    bs = (skills_base / "harness-brainstorm" / "SKILL.md").read_text(encoding="utf-8")
    assert "interaction depth: high" in bs

    vs = (skills_base / "harness-vision" / "SKILL.md").read_text(encoding="utf-8")
    assert "interaction depth: medium" in vs

    pl = (skills_base / "harness-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "interaction depth: low" in pl


def test_review_gate_human_has_stop(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    cfg.native.plan_review_gate = "human"
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "**STOP.**" in content
    assert "SUMMARY CONFIRM" not in content


def test_review_gate_ai_auto_proceeds(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    cfg.native.plan_review_gate = "ai"
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "auto-approved after plan review" in content
    assert "**STOP.**" not in content
    assert "escalation score" not in content


def test_retro_uses_config_window_days(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    retro = (tmp_path / ".cursor" / "skills" / "harness" / "harness-retro" / "SKILL.md")
    content = retro.read_text(encoding="utf-8")
    assert '"N days ago"' not in content
    assert "14 days ago" in content


def test_retro_custom_window_days(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    cfg.native.retro_window_days = 30
    generate_native_artifacts(tmp_path, cfg=cfg)
    retro = (tmp_path / ".cursor" / "skills" / "harness" / "harness-retro" / "SKILL.md")
    content = retro.read_text(encoding="utf-8")
    assert "30 days ago" in content


def test_eval_has_context_degradation_ladder(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "Context Degradation Ladder" in content
    assert "Minimum viable eval" in content
    assert "FATAL" in content


def test_eval_uses_minimal_interaction_wording(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "minimal-interaction" in content
    assert "non-interactive" not in content


def test_ship_uses_minimal_interaction_wording(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "minimal-interaction" in content
    assert "non-interactive" not in content


def test_total_skill_count_is_ten(tmp_path: Path):
    """10 skills are generated."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    skills_dir = tmp_path / ".cursor" / "skills" / "harness"
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
    assert len(skill_dirs) == 10


# --- v3.1: Unified 5-role system + recursive composition ---


def test_five_role_agents_generated(tmp_path: Path):
    """5 role agents are generated (no old evaluator/adversarial-reviewer)."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    agent_files = sorted(f.stem for f in agents_dir.glob("harness-*.md"))
    assert "harness-architect" in agent_files
    assert "harness-product-owner" in agent_files
    assert "harness-engineer" in agent_files
    assert "harness-qa" in agent_files
    assert "harness-project-manager" in agent_files
    assert "harness-evaluator" not in agent_files
    assert "harness-adversarial-reviewer" not in agent_files
    assert len(agent_files) == 5


def test_role_agents_have_dual_mode(tmp_path: Path):
    """Each role agent contains both plan-review and code-eval mode sections."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    for name in ("harness-architect", "harness-product-owner", "harness-engineer",
                 "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "plan-review" in content, f"{name} missing plan-review mode"
        assert "code-eval" in content, f"{name} missing code-eval mode"


def test_role_agents_have_output_contract(tmp_path: Path):
    """Each role agent has the unified output contract format."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    for name in ("harness-architect", "harness-product-owner", "harness-engineer",
                 "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "Output Contract" in content, f"{name} missing output contract"
        assert "Score: N/10" in content, f"{name} missing score format"
        assert "PASS | ISSUES_FOUND" in content, f"{name} missing verdict format"


def test_role_agents_have_memverse_integration(tmp_path: Path):
    """Each role agent has Memverse integration section when Memverse is enabled."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = True
    generate_native_artifacts(tmp_path, cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    for name in ("harness-architect", "harness-product-owner", "harness-engineer",
                 "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "Memverse Integration" in content, f"{name} missing Memverse integration"
        assert "search_memory" in content, f"{name} missing search_memory"


def test_qa_agent_has_ci_ownership(tmp_path: Path):
    """QA agent is explicitly the only CI runner."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    qa = (tmp_path / ".cursor" / "agents" / "harness-qa.md").read_text(encoding="utf-8")
    assert "CI Ownership" in qa
    assert "ONLY" in qa
    assert "pytest" in qa


def test_role_model_override_in_agent(tmp_path: Path):
    """Per-role model config renders into agent template."""
    cfg = _make_cfg(tmp_path)
    cfg.native.role_models = {"architect": "gpt-4.1"}
    with patch("harness.native.skill_gen.detect_cursor_recent_models", return_value=["gpt-4.1"]):
        generate_native_artifacts(tmp_path, cfg=cfg)
    arch = (tmp_path / ".cursor" / "agents" / "harness-architect.md").read_text(encoding="utf-8")
    assert "gpt-4.1" in arch


def test_agent_omits_model_frontmatter_when_using_default(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    with patch("harness.native.skill_gen.detect_cursor_recent_models", return_value=[]):
        generate_native_artifacts(tmp_path, cfg=cfg)
    arch = (tmp_path / ".cursor" / "agents" / "harness-architect.md").read_text(encoding="utf-8")
    frontmatter = arch.split("---", 2)[1]
    assert "model:" not in frontmatter


# --- Recursive composition ---


def test_brainstorm_includes_vision_core(tmp_path: Path):
    """brainstorm recursively includes _vision-core content."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "Update Vision" in content


def test_brainstorm_includes_plan_core(tmp_path: Path):
    """brainstorm still includes active-plan generation within the loop controller."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "Plan Generation" in content
    assert "Plan Backlog" in content
    assert "Active Plan" in content
    assert "Feedback Ledger" in content
    assert "Stop Conditions" in content
    assert "unattended background scheduler" in content


def test_brainstorm_includes_plan_review(tmp_path: Path):
    """brainstorm recursively includes the 5-role plan review."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "Plan Review" in content
    assert "5-Role Parallel Dispatch" in content
    assert "harness-architect" in content
    assert "harness-qa" in content


def test_brainstorm_and_ship_include_long_horizon_review_context_hints(tmp_path: Path):
    """Generated skills expose stable long-horizon review context hints."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    brainstorm = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    brainstorm_content = brainstorm.read_text(encoding="utf-8")
    assert "roadmap_backlog_path" in brainstorm_content
    assert "single-round" in brainstorm_content
    assert "do NOT force loop assumptions" in brainstorm_content

    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    ship_content = ship.read_text(encoding="utf-8")
    assert "feedback_ledger_path" in ship_content
    assert "continue_pause_summary" in ship_content


def test_brainstorm_includes_ship_invocation(tmp_path: Path):
    """brainstorm includes the ship invocation inside the loop controller."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "/harness-ship" in content


def test_vision_includes_vision_core(tmp_path: Path):
    """vision includes _vision-core content."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    vs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-vision" / "SKILL.md")
    content = vs.read_text(encoding="utf-8")
    assert "Update Vision" in content
    assert "product and direction artifact" in content
    assert "implementation choices belong in `plan.md`" in content


def test_brainstorm_and_vision_stay_in_harness_workflow(tmp_path: Path):
    """brainstorm/vision should not switch to Cursor Plan mode."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    skills_base = tmp_path / ".cursor" / "skills" / "harness"

    brainstorm = (skills_base / "harness-brainstorm" / "SKILL.md").read_text(encoding="utf-8")
    assert "do NOT call Cursor `SwitchMode` to `plan`" in brainstorm
    assert "Cursor's built-in Plan mode" in brainstorm

    vision = (skills_base / "harness-vision" / "SKILL.md").read_text(encoding="utf-8")
    assert "do NOT call Cursor `SwitchMode` to `plan`" in vision
    assert "Cursor's built-in Plan mode" in vision


def test_vision_includes_plan_core(tmp_path: Path):
    """vision includes _plan-core content via recursive chain."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    vs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-vision" / "SKILL.md")
    content = vs.read_text(encoding="utf-8")
    assert "Plan Generation" in content
    assert "Decision Classification" in content


def test_plan_includes_plan_core_not_vision(tmp_path: Path):
    """plan includes _plan-core but NOT _vision-core."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    pl = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = pl.read_text(encoding="utf-8")
    assert "Plan Generation" in content
    assert "Update Vision" not in content
    assert "Continuous Loop Controller" not in content
    assert "Plan Backlog" not in content


def test_product_and_pm_agents_include_direction_governance(tmp_path: Path):
    """PO and PM agents include long-horizon governance language."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    po = (tmp_path / ".cursor" / "agents" / "harness-product-owner.md").read_text(encoding="utf-8")
    assert "Roadmap / Plan Backlog alignment" in po
    assert "Evidence of direction progress" in po
    assert "Long-Horizon Governance Boundary" in po
    assert "Direction recommendation" in po
    assert "single-round" in po
    assert "do NOT" in po
    assert "`N/A`" in po

    pm = (tmp_path / ".cursor" / "agents" / "harness-project-manager.md").read_text(encoding="utf-8")
    assert "Roadmap / Active Plan relationship" in pm
    assert "Backlog health" in pm
    assert "Long-Horizon Governance Boundary" in pm
    assert "Direction recommendation" in pm
    assert "single-round" in pm
    assert "do NOT" in pm
    assert "`N/A`" in pm


def test_plan_includes_plan_review(tmp_path: Path):
    """plan includes the 5-role plan review section."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    pl = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = pl.read_text(encoding="utf-8")
    assert "5-Role Parallel Dispatch" in content
    assert "Re-Plan Loop" in content


def test_plan_includes_ship_invocation(tmp_path: Path):
    """plan includes the ship invocation after review gate."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    pl = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = pl.read_text(encoding="utf-8")
    assert "/harness-ship" in content


# --- Eval uses new 5-role code review ---


def test_eval_uses_five_role_code_review(tmp_path: Path):
    """eval template dispatches 5 role subagents, not old 3-pass system."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "5-Role Code Review" in content
    assert "harness-architect" in content
    assert "harness-engineer" in content
    assert "harness-qa" in content
    assert "harness-product-owner" in content
    assert "harness-project-manager" in content
    assert "Pass 1:" not in content
    assert "Pass 2:" not in content
    assert "Pass 3:" not in content


def test_eval_has_degradation_ladder(tmp_path: Path):
    """eval code review section has degradation ladder for subagent failures."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "Degradation ladder" in content
    assert "5/5 respond" in content
    assert "0/5 respond" in content


# --- Ship uses new 5-role code review ---


def test_ship_step38_uses_five_role_review(tmp_path: Path):
    """ship Step 3.8 dispatches 5 role reviewers, not old 3-pass system."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "5-Role Code Evaluation" in content
    assert "harness-architect" in content
    assert "harness-qa" in content
    assert "harness-evaluator" not in content


# --- Review gate references plan review scores ---


def test_review_gate_references_plan_review_scores(tmp_path: Path):
    """auto mode review gate references aggregate plan review score."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "plan review aggregate score" in content
    assert "Arch" in content
    assert "Aggregate" in content


# --- Worktrees.json generation ---


def test_worktrees_json_generated(tmp_path: Path):
    """generate_native_artifacts creates .cursor/worktrees.json."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    wt = tmp_path / ".cursor" / "worktrees.json"
    assert wt.exists()
    data = json.loads(wt.read_text(encoding="utf-8"))
    assert "setup-worktree-unix" in data
    assert "setup-worktree-windows" in data


def test_worktrees_json_unix_scripts_correct(tmp_path: Path):
    """Unix setup scripts copy .agents/ config and .cursor/ directory."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    data = json.loads((tmp_path / ".cursor" / "worktrees.json").read_text(encoding="utf-8"))
    unix = data["setup-worktree-unix"]
    assert isinstance(unix, list)
    assert any("mkdir" in cmd and ".agents/tasks" in cmd for cmd in unix)
    assert any("config.toml" in cmd for cmd in unix)
    assert any("vision.md" in cmd for cmd in unix)
    assert any(".cursor" in cmd and "cp" in cmd for cmd in unix)
    assert any("HARNESS_TASK_ID" in cmd for cmd in unix), "unix scripts should export HARNESS_TASK_ID"


def test_worktrees_json_windows_scripts_correct(tmp_path: Path):
    """Windows setup scripts use xcopy and Windows path separators."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    data = json.loads((tmp_path / ".cursor" / "worktrees.json").read_text(encoding="utf-8"))
    win = data["setup-worktree-windows"]
    assert isinstance(win, list)
    assert any("mkdir" in cmd and "agents" in cmd for cmd in win)
    assert any("config.toml" in cmd for cmd in win)
    assert any("vision.md" in cmd for cmd in win)
    assert any("xcopy" in cmd and ".cursor" in cmd for cmd in win)
    assert any("HARNESS_TASK_ID" in cmd for cmd in win), "windows scripts should set HARNESS_TASK_ID"


def test_worktrees_json_skip_when_exists_no_force(tmp_path: Path):
    """Existing worktrees.json is preserved when force=False."""
    cfg = _make_cfg(tmp_path)
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    sentinel = '{"custom": true}\n'
    (cursor_dir / "worktrees.json").write_text(sentinel, encoding="utf-8")

    generate_native_artifacts(tmp_path, cfg=cfg, force=False)

    assert (cursor_dir / "worktrees.json").read_text(encoding="utf-8") == sentinel


def test_worktrees_json_overwrite_when_force(tmp_path: Path):
    """Existing worktrees.json is overwritten when force=True."""
    cfg = _make_cfg(tmp_path)
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    (cursor_dir / "worktrees.json").write_text('{"custom": true}\n', encoding="utf-8")

    generate_native_artifacts(tmp_path, cfg=cfg, force=True)

    data = json.loads((cursor_dir / "worktrees.json").read_text(encoding="utf-8"))
    assert "setup-worktree-unix" in data
    assert "custom" not in data


def test_worktrees_json_count_incremented(tmp_path: Path):
    """worktrees.json is counted in the returned artifact count."""
    cfg = _make_cfg(tmp_path)
    count_with = generate_native_artifacts(tmp_path, cfg=cfg, force=True)

    (tmp_path / ".cursor" / "worktrees.json").write_text('{"x":1}', encoding="utf-8")
    count_without = generate_native_artifacts(tmp_path, cfg=cfg, force=False)

    assert count_with == count_without + 1


# --- resolve_native_lang ---


class TestResolveNativeLang:
    def test_explicit_en_zh(self):
        assert resolve_native_lang(lang="en") == "en"
        assert resolve_native_lang(lang="zh") == "zh"

    def test_explicit_other_defaults_en(self):
        assert resolve_native_lang(lang="fr") == "en"

    def test_from_config(self, tmp_path: Path):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "config.toml").write_text(
            '[project]\nname = "x"\nlang = "zh"\n',
            encoding="utf-8",
        )
        assert resolve_native_lang(tmp_path) == "zh"

    def test_config_load_failure_falls_through(self, tmp_path: Path):
        assert resolve_native_lang(tmp_path) == "en"

    @patch("harness.native.skill_gen.HarnessConfig.load", side_effect=OSError("no config"))
    @patch("harness.native.skill_gen.get_lang", return_value="zh")
    def test_fallback_ui_lang(self, _mock_lang, _mock_load, tmp_path: Path):
        assert resolve_native_lang(tmp_path) == "zh"

    @patch("harness.native.skill_gen.get_lang", return_value="invalid")
    def test_fallback_invalid_ui_lang_defaults_en(self, _mock_lang):
        assert resolve_native_lang(None) == "en"


# --- i18n: Chinese locale tests ---


def test_zh_directory_parity():
    """zh/ directory must mirror en/ — same filenames in every subdirectory."""
    from harness.native.skill_gen import _get_template_dir

    en_dir = _get_template_dir("en")
    zh_dir = _get_template_dir("zh")

    def _relative_files(base: Path, exclude_subdir: str = "") -> set[str]:
        result = set()
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base))
            if exclude_subdir and rel.startswith(exclude_subdir):
                continue
            result.add(rel)
        return result

    en_files = _relative_files(en_dir, exclude_subdir="zh/")
    zh_files = _relative_files(zh_dir)
    missing_in_zh = en_files - zh_files
    assert not missing_in_zh, f"zh/ is missing files present in en/: {sorted(missing_in_zh)}"
    extra_in_zh = zh_files - en_files
    assert not extra_in_zh, f"zh/ has extra files not in en/: {sorted(extra_in_zh)}"


def test_zh_templates_render_without_errors(tmp_path: Path):
    """All zh templates render with StrictUndefined — no missing variables."""
    import jinja2
    from harness.native.skill_gen import _build_full_context as _bfc, _get_template_dir

    cfg = _make_cfg(tmp_path)
    tmpl_dir = _get_template_dir("zh")
    context = _bfc(cfg, lang="zh")

    strict_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tmpl_dir)),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )

    for tmpl_name in strict_env.loader.list_templates():
        if not tmpl_name.endswith(".j2"):
            continue
        tmpl = strict_env.get_template(tmpl_name)
        try:
            tmpl.render(**context)
        except jinja2.UndefinedError as exc:
            __import__("pytest").fail(
                f"Undefined variable in zh/{tmpl_name}: {exc}"
            )


def test_zh_generated_artifacts_contain_chinese(tmp_path: Path):
    """When lang=zh, generated skills/agents/rules contain Chinese characters."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)

    build_skill = tmp_path / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md"
    content = build_skill.read_text(encoding="utf-8")
    assert "严格按合约交付" in content, "zh build skill should contain Chinese principles"

    architect = tmp_path / ".cursor" / "agents" / "harness-architect.md"
    content_arch = architect.read_text(encoding="utf-8")
    assert "架构" in content_arch, "zh architect agent should contain Chinese"

    rule = tmp_path / ".cursor" / "rules" / "harness-trust-boundary.mdc"
    content_rule = rule.read_text(encoding="utf-8")
    assert "信任边界" in content_rule, "zh trust-boundary rule should be in Chinese"


def test_zh_brainstorm_and_governance_agents_contain_loop_concepts(tmp_path: Path):
    """zh generation includes brainstorm loop anchors and governance language."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)

    brainstorm = tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md"
    content_bs = brainstorm.read_text(encoding="utf-8")
    assert "持续迭代控制器" in content_bs
    assert "Plan Backlog" in content_bs
    assert "Feedback Ledger" in content_bs
    assert "停止条件" in content_bs
    assert "不要调用 Cursor 的 `SwitchMode` 切到 `plan`" in content_bs
    assert "业务/用户语言" in content_bs

    vision = tmp_path / ".cursor" / "skills" / "harness" / "harness-vision" / "SKILL.md"
    content_vs = vision.read_text(encoding="utf-8")
    assert "工作流边界" in content_vs
    assert "不要调用 Cursor 的 `SwitchMode` 切到 `plan`" in content_vs
    assert "Cursor 内置的 Plan 模式" in content_vs

    po = tmp_path / ".cursor" / "agents" / "harness-product-owner.md"
    content_po = po.read_text(encoding="utf-8")
    assert "长期方向治理边界" in content_po
    assert "方向推进证据" in content_po
    assert "Direction recommendation" in content_po

    pm = tmp_path / ".cursor" / "agents" / "harness-project-manager.md"
    content_pm = pm.read_text(encoding="utf-8")
    assert "长期方向治理边界" in content_pm
    assert "Backlog 健康度" in content_pm
    assert "Direction recommendation" in content_pm


def test_zh_plan_build_eval_ship_reference_workflow_state(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)

    skills_base = tmp_path / ".cursor" / "skills" / "harness"
    for name in ("harness-plan", "harness-build", "harness-eval", "harness-ship"):
        content = (skills_base / name / "SKILL.md").read_text(encoding="utf-8")
        assert "workflow-state.json" in content, f"{name} missing zh workflow-state reference"


def test_zh_resources_contain_chinese(tmp_path: Path):
    """zh static resources (review-checklist, specialists) contain Chinese."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)

    checklist = (
        tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "review-checklist.md"
    )
    content = checklist.read_text(encoding="utf-8")
    assert "评审" in content, "zh review-checklist should contain Chinese"


def test_en_generation_unchanged_after_zh_addition(tmp_path: Path):
    """English generation is not affected by the zh directory's existence."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="en", cfg=cfg)

    build_skill = tmp_path / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md"
    content = build_skill.read_text(encoding="utf-8")
    assert "Deliver exactly per contract" in content
    assert "严格按合约交付" not in content


def test_get_template_dir_returns_zh_when_available():
    """_get_template_dir('zh') returns the zh subdirectory."""
    from harness.native.skill_gen import _get_template_dir

    en_dir = _get_template_dir("en")
    zh_dir = _get_template_dir("zh")
    assert zh_dir != en_dir
    assert zh_dir.name == "zh"
    assert zh_dir.parent == en_dir


def test_get_template_dir_unknown_lang_fallback():
    """Unknown lang values fall back to en directory."""
    from harness.native.skill_gen import _get_template_dir

    en_dir = _get_template_dir("en")
    assert _get_template_dir("fr") == en_dir
    assert _get_template_dir("") == en_dir


def test_i18n_catalogs_key_parity():
    """en.py and zh.py must have exactly the same set of message keys."""
    from harness.i18n.en import MESSAGES as EN
    from harness.i18n.zh import MESSAGES as ZH

    en_keys = set(EN.keys())
    zh_keys = set(ZH.keys())
    missing_in_zh = en_keys - zh_keys
    missing_in_en = zh_keys - en_keys
    assert not missing_in_zh, f"Keys in en.py but missing in zh.py: {sorted(missing_in_zh)}"
    assert not missing_in_en, f"Keys in zh.py but missing in en.py: {sorted(missing_in_en)}"


def test_brainstorm_i18n_hints_describe_loop():
    """init/native hints describe brainstorm as a loop, not a single plan."""
    from harness.i18n.en import MESSAGES as EN
    from harness.i18n.zh import MESSAGES as ZH

    assert "roadmap/backlog" in EN["native.hint_brainstorm"]
    assert "active plan" in EN["init.guide_brainstorm"]
    assert "roadmap/backlog" in ZH["native.hint_brainstorm"]
    assert "active plan" in ZH["init.guide_brainstorm"]


def test_readmes_explain_entry_point_boundaries():
    """README docs distinguish brainstorm, vision, and single-round plan usage."""
    repo_root = Path(__file__).resolve().parents[1]
    readme_en = (repo_root / "README.md").read_text(encoding="utf-8")
    readme_zh = (repo_root / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "long-horizon loop" in readme_en
    assert "/harness-vision" in readme_en
    assert "single-round plan" in readme_en

    assert "长期方向" in readme_zh
    assert "/harness-vision" in readme_zh
    assert "单轮 plan" in readme_zh


def test_zh_ship_skill_contains_chinese(tmp_path: Path):
    """Ship skill — the largest template — renders correctly in Chinese."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)

    ship_skill = tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md"
    content = ship_skill.read_text(encoding="utf-8")
    assert "自动化管线" in content or "交付管线" in content
    assert "pytest" in content, "CI command should still be present"


def test_ship_en_and_zh_reference_harness_gate(tmp_path: Path):
    """Both en and zh ship templates reference 'harness gate' CLI command."""
    cfg = _make_cfg(tmp_path)

    generate_native_artifacts(tmp_path, lang="en", cfg=cfg)
    ship_en = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content_en = ship_en.read_text(encoding="utf-8")
    assert "harness gate" in content_en, "en ship template must reference 'harness gate'"

    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)
    ship_zh = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content_zh = ship_zh.read_text(encoding="utf-8")
    assert "harness gate" in content_zh, "zh ship template must reference 'harness gate'"


# --- Handoff references in templates ---


def test_en_templates_reference_handoff(tmp_path: Path):
    """EN plan/build/eval/ship templates reference handoff JSON files."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="en", cfg=cfg)
    skills_base = tmp_path / ".cursor" / "skills" / "harness"

    plan_content = (skills_base / "harness-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "handoff-plan.json" in plan_content

    build_content = (skills_base / "harness-build" / "SKILL.md").read_text(encoding="utf-8")
    assert "handoff-plan.json" in build_content
    assert "handoff-build.json" in build_content

    eval_content = (skills_base / "harness-eval" / "SKILL.md").read_text(encoding="utf-8")
    assert "handoff-build.json" in eval_content

    ship_content = (skills_base / "harness-ship" / "SKILL.md").read_text(encoding="utf-8")
    assert "handoff-ship.json" in ship_content


def test_zh_templates_reference_handoff(tmp_path: Path):
    """ZH plan/build/eval/ship templates reference handoff JSON files."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)
    skills_base = tmp_path / ".cursor" / "skills" / "harness"

    plan_content = (skills_base / "harness-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "handoff-plan.json" in plan_content

    build_content = (skills_base / "harness-build" / "SKILL.md").read_text(encoding="utf-8")
    assert "handoff-plan.json" in build_content
    assert "handoff-build.json" in build_content

    eval_content = (skills_base / "harness-eval" / "SKILL.md").read_text(encoding="utf-8")
    assert "handoff-build.json" in eval_content

    ship_content = (skills_base / "harness-ship" / "SKILL.md").read_text(encoding="utf-8")
    assert "handoff-ship.json" in ship_content


# --- B4: Layered context assembly ---


def test_layered_context_agents_lack_stage_keys(tmp_path: Path):
    """Agent artifacts should NOT receive stage-layer keys (hooks, gates)."""
    from harness.native.skill_gen import _build_layered_context

    cfg = _make_cfg(tmp_path)
    ctx = _build_layered_context(cfg, "agent", "harness-architect", lang="en")
    assert "ci_command" in ctx
    assert "evaluator_model" in ctx
    for key in ("hooks_pre_build", "hooks_post_eval", "hooks_pre_ship",
                "review_gate", "plan_review_gate",
                "gate_full_review_min", "gate_summary_confirm_min"):
        assert key not in ctx, f"agent should not have stage key: {key}"


def test_layered_context_rules_lack_role_keys(tmp_path: Path):
    """Rule artifacts with only base+stage should NOT receive role-layer keys."""
    from harness.native.skill_gen import _build_layered_context

    cfg = _make_cfg(tmp_path)
    ctx = _build_layered_context(cfg, "rule", "harness-workflow", lang="en")
    assert "trunk_branch" in ctx
    assert "ci_command" in ctx
    for key in ("planner_principles", "builder_principles",
                "role_models_architect", "role_models_qa"):
        assert key not in ctx, f"rule without layer 1 should not have: {key}"


def test_layered_context_skills_have_all_layers(tmp_path: Path):
    """Skill artifacts get all layers (base + role + stage)."""
    from harness.native.skill_gen import _build_layered_context

    cfg = _make_cfg(tmp_path)
    ctx = _build_layered_context(cfg, "skill", "harness-build", lang="en")
    assert "ci_command" in ctx
    assert "builder_principles" in ctx
    assert "hooks_pre_build" in ctx
    assert "review_gate" in ctx


def test_layered_context_unknown_artifact_gets_full(tmp_path: Path):
    """Unknown artifact type/name falls back to full context."""
    from harness.native.skill_gen import _build_layered_context

    cfg = _make_cfg(tmp_path)
    ctx = _build_layered_context(cfg, "unknown", "unknown-name", lang="en")
    assert "ci_command" in ctx
    assert "builder_principles" in ctx
    assert "hooks_pre_build" in ctx


def test_dead_variables_removed(tmp_path: Path):
    """adversarial_mechanism and evaluator_model_requested are not in context."""
    cfg = _make_cfg(tmp_path)
    ctx = _build_full_context(cfg)
    assert "adversarial_mechanism" not in ctx
    assert "evaluator_model_requested" not in ctx


def test_full_context_superset_of_layered(tmp_path: Path):
    """_build_full_context returns superset of any layered context."""
    from harness.native.skill_gen import _build_layered_context

    cfg = _make_cfg(tmp_path)
    full = _build_full_context(cfg)
    layered = _build_layered_context(cfg, "skill", "harness-build", lang="en")
    for key in layered:
        assert key in full, f"full context missing key: {key}"


def test_rule_activation_disabled_skips_file(tmp_path: Path):
    """disabled rule_activation prevents file generation."""
    cfg = _make_cfg(tmp_path)
    cfg.native.rule_activation = {"harness-safety-guardrails": "disabled"}
    generate_native_artifacts(tmp_path, cfg=cfg)

    rules_dir = tmp_path / ".cursor" / "rules"
    assert not (rules_dir / "harness-safety-guardrails.mdc").exists()
    assert (rules_dir / "harness-trust-boundary.mdc").exists()


def test_rule_activation_phase_match_adds_marker(tmp_path: Path):
    """phase_match rule_activation adds a marker comment to the file."""
    cfg = _make_cfg(tmp_path)
    cfg.native.rule_activation = {"harness-workflow": "phase_match"}
    generate_native_artifacts(tmp_path, cfg=cfg)

    content = (tmp_path / ".cursor" / "rules" / "harness-workflow.mdc").read_text(encoding="utf-8")
    assert content.startswith("<!-- rule-activation: phase_match -->")


def test_rule_activation_default_generates_all(tmp_path: Path):
    """Default rule_activation (empty) generates all 4 rules."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    rules_dir = tmp_path / ".cursor" / "rules"
    assert (rules_dir / "harness-trust-boundary.mdc").exists()
    assert (rules_dir / "harness-workflow.mdc").exists()
    assert (rules_dir / "harness-fix-first.mdc").exists()
    assert (rules_dir / "harness-safety-guardrails.mdc").exists()


def test_rule_activation_disabled_reduces_artifact_count(tmp_path: Path):
    """Disabling a rule reduces the total artifact count."""
    cfg = _make_cfg(tmp_path)
    count_all = generate_native_artifacts(tmp_path, cfg=cfg, force=True)

    cfg.native.rule_activation = {"harness-safety-guardrails": "disabled"}
    count_less = generate_native_artifacts(tmp_path, cfg=cfg, force=True)
    assert count_less == count_all - 1


def test_agent_context_layers_comment(tmp_path: Path):
    """Generated agents contain context layers HTML comment."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    agents_dir = tmp_path / ".cursor" / "agents"
    for agent_name in ("harness-architect", "harness-product-owner",
                       "harness-engineer", "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{agent_name}.md").read_text(encoding="utf-8")
        assert "<!-- context: layers " in content, f"{agent_name} missing context layers comment"


def test_zh_agent_context_layers_comment(tmp_path: Path):
    """ZH generated agents contain context layers HTML comment."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)

    agents_dir = tmp_path / ".cursor" / "agents"
    for agent_name in ("harness-architect", "harness-product-owner",
                       "harness-engineer", "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{agent_name}.md").read_text(encoding="utf-8")
        assert "<!-- context: layers " in content


def test_config_rule_activation_unknown_key_warns():
    """Unknown rule_activation key emits UserWarning."""
    import warnings as _w
    from harness.core.config import NativeModeConfig

    with _w.catch_warnings(record=True) as ws:
        _w.simplefilter("always")
        NativeModeConfig(rule_activation={"nonexistent-rule": "always"})
    assert any("Unknown native.rule_activation" in str(w.message) for w in ws)


def test_config_rule_activation_invalid_value_warns():
    """Invalid rule_activation value emits UserWarning."""
    import warnings as _w
    from harness.core.config import NativeModeConfig

    with _w.catch_warnings(record=True) as ws:
        _w.simplefilter("always")
        NativeModeConfig(rule_activation={"harness-workflow": "invalid_mode"})
    assert any("Invalid native.rule_activation" in str(w.message) for w in ws)


# --- B5: Workflow Memory Pack ---


def test_memverse_disabled_agents_no_memverse_content(tmp_path: Path):
    """Memverse disabled → agents do not contain Memverse instructions."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = False
    generate_native_artifacts(tmp_path, cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    for name in ("harness-architect", "harness-product-owner", "harness-engineer",
                 "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "search_memory" not in content, f"{name} leaks Memverse when disabled"
        assert "add_memories" not in content, f"{name} leaks Memverse when disabled"


def test_memverse_enabled_agents_have_memverse_content(tmp_path: Path):
    """Memverse enabled → agents contain Memverse instructions + correct domain."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = True
    cfg.integrations.memverse.domain_prefix = "my-custom-domain"
    generate_native_artifacts(tmp_path, cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    for name in ("harness-architect", "harness-product-owner", "harness-engineer",
                 "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "search_memory" in content, f"{name} missing Memverse when enabled"


def test_memverse_disabled_eval_no_memverse(tmp_path: Path):
    """Memverse disabled → eval skill does not reference search_memory/add_memories."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = False
    generate_native_artifacts(tmp_path, cfg=cfg)
    content = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md").read_text(encoding="utf-8")
    assert "search_memory" not in content
    assert "add_memories" not in content


def test_memverse_enabled_eval_has_memverse(tmp_path: Path):
    """Memverse enabled → eval skill references Memverse."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = True
    generate_native_artifacts(tmp_path, cfg=cfg)
    content = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md").read_text(encoding="utf-8")
    assert "search_memory" in content
    assert "add_memories" in content


def test_memverse_disabled_ship_no_memverse(tmp_path: Path):
    """Memverse disabled → ship skill does not reference prior learnings."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = False
    generate_native_artifacts(tmp_path, cfg=cfg)
    content = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md").read_text(encoding="utf-8")
    assert "search_memory" not in content


def test_memverse_disabled_learn_shows_not_enabled(tmp_path: Path):
    """Memverse disabled → learn skill shows 'not enabled' message."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = False
    generate_native_artifacts(tmp_path, cfg=cfg)
    content = (tmp_path / ".cursor" / "skills" / "harness" / "harness-learn" / "SKILL.md").read_text(encoding="utf-8")
    assert "search_memory" not in content
    assert "not enabled" in content.lower() or "未启用" in content


def test_memverse_enabled_learn_has_full_content(tmp_path: Path):
    """Memverse enabled → learn skill has full Memverse content."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = True
    generate_native_artifacts(tmp_path, cfg=cfg)
    content = (tmp_path / ".cursor" / "skills" / "harness" / "harness-learn" / "SKILL.md").read_text(encoding="utf-8")
    assert "search_memory" in content
    assert "add_memories" in content


def test_memverse_domain_fallback_to_project_name(tmp_path: Path):
    """Empty domain_prefix falls back to project_name."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = True
    cfg.integrations.memverse.domain_prefix = ""
    cfg.project.name = "test-proj"
    generate_native_artifacts(tmp_path, cfg=cfg)
    content = (tmp_path / ".cursor" / "skills" / "harness" / "harness-learn" / "SKILL.md").read_text(encoding="utf-8")
    assert "test-proj" in content


def test_memverse_domain_uses_prefix_when_set(tmp_path: Path):
    """Non-empty domain_prefix is used as memverse_domain."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = True
    cfg.integrations.memverse.domain_prefix = "custom-domain"
    generate_native_artifacts(tmp_path, cfg=cfg)
    content = (tmp_path / ".cursor" / "skills" / "harness" / "harness-learn" / "SKILL.md").read_text(encoding="utf-8")
    assert "custom-domain" in content


def test_layer0_context_includes_memverse_keys(tmp_path: Path):
    """Layer 0 context includes memverse_enabled and memverse_domain."""
    from harness.native.skill_gen import _build_layered_context

    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = True
    cfg.integrations.memverse.domain_prefix = "my-proj"
    ctx = _build_layered_context(cfg, "agent", "harness-architect", lang="en")
    assert "memverse_enabled" in ctx
    assert ctx["memverse_enabled"] == "true"
    assert "memverse_domain" in ctx
    assert ctx["memverse_domain"] == "my-proj"


def test_layer0_context_memverse_disabled(tmp_path: Path):
    """Layer 0 context reflects disabled state."""
    from harness.native.skill_gen import _build_layered_context

    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = False
    ctx = _build_layered_context(cfg, "skill", "harness-eval", lang="en")
    assert ctx["memverse_enabled"] == "false"


def test_zh_memverse_disabled_no_leakage(tmp_path: Path):
    """ZH templates: Memverse disabled → no search_memory/add_memories in agents."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = False
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    for name in ("harness-architect", "harness-product-owner", "harness-engineer",
                 "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "search_memory" not in content, f"ZH {name} leaks Memverse when disabled"


def test_zh_memverse_enabled_has_content(tmp_path: Path):
    """ZH templates: Memverse enabled → agents contain Memverse."""
    cfg = _make_cfg(tmp_path)
    cfg.integrations.memverse.enabled = True
    generate_native_artifacts(tmp_path, lang="zh", cfg=cfg)
    agents_dir = tmp_path / ".cursor" / "agents"
    for name in ("harness-architect", "harness-product-owner", "harness-engineer",
                 "harness-qa", "harness-project-manager"):
        content = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        assert "search_memory" in content, f"ZH {name} missing Memverse when enabled"
