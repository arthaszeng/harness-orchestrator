"""Generate Cursor-native mode artifacts (skills, subagents, rules).

Reads SSOT from roles.py + i18n prompts + config, renders Jinja2 templates,
and writes the results to .cursor/skills/harness/, .cursor/agents/,
and .cursor/rules/.
"""

from __future__ import annotations

import functools
import importlib.resources
from pathlib import Path
from typing import Literal

import jinja2
import typer

from harness.core.config import HarnessConfig
from harness.core.model_selection import detect_cursor_recent_models, resolve_effective_model
from harness.core.roles import NATIVE_REVIEW_ROLES
from harness.i18n import get_lang, t


def resolve_native_lang(project_root: Path | None = None, lang: str | None = None) -> str:
    """Resolve language for native artifact generation.

    Priority: explicit arg → config.project.lang → current i18n lang → "en".
    """
    if lang is not None:
        return lang if lang in ("en", "zh") else "en"
    if project_root is not None:
        try:
            cfg = HarnessConfig.load(project_root)
            pl = cfg.project.lang
            if pl in ("en", "zh"):
                return pl
        except (OSError, ValueError, KeyError):
            pass
    gl = get_lang()
    return gl if gl in ("en", "zh") else "en"


_TEMPLATE_DIR = "native"

_PUBLIC_SKILL_TEMPLATES = [
    ("skill-vision.md.j2", "harness-vision"),
    ("skill-plan.md.j2", "harness-plan"),
    ("skill-ship.md.j2", "harness-ship"),
    ("skill-investigate.md.j2", "harness-investigate"),
    ("skill-learn.md.j2", "harness-learn"),
    ("skill-retro.md.j2", "harness-retro"),
]

_INTERNAL_SKILL_TEMPLATES = [
    ("skill-build.md.j2", "harness-build"),
    ("skill-eval.md.j2", "harness-eval"),
    ("skill-doc-release.md.j2", "harness-doc-release"),
]

_SKILL_TEMPLATES = _PUBLIC_SKILL_TEMPLATES + _INTERNAL_SKILL_TEMPLATES

_AGENT_TEMPLATES = [
    ("agent-architect.md.j2", "harness-architect"),
    ("agent-product-owner.md.j2", "harness-product-owner"),
    ("agent-engineer.md.j2", "harness-engineer"),
    ("agent-qa.md.j2", "harness-qa"),
    ("agent-project-manager.md.j2", "harness-project-manager"),
]

_INTERNAL_SKILL_NAMES = frozenset(name for _, name in _INTERNAL_SKILL_TEMPLATES)

_RULE_TEMPLATES = [
    ("rule-trust-boundary.mdc.j2", "harness-trust-boundary"),
    ("rule-workflow.mdc.j2", "harness-workflow"),
    ("rule-fix-first.mdc.j2", "harness-fix-first"),
    ("rule-safety-guardrails.mdc.j2", "harness-safety-guardrails"),
]

_REFERENCE_FILES: list[tuple[str, str, str, str]] = [
    # (source_path, target_skill, output_filename, mode)
    # mode: "copy" = plain file copy, "render" = Jinja2 render with full_ctx
    ("review-checklist.md", "harness-eval", "review-checklist.md", "copy"),
    ("specialists/testing.md", "harness-eval", "specialists/testing.md", "copy"),
    ("specialists/security.md", "harness-eval", "specialists/security.md", "copy"),
    ("specialists/performance.md", "harness-eval", "specialists/performance.md", "copy"),
    ("specialists/red-team.md", "harness-eval", "specialists/red-team.md", "copy"),
    ("references/code-review-protocol.md.j2", "harness-eval", "code-review-protocol.md", "render"),
    ("references/ship-pr-protocol.md.j2", "harness-ship", "ship-pr-protocol.md", "render"),
    ("references/ship-test-triage.md.j2", "harness-ship", "ship-test-triage.md", "render"),
    ("references/ship-coverage-audit.md.j2", "harness-ship", "ship-coverage-audit.md", "render"),
]


