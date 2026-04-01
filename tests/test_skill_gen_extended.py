"""skill_gen.py 扩展功能测试：角色裁剪、项目语言检测、hook、资源部署"""

from pathlib import Path

from harness.core.config import HarnessConfig
from harness.native.skill_gen import (
    _build_context,
    _detect_project_lang,
    generate_native_artifacts,
)


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


def test_generate_deploys_resource_files(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "make test"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    count = generate_native_artifacts(tmp_path, cfg=cfg)
    assert count >= 19

    eval_dir = tmp_path / ".cursor" / "skills" / "harness" / "harness-eval"
    assert (eval_dir / "review-checklist.md").exists()
    assert (eval_dir / "specialists" / "testing.md").exists()
    assert (eval_dir / "specialists" / "security.md").exists()
    assert (eval_dir / "specialists" / "performance.md").exists()
    assert (eval_dir / "specialists" / "red-team.md").exists()


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
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    build_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md")
    content = build_skill.read_text(encoding="utf-8")
    assert "Error Recovery Matrix" in content
    assert "Import error" in content


def test_generated_eval_includes_trust_boundary(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)

    eval_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = eval_skill.read_text(encoding="utf-8")
    assert "Trust Boundaries" in content
    assert "UNTRUSTED" in content


def test_generated_ship_includes_bypass_immunity(tmp_path: Path):
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
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


def _make_cfg(tmp_path: Path) -> HarnessConfig:
    """Helper: create a minimal config for generation tests."""
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir(exist_ok=True)
    (agents_dir / "config.toml").write_text(
        '[project]\nname = "test"\n[ci]\ncommand = "pytest"\n',
        encoding="utf-8",
    )
    return HarnessConfig.load(tmp_path)


def test_generated_ship_has_single_test_step(tmp_path: Path):
    """Ship template has Step 3 Run Tests as sole CI execution point (no duplicate CI Verification)."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "Step 3: Run Tests" in content
    assert "CI Verification" not in content


def test_generated_eval_includes_hook_points_when_configured(tmp_path: Path):
    """eval template includes hook section when hooks_post_eval is set."""
    cfg = _make_cfg(tmp_path)
    cfg.native.hooks_post_eval = "scripts/post-eval.sh"
    generate_native_artifacts(tmp_path, cfg=cfg)
    eval_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = eval_skill.read_text(encoding="utf-8")
    assert "Post-Eval Hook" in content
    assert "scripts/post-eval.sh" in content


def test_generated_eval_no_hook_residue_when_empty(tmp_path: Path):
    """eval template omits hook section when no hooks configured."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    eval_skill = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = eval_skill.read_text(encoding="utf-8")
    assert "Post-Eval Hook" not in content


def test_generated_evaluator_agent_has_rust_lang_review(tmp_path: Path):
    """evaluator agent template includes Rust review focus for Rust projects."""
    cfg = _make_cfg(tmp_path)
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    cfg = HarnessConfig.load(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    evaluator = (tmp_path / ".cursor" / "agents" / "harness-evaluator.md")
    content = evaluator.read_text(encoding="utf-8")
    assert "Rust-Specific Review Focus" in content
    assert "unwrap()" in content


def test_generated_ship_advisory_mode(tmp_path: Path):
    """ship Step 6 uses advisory wording when review_gate=advisory."""
    cfg = _make_cfg(tmp_path)
    cfg.native.review_gate = "advisory"
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "advisory mode" in content
    assert "does not block" in content


def test_generated_evaluator_has_output_contract(tmp_path: Path):
    """agent-evaluator uses _output-format-eval section partial."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    evaluator = (tmp_path / ".cursor" / "agents" / "harness-evaluator.md")
    content = evaluator.read_text(encoding="utf-8")
    assert "Output Contract" in content
    assert "VALIDATION RULES" in content


def test_generated_build_no_hook_residue_when_empty(tmp_path: Path):
    """build template has clean formatting when no hooks are set."""
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
    """review-checklist uses main..HEAD, not origin/main."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    checklist = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "review-checklist.md")
    content = checklist.read_text(encoding="utf-8")
    assert "git diff main..HEAD" in content
    assert "origin/main" not in content


def test_retro_uses_real_template_path(tmp_path: Path):
    """retro template references actual file path, not fictional one."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    retro = (tmp_path / ".cursor" / "skills" / "harness" / "harness-retro" / "SKILL.md")
    content = retro.read_text(encoding="utf-8")
    assert "src/harness/templates/ship.j2" not in content
    assert "skill-ship.md.j2" in content


def test_ship_has_eval_artifact_gate(tmp_path: Path):
    """ship template contains the eval artifact gate before Step 6."""
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
    """ship pre-flight includes eval readiness reminder with TODO template."""
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
    """ship Important Rules section puts eval-skip prevention first."""
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


# --- New tests for v2.3 audit fixes ---


def test_retro_uses_config_window_days(tmp_path: Path):
    """retro template uses retro_window_days variable, not literal N."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    retro = (tmp_path / ".cursor" / "skills" / "harness" / "harness-retro" / "SKILL.md")
    content = retro.read_text(encoding="utf-8")
    assert '"N days ago"' not in content
    assert "14 days ago" in content


def test_retro_custom_window_days(tmp_path: Path):
    """retro template respects custom retro_window_days from config."""
    cfg = _make_cfg(tmp_path)
    cfg.native.retro_window_days = 30
    generate_native_artifacts(tmp_path, cfg=cfg)
    retro = (tmp_path / ".cursor" / "skills" / "harness" / "harness-retro" / "SKILL.md")
    content = retro.read_text(encoding="utf-8")
    assert "30 days ago" in content


def test_eval_has_context_degradation_ladder(tmp_path: Path):
    """eval template includes the context degradation ladder in Step 0."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "Context Degradation Ladder" in content
    assert "Minimum viable eval" in content
    assert "FATAL" in content


def test_eval_degradation_matrix_before_step1(tmp_path: Path):
    """eval degradation matrix appears before Step 1, not at the end."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "Degradation Matrix" in content
    matrix_pos = content.index("Degradation Matrix")
    step1_pos = content.index("Step 1:")
    assert matrix_pos < step1_pos, "Degradation matrix must appear before Step 1"


def test_eval_uses_minimal_interaction_wording(tmp_path: Path):
    """eval template says minimal-interaction, not non-interactive."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "minimal-interaction" in content
    assert "non-interactive" not in content


def test_plan_is_end_to_end(tmp_path: Path):
    """plan template is end-to-end (includes execution pipeline), not plan-only."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "Autonomous Execution Pipeline" in content
    assert "From Requirement to PR" in content
    assert "Phase: Build" in content
    assert "Phase: Ship" in content


def test_ship_uses_minimal_interaction_wording(tmp_path: Path):
    """ship template says minimal-interaction, not non-interactive."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "minimal-interaction" in content
    assert "non-interactive" not in content


def test_eval_dispatches_evaluator_subagent(tmp_path: Path):
    """eval template dispatches harness-evaluator via Task tool instead of inline review."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "harness-evaluator" in content
    assert "Dispatch Reviewers" in content
    assert "(you, the main agent)" not in content


def test_evaluator_agent_has_full_methodology(tmp_path: Path):
    """evaluator agent template contains review checklist ref, finding schema, coverage check."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    evaluator = (tmp_path / ".cursor" / "agents" / "harness-evaluator.md")
    content = evaluator.read_text(encoding="utf-8")
    assert "review-checklist.md" in content
    assert "confidence" in content
    assert "Coverage Spot-Check" in content
    assert "Finding Classification" in content


def test_evaluator_agent_python_lang(tmp_path: Path):
    """evaluator agent includes Python-specific review for Python projects."""
    cfg = _make_cfg(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    cfg = HarnessConfig.load(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    evaluator = (tmp_path / ".cursor" / "agents" / "harness-evaluator.md")
    content = evaluator.read_text(encoding="utf-8")
    assert "Python-Specific Review Focus" in content


def test_ship_dispatches_evaluator_subagent(tmp_path: Path):
    """ship Step 3.8 dispatches harness-evaluator instead of inline Pass 1."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "harness-evaluator" in content
    assert "Structured review using the review checklist" not in content


def test_no_claude_references_in_templates(tmp_path: Path):
    """No 'Claude' (capital C) references remain in generated skills or agents."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    cursor_dir = tmp_path / ".cursor"
    for md_file in cursor_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        assert "Claude" not in content, f"Found 'Claude' in {md_file.relative_to(tmp_path)}"


def test_mechanism_subagent_mode(tmp_path: Path):
    """eval template shows subagent-only mode dispatch block when mechanism=subagent."""
    cfg = _make_cfg(tmp_path)
    cfg.native.adversarial_mechanism = "subagent"
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "subagent-only mode" in content
    assert "Adversarial dispatch: auto mode" not in content
    assert "Adversarial dispatch: CLI mode" not in content


def test_mechanism_cli_mode(tmp_path: Path):
    """eval template shows CLI mode dispatch block when mechanism=cli."""
    cfg = _make_cfg(tmp_path)
    cfg.native.adversarial_mechanism = "cli"
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "Adversarial dispatch: CLI mode" in content
    assert "subagent-only mode" not in content
    assert "Adversarial dispatch: auto mode" not in content


def test_mechanism_auto_mode_default(tmp_path: Path):
    """eval template shows auto mode dispatch block by default (mechanism=auto)."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    ev = (tmp_path / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md")
    content = ev.read_text(encoding="utf-8")
    assert "Adversarial dispatch: auto mode" in content


def test_ship_mechanism_branches(tmp_path: Path):
    """ship Step 3.8 also has mechanism branching matching eval."""
    cfg = _make_cfg(tmp_path)
    cfg.native.adversarial_mechanism = "subagent"
    generate_native_artifacts(tmp_path, cfg=cfg)
    ship = (tmp_path / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md")
    content = ship.read_text(encoding="utf-8")
    assert "subagent-only mode" in content


def test_error_recovery_no_test_overlap(tmp_path: Path):
    """error recovery partial does not duplicate test failure triage."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    build = (tmp_path / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md")
    content = build.read_text(encoding="utf-8")
    assert "Error Recovery Matrix" in content
    matrix_start = content.index("Error Recovery Matrix")
    matrix_section = content[matrix_start:matrix_start + 500]
    assert "CI failure (test)" not in matrix_section


def test_jinja_env_cache_shared(tmp_path: Path):
    """_get_jinja_env returns the same Environment instance for same path."""
    from harness.native.skill_gen import _get_jinja_env
    tmpl_dir = str(tmp_path.resolve())
    (tmp_path / "dummy.j2").write_text("hello", encoding="utf-8")
    env1 = _get_jinja_env(tmpl_dir)
    env2 = _get_jinja_env(tmpl_dir)
    assert env1 is env2


def test_config_rejects_invalid_mechanism(tmp_path: Path):
    """NativeModeConfig rejects invalid adversarial_mechanism values."""
    import pydantic
    from harness.core.config import NativeModeConfig
    with __import__("pytest").raises(pydantic.ValidationError):
        NativeModeConfig(adversarial_mechanism="invalid_value")


def test_config_rejects_invalid_review_gate(tmp_path: Path):
    """NativeModeConfig rejects invalid review_gate values."""
    import pydantic
    from harness.core.config import NativeModeConfig
    with __import__("pytest").raises(pydantic.ValidationError):
        NativeModeConfig(review_gate="invalid_value")


def test_templates_have_no_undefined_variables(tmp_path: Path):
    """All templates render without UndefinedError when given the full context.

    Uses StrictUndefined to catch typos that the lenient prod mode would silently swallow.
    """
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


# --- v3.0: Three entry points + review gate + execution pipeline ---


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
    """brainstorm template includes vision.md update step."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "vision.md" in content
    assert "Converge on Vision" in content


def test_brainstorm_includes_execution_pipeline(tmp_path: Path):
    """brainstorm template includes the shared autonomous execution pipeline."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    bs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-brainstorm" / "SKILL.md")
    content = bs.read_text(encoding="utf-8")
    assert "Autonomous Execution Pipeline" in content
    assert "Phase: Build" in content
    assert "Phase: Eval" in content
    assert "Phase: Ship" in content
    assert "Phase: Auto-Retro" in content


def test_vision_has_clarification_phase(tmp_path: Path):
    """vision template includes clarification step for ambiguous direction."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    vs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-vision" / "SKILL.md")
    content = vs.read_text(encoding="utf-8")
    assert "Vision Clarification" in content
    assert "From Direction to PR" in content


def test_vision_includes_execution_pipeline(tmp_path: Path):
    """vision template includes the shared autonomous execution pipeline."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    vs = (tmp_path / ".cursor" / "skills" / "harness" / "harness-vision" / "SKILL.md")
    content = vs.read_text(encoding="utf-8")
    assert "Autonomous Execution Pipeline" in content
    assert "Phase: Build" in content
    assert "Phase: Auto-Retro" in content


def test_all_three_entry_points_include_review_gate(tmp_path: Path):
    """All 3 entry point skills include the review gate section."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    skills_base = tmp_path / ".cursor" / "skills" / "harness"
    for name in ("harness-brainstorm", "harness-vision", "harness-plan"):
        content = (skills_base / name / "SKILL.md").read_text(encoding="utf-8")
        assert "Review Gate" in content, f"Missing Review Gate in {name}"


def test_review_gate_auto_has_scoring_table(tmp_path: Path):
    """auto mode review gate includes the escalation scoring table."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "escalation score" in content
    assert "FULL REVIEW" in content
    assert "SUMMARY CONFIRM" in content
    assert "AUTO PROCEED" in content


def test_review_gate_auto_has_interaction_depth(tmp_path: Path):
    """auto mode review gate shows the correct interaction depth per entry point."""
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
    """human mode review gate tells agent to stop and wait."""
    cfg = _make_cfg(tmp_path)
    cfg.native.plan_review_gate = "human"
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "**STOP.**" in content
    assert "SUMMARY CONFIRM" not in content


def test_review_gate_ai_auto_proceeds(tmp_path: Path):
    """ai mode review gate proceeds without human gate."""
    cfg = _make_cfg(tmp_path)
    cfg.native.plan_review_gate = "ai"
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "auto-approved after adversarial review" in content
    assert "**STOP.**" not in content
    assert "escalation score" not in content


def test_execution_pipeline_has_auto_retro(tmp_path: Path):
    """execution pipeline includes lightweight auto-retro phase."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "Auto-Retro" in content
    assert "add_memories" in content
    assert "cycles.jsonl" in content
    assert "< 30 seconds" in content


def test_execution_pipeline_has_hooks(tmp_path: Path):
    """execution pipeline renders hook points when configured."""
    cfg = _make_cfg(tmp_path)
    cfg.native.hooks_pre_build = "scripts/pre-build.sh"
    cfg.native.hooks_pre_ship = "scripts/pre-ship.sh"
    generate_native_artifacts(tmp_path, cfg=cfg)
    plan = (tmp_path / ".cursor" / "skills" / "harness" / "harness-plan" / "SKILL.md")
    content = plan.read_text(encoding="utf-8")
    assert "scripts/pre-build.sh" in content
    assert "scripts/pre-ship.sh" in content


def test_config_plan_review_gate_literal(tmp_path: Path):
    """NativeModeConfig rejects invalid plan_review_gate values."""
    import pydantic
    from harness.core.config import NativeModeConfig
    with __import__("pytest").raises(pydantic.ValidationError):
        NativeModeConfig(plan_review_gate="invalid_value")


def test_config_plan_review_gate_defaults_to_auto():
    """plan_review_gate defaults to 'auto'."""
    from harness.core.config import NativeModeConfig
    cfg = NativeModeConfig()
    assert cfg.plan_review_gate == "auto"


def test_build_context_has_plan_review_gate(tmp_path: Path):
    """_build_context includes plan_review_gate in the template context."""
    cfg = HarnessConfig()
    cfg.project_root = tmp_path
    ctx = _build_context(cfg)
    assert "plan_review_gate" in ctx
    assert ctx["plan_review_gate"] == "auto"


def test_total_skill_count_is_ten(tmp_path: Path):
    """10 skills are generated (3 primary + 7 existing)."""
    cfg = _make_cfg(tmp_path)
    generate_native_artifacts(tmp_path, cfg=cfg)
    skills_dir = tmp_path / ".cursor" / "skills" / "harness"
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
    assert len(skill_dirs) == 10
