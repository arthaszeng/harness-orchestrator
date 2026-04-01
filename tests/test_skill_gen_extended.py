"""skill_gen.py 扩展功能测试：角色裁剪、项目语言检测、hook、资源部署、递归组合、5 角色系统"""

import json
from pathlib import Path
from unittest.mock import patch

from harness.core.config import HarnessConfig
from harness.native.skill_gen import (
    _build_context,
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


# --- _build_context ---


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


def test_build_context_has_review_gate(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_context(cfg)
    assert "review_gate" in ctx
    assert ctx["review_gate"] == "eng"


def test_build_context_review_gate_custom(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.review_gate = "advisory"
    ctx = _build_context(cfg)
    assert ctx["review_gate"] == "advisory"


def test_build_context_has_plan_review_gate(tmp_path: Path):
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_context(cfg)
    assert "plan_review_gate" in ctx
    assert ctx["plan_review_gate"] == "auto"


def test_build_context_has_role_models(tmp_path: Path):
    """_build_context includes role_models_* for all 5 roles."""
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_context(cfg)
    for role in ("architect", "product_owner", "engineer", "qa", "project_manager"):
        assert f"role_models_{role}" in ctx
        assert ctx[f"role_models_{role}"] == ""


def test_build_context_role_models_from_config(tmp_path: Path):
    """_build_context passes per-role model overrides from config."""
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    cfg.native.role_models = {"architect": "gpt-4.1", "qa": "o3-mini"}
    ctx = _build_context(cfg)
    assert ctx["role_models_architect"] == "gpt-4.1"
    assert ctx["role_models_qa"] == "o3-mini"
    assert ctx["role_models_engineer"] == ""


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
    assert "evaluation-r*.md" in content
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


# --- StrictUndefined template validation ---


def test_templates_have_no_undefined_variables(tmp_path: Path):
    """All templates render without UndefinedError when given the full context."""
    import jinja2
    from harness.native.skill_gen import _build_context, _get_template_dir

    cfg = _make_cfg(tmp_path)
    tmpl_dir = _get_template_dir()
    context = _build_context(cfg)

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
    assert "From Idea to PR" in content


def test_brainstorm_updates_vision(tmp_path: Path):
    """brainstorm template includes vision.md update step via _vision-core."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "vision.md" in content
    assert "Update Vision" in content


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
    """Each role agent has Memverse integration section."""
    cfg = _make_cfg(tmp_path)
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
    generate_native_artifacts(tmp_path, cfg=cfg)
    arch = (tmp_path / ".cursor" / "agents" / "harness-architect.md").read_text(encoding="utf-8")
    assert "gpt-4.1" in arch


# --- Recursive composition ---


def test_brainstorm_includes_vision_core(tmp_path: Path):
    """brainstorm recursively includes _vision-core content."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "Update Vision" in content


def test_brainstorm_includes_plan_core(tmp_path: Path):
    """brainstorm recursively includes _plan-core content (via vision-content → plan-content)."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "Plan Generation" in content
    assert "Produce Spec + Contract" in content


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


def test_brainstorm_includes_ship_invocation(tmp_path: Path):
    """brainstorm includes the ship invocation at the end of plan-content."""
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