def _get_template_dir(lang: str = "en") -> Path:
    pkg = importlib.resources.files("harness") / "templates" / _TEMPLATE_DIR
    base = Path(str(pkg))
    if lang == "zh":
        zh_dir = base / "zh"
        if zh_dir.is_dir():
            return zh_dir
    return base


def _detect_project_lang(cfg: HarnessConfig) -> str:
    """Detect project language from project root markers."""
    root = cfg.project_root
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "python"
    if (root / "package.json").exists():
        return "typescript"
    if (root / "go.mod").exists():
        return "go"
    if (root / "Cargo.toml").exists():
        return "rust"
    if (root / "pom.xml").exists() or (root / "build.gradle").exists():
        return "java"
    return "unknown"


_ROLE_NAMES = tuple(sorted(NATIVE_REVIEW_ROLES))

# ---------------------------------------------------------------------------
# Layered context assembly
#
#   Layer 0 (Base)  — project-wide scalars shared by all artifacts
#   Layer 1 (Role)  — principles, per-role model selections
#   Layer 2 (Stage) — gates, hooks, thresholds (pipeline-specific)
# ---------------------------------------------------------------------------

_LAYER_KEYS: dict[int, set[str]] = {
    0: {
        "ci_command",
        "trunk_branch",
        "branch_prefix",
        "pass_threshold",
        "max_iterations",
        "project_name",
        "project_lang",
        "artifact_lang",
        "retro_window_days",
        "memverse_enabled",
        "memverse_domain",
        # role_models_* in L0: needed by dispatch tables in plan/eval/ship sections
        *(f"role_models_{rn}" for rn in sorted(NATIVE_REVIEW_ROLES)),
    },
    1: {
        "planner_principles",
        "builder_principles",
        "evaluator_model",
    },
    2: {
        "review_gate",
        "plan_review_gate",
        "hooks_pre_build",
        "hooks_post_eval",
        "hooks_pre_ship",
        "gate_full_review_min",
        "gate_summary_confirm_min",
    },
}

ArtifactType = Literal["skill", "agent", "rule"]

_ARTIFACT_LAYERS: dict[tuple[ArtifactType, str], set[int]] = {
    # Skills — layers per actual template key usage
    ("skill", "harness-vision"): {0, 1, 2},       # L1: planner_principles; L2: review_gate, hooks, gates
    ("skill", "harness-plan"): {0, 1, 2},          # L1: planner_principles; L2: plan_review_gate, gates
    ("skill", "harness-build"): {0, 1, 2},         # L1: builder_principles; L2: hooks
    ("skill", "harness-eval"): {0, 2},             # L2: hooks_post_eval; no L1 keys used
    ("skill", "harness-ship"): {0, 2},             # L2: review_gate, hooks; no L1 keys used
    ("skill", "harness-investigate"): {0},         # base only — no L1/L2 keys referenced
    ("skill", "harness-learn"): {0},               # base only — no L1/L2 keys referenced
    ("skill", "harness-doc-release"): {0},         # base only — no L1/L2 keys referenced
    ("skill", "harness-retro"): {0},               # base only — no L1/L2 keys referenced
    # Agents — base + role (no stage hooks)
    ("agent", "harness-architect"): {0, 1},
    ("agent", "harness-product-owner"): {0, 1},
    ("agent", "harness-engineer"): {0, 1},
    ("agent", "harness-qa"): {0, 1},
    ("agent", "harness-project-manager"): {0, 1},
    # Rules — base + stage (no role)
    ("rule", "harness-trust-boundary"): {0, 1, 2},
    ("rule", "harness-workflow"): {0, 2},
    ("rule", "harness-fix-first"): {0, 2},
    ("rule", "harness-safety-guardrails"): {0},
}


def _build_full_context(cfg: HarnessConfig, *, lang: str = "en") -> dict[str, str]:
    """Build the complete context with all layers."""
    rm = cfg.native.role_models
    recent_models = detect_cursor_recent_models()
    available_models = recent_models or None
    effective_evaluator_model = resolve_effective_model(
        cfg.native.evaluator_model,
        available_models=available_models,
    )
    ctx: dict[str, str] = {
        # Metadata (populated per-artifact by _build_layered_context callers)
        "context_layers": "",
        # Layer 0 — Base
        "ci_command": cfg.ci.command,
        "trunk_branch": cfg.workflow.trunk_branch,
        "branch_prefix": cfg.workflow.branch_prefix.rstrip("/"),
        "pass_threshold": str(cfg.workflow.pass_threshold),
        "max_iterations": str(cfg.workflow.max_iterations),
        "project_name": cfg.project.name,
        "project_lang": _detect_project_lang(cfg),
        "artifact_lang": lang,
        "retro_window_days": str(cfg.native.retro_window_days),
        "memverse_enabled": "true" if cfg.integrations.memverse.enabled else "false",
        "memverse_domain": (
            cfg.integrations.memverse.domain_prefix.strip()
            or cfg.project.name
            or "harness-flow"
        ),
        # Layer 1 — Role
        "evaluator_model": effective_evaluator_model or "IDE default",
        "planner_principles": _planner_principles(lang),
        "builder_principles": _builder_principles(lang),
        # Layer 2 — Stage
        "review_gate": cfg.native.review_gate,
        "plan_review_gate": cfg.native.plan_review_gate,
        "hooks_pre_build": cfg.native.hooks_pre_build,
        "hooks_post_eval": cfg.native.hooks_post_eval,
        "hooks_pre_ship": cfg.native.hooks_pre_ship,
        "gate_full_review_min": str(cfg.native.gate_full_review_min),
        "gate_summary_confirm_min": str(cfg.native.gate_summary_confirm_min),
    }

    for rn in _ROLE_NAMES:
        ctx[f"role_models_{rn}"] = resolve_effective_model(
            rm.get(rn, ""),
            cfg.native.evaluator_model,
            available_models=available_models,
        )

    return ctx


def _filter_context(
    full: dict[str, str],
    artifact_type: ArtifactType,
    artifact_name: str,
) -> dict[str, str]:
    """Filter a pre-built full context to the layers needed by one artifact.

    Raises ``KeyError`` if the artifact is not registered in ``_ARTIFACT_LAYERS``.
    Adding a new template **requires** registering it in ``_ARTIFACT_LAYERS`` to
    prevent unintended context leakage.
    """
    layers = _ARTIFACT_LAYERS.get((artifact_type, artifact_name))
    if layers is None:
        raise KeyError(
            f"Unregistered artifact ({artifact_type!r}, {artifact_name!r}). "
            "Register it in _ARTIFACT_LAYERS before rendering."
        )
    allowed_keys: set[str] = set()
    for layer_id in layers:
        allowed_keys |= _LAYER_KEYS.get(layer_id, set())
    return {k: v for k, v in full.items() if k in allowed_keys}


def _build_layered_context(
    cfg: HarnessConfig,
    artifact_type: ArtifactType,
    artifact_name: str,
    *,
    lang: str = "en",
) -> dict[str, str]:
    """Build a per-artifact context containing only the needed layers.

    Convenience wrapper that builds full context then filters.
    """
    return _filter_context(_build_full_context(cfg, lang=lang), artifact_type, artifact_name)


def _planner_principles(lang: str = "en") -> str:
    if lang == "zh":
        return (
            "1. **先做系统设计思考** — 写 Spec 之前，先识别核心挑战、必要架构约束和常见设计陷阱\n"
            "2. **交付清晰的合约** — 每个交付物必须有验收标准\n"
            "3. **先搜索再构建** — 在提出新模式之前，先检查项目已有的实现\n"
            "4. **完整性** — 在成本较低时覆盖测试、错误处理和类型安全\n"
            "5. **范围纪律** — 不添加超出需求的交付物\n"
            "6. **不做实现** — 你负责规划，Builder 负责实现"
        )
    return (
        "1. **Design thinking first** — before writing the Spec, identify core challenges, essential architectural constraints, and common design pitfalls\n"
        "2. **Deliver a clear contract** — every deliverable must have acceptance criteria\n"
        "3. **Search Before Building** — check what the project already uses before proposing new patterns\n"
        "4. **Completeness** — cover tests, error handling, and type safety when cost is small\n"
        "5. **Scope discipline** — do not add deliverables beyond the stated requirement\n"
        "6. **No implementation** — you plan, the Builder implements"
    )


def _builder_principles(lang: str = "en") -> str:
    if lang == "zh":
        return (
            "1. **严格按合约交付** — 只实现合约列出的内容\n"
            "2. **小提交** — 每个逻辑单元一个提交；格式 `<type>(scope): description`\n"
            "3. **遵循项目约定** — 写新代码前先检查已有模式\n"
            "4. **测试覆盖** — 新行为需要测试；变更必须保持现有测试通过\n"
            "5. **对照设计原则实现** — 合约中的 Design Principles 是必须满足的架构约束；实现前逐条确认"
        )
    return (
        "1. **Deliver exactly per contract** — implement only what the contract lists\n"
        "2. **Small commits** — one commit per logical unit; message format `<type>(scope): description`\n"
        "3. **Follow project conventions** — check existing patterns before writing new code\n"
        "4. **Test coverage** — new behavior needs tests; changes must keep existing tests passing\n"
        "5. **Implement against Design Principles** — the Design Principles in the contract are mandatory architectural constraints; verify each one before implementing"
    )


@functools.lru_cache(maxsize=8)
def _get_jinja_env(tmpl_dir: str, fallback_dir: str | None = None) -> jinja2.Environment:
    search_paths = [tmpl_dir]
    if fallback_dir and fallback_dir != tmpl_dir:
        search_paths.append(fallback_dir)
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(search_paths),
        undefined=jinja2.Undefined,
        keep_trailing_newline=True,
    )


def _get_base_template_dir() -> Path:
    """Return the base (en) template directory."""
    pkg = importlib.resources.files("harness") / "templates" / _TEMPLATE_DIR
    return Path(str(pkg))


def _render_template(tmpl_dir: Path, tmpl_name: str, context: dict[str, str]) -> str:
    base_dir = _get_base_template_dir()
    fallback = str(base_dir.resolve()) if tmpl_dir.resolve() != base_dir.resolve() else None
    env = _get_jinja_env(str(tmpl_dir.resolve()), fallback)
    tmpl = env.get_template(tmpl_name)
    return tmpl.render(**context)



def _cleanup_legacy_paths(project_root: Path) -> None:
    """Remove artifacts from pre-4.2 layout that would pollute the Cursor menu."""
    skills_base = project_root / ".cursor" / "skills" / "harness"
    old_agents_dir = project_root / ".cursor" / "agents"

    for skill_name in _INTERNAL_SKILL_NAMES:
        stale = skills_base / skill_name / "SKILL.md"
        if stale.is_file():
            stale.unlink()

    for _, agent_name in _AGENT_TEMPLATES:
        stale = old_agents_dir / f"{agent_name}.md"
        if stale.is_file():
            stale.unlink()

    if old_agents_dir.is_dir() and not any(old_agents_dir.iterdir()):
        old_agents_dir.rmdir()


def generate_native_artifacts(
    project_root: Path,
    *,
    lang: str = "en",
    cfg: HarnessConfig | None = None,
    force: bool = False,
) -> int:
    """Generate all Cursor-native mode artifacts. Returns count of files written."""
    if cfg is None:
        cfg = HarnessConfig.load(project_root)

    _cleanup_legacy_paths(project_root)

    tmpl_dir = _get_template_dir(lang)
    rule_activation = cfg.native.rule_activation
    full_ctx = _build_full_context(cfg, lang=lang)
    count = 0

    typer.echo(t("native.generating"))
    skipped: list[str] = []

    def _try_render_and_write(
        tmpl_name: str, artifact_name: str, out_path: Path, ctx: dict[str, str],
    ) -> bool:
        try:
            content = _render_template(tmpl_dir, tmpl_name, ctx)
            out_path.write_text(content, encoding="utf-8")
            return True
        except (jinja2.TemplateError, OSError) as exc:
            typer.echo(
                f"  [error] skipping {artifact_name}: {type(exc).__name__}: {exc}",
                err=True,
            )
            skipped.append(artifact_name)
            return False

    # Skills → .cursor/skills/harness/<name>/SKILL.md (public) or PROTOCOL.md (internal)
    skills_base = project_root / ".cursor" / "skills" / "harness"
    for tmpl_name, skill_name in _SKILL_TEMPLATES:
        skill_dir = skills_base / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        filename = "PROTOCOL.md" if skill_name in _INTERNAL_SKILL_NAMES else "SKILL.md"
        out_path = skill_dir / filename
        ctx = _filter_context(full_ctx, "skill", skill_name)
        if _try_render_and_write(tmpl_name, skill_name, out_path, ctx):
            typer.echo(t("native.generated_skill", path=_rel(project_root, out_path)))
            count += 1

    # Agents → .cursor/skills/harness/_agents/<name>.md (hidden from Cursor agent menu)
    agents_dir = skills_base / "_agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for tmpl_name, agent_name in _AGENT_TEMPLATES:
        out_path = agents_dir / f"{agent_name}.md"
        ctx = _filter_context(full_ctx, "agent", agent_name)
        ctx["context_layers"] = ",".join(
            str(i) for i in sorted(_ARTIFACT_LAYERS.get(("agent", agent_name), {0, 1}))
        )
        if _try_render_and_write(tmpl_name, agent_name, out_path, ctx):
            typer.echo(t("native.generated_agent", path=_rel(project_root, out_path)))
            count += 1

    # Rules → .cursor/rules/<name>.mdc
    rules_dir = project_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    for tmpl_name, rule_name in _RULE_TEMPLATES:
        activation = rule_activation.get(rule_name, "always")
        if activation == "disabled":
            continue
        out_path = rules_dir / f"{rule_name}.mdc"
        ctx = _filter_context(full_ctx, "rule", rule_name)
        if _try_render_and_write(tmpl_name, rule_name, out_path, ctx):
            content = out_path.read_text(encoding="utf-8")
            if activation == "phase_match":
                content = f"<!-- rule-activation: phase_match -->\n{content}"
                out_path.write_text(content, encoding="utf-8")
            typer.echo(t("native.generated_rule", path=_rel(project_root, out_path)))
            count += 1

    # Reference files → .cursor/skills/harness/<target_skill>/<filename>
    for source_path, target_skill, out_name, mode in _REFERENCE_FILES:
        target_dir = skills_base / target_skill
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / out_name
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "copy":
            src = tmpl_dir / source_path
            if not src.exists():
                typer.echo(f"  [warn] resource not found: {source_path}", err=True)
                continue
            try:
                out_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                typer.echo(t("native.generated_skill", path=_rel(project_root, out_path)))
                count += 1
            except OSError as exc:
                typer.echo(f"  [error] skipping {out_name}: {exc}", err=True)
                skipped.append(out_name)
        else:
            if _try_render_and_write(source_path, f"ref:{out_name}", out_path, full_ctx):
                typer.echo(t("native.generated_skill", path=_rel(project_root, out_path)))
                count += 1

    if skipped:
        typer.echo(
            f"  [warn] {count} files generated, {len(skipped)} skipped due to errors: "
            f"{', '.join(skipped)}",
            err=True,
        )
    typer.echo(t("native.done", count=count))
    return count



def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
