"""Generate Cursor-native mode artifacts (skills, subagents, rules).

Reads SSOT from roles.py + i18n prompts + config, renders Jinja2 templates,
and writes the results to .cursor/skills/harness/, .cursor/agents/,
and .cursor/rules/.
"""

from __future__ import annotations

import functools
import importlib.resources
from pathlib import Path

import jinja2
import typer

from harness.core.config import HarnessConfig
from harness.core.roles import NATIVE_REVIEW_ROLES
from harness.i18n import t


_TEMPLATE_DIR = "native"

_SKILL_TEMPLATES = [
    ("skill-brainstorm.md.j2", "harness-brainstorm"),
    ("skill-vision.md.j2", "harness-vision"),
    ("skill-plan.md.j2", "harness-plan"),
    ("skill-build.md.j2", "harness-build"),
    ("skill-eval.md.j2", "harness-eval"),
    ("skill-ship.md.j2", "harness-ship"),
    ("skill-investigate.md.j2", "harness-investigate"),
    ("skill-learn.md.j2", "harness-learn"),
    ("skill-doc-release.md.j2", "harness-doc-release"),
    ("skill-retro.md.j2", "harness-retro"),
]

_AGENT_TEMPLATES = [
    ("agent-architect.md.j2", "harness-architect"),
    ("agent-product-owner.md.j2", "harness-product-owner"),
    ("agent-engineer.md.j2", "harness-engineer"),
    ("agent-qa.md.j2", "harness-qa"),
    ("agent-project-manager.md.j2", "harness-project-manager"),
]

_RULE_TEMPLATES = [
    ("rule-trust-boundary.mdc.j2", "harness-trust-boundary"),
    ("rule-workflow.mdc.j2", "harness-workflow"),
    ("rule-fix-first.mdc.j2", "harness-fix-first"),
    ("rule-safety-guardrails.mdc.j2", "harness-safety-guardrails"),
]

_RESOURCE_FILES = [
    "review-checklist.md",
    "specialists/testing.md",
    "specialists/security.md",
    "specialists/performance.md",
    "specialists/red-team.md",
]


def _get_template_dir() -> Path:
    pkg = importlib.resources.files("harness") / "templates" / _TEMPLATE_DIR
    return Path(str(pkg))


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


def _build_context(cfg: HarnessConfig, *, role: str = "") -> dict[str, str]:
    """Build the Jinja2 template context from config + i18n.

    When role is specified, irrelevant variables are stripped to reduce
    token noise (inspired by Claude Code's omitClaudeMd pattern).
    """
    rm = cfg.native.role_models
    ctx: dict[str, str] = {
        "ci_command": cfg.ci.command,
        "trunk_branch": cfg.workflow.trunk_branch,
        "branch_prefix": cfg.workflow.branch_prefix,
        "pass_threshold": str(cfg.workflow.pass_threshold),
        "max_iterations": str(cfg.workflow.max_iterations),
        "adversarial_model": cfg.native.adversarial_model,
        "adversarial_mechanism": cfg.native.adversarial_mechanism,
        "planner_principles": _planner_principles(),
        "builder_principles": _builder_principles(),
        "project_name": cfg.project.name,
        "project_lang": _detect_project_lang(cfg),
        "hooks_pre_build": cfg.native.hooks_pre_build,
        "hooks_post_eval": cfg.native.hooks_post_eval,
        "hooks_pre_ship": cfg.native.hooks_pre_ship,
        "review_gate": cfg.native.review_gate,
        "plan_review_gate": cfg.native.plan_review_gate,
        "retro_window_days": str(cfg.native.retro_window_days),
        "gate_full_review_min": str(cfg.native.gate_full_review_min),
        "gate_summary_confirm_min": str(cfg.native.gate_summary_confirm_min),
    }

    for rn in _ROLE_NAMES:
        ctx[f"role_models_{rn}"] = rm.get(rn, "")

    if role == "planner":
        for key in ("builder_principles",):
            ctx.pop(key, None)

    return ctx


def _planner_principles() -> str:
    return (
        "1. **Deliver a clear contract** — every deliverable must have acceptance criteria\n"
        "2. **Search Before Building** — check what the project already uses before proposing new patterns\n"
        "3. **Completeness** — cover tests, error handling, and type safety when cost is small\n"
        "4. **Scope discipline** — do not add deliverables beyond the stated requirement\n"
        "5. **No implementation** — you plan, the Builder implements"
    )


def _builder_principles() -> str:
    return (
        "1. **Deliver exactly per contract** — implement only what the contract lists\n"
        "2. **Small commits** — one commit per logical unit; message format `<type>(scope): description`\n"
        "3. **Follow project conventions** — check existing patterns before writing new code\n"
        "4. **Test coverage** — new behavior needs tests; changes must keep existing tests passing\n"
        "5. **No architecture calls** — Planner owns architecture; you implement"
    )


@functools.lru_cache(maxsize=4)
def _get_jinja_env(tmpl_dir: str) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(tmpl_dir),
        undefined=jinja2.Undefined,
        keep_trailing_newline=True,
    )


def _render_template(tmpl_dir: Path, tmpl_name: str, context: dict[str, str]) -> str:
    env = _get_jinja_env(str(tmpl_dir.resolve()))
    tmpl = env.get_template(tmpl_name)
    return tmpl.render(**context)


def generate_native_artifacts(
    project_root: Path,
    *,
    lang: str = "en",  # reserved for future i18n
    cfg: HarnessConfig | None = None,
) -> int:
    """Generate all Cursor-native mode artifacts. Returns count of files written."""
    if cfg is None:
        cfg = HarnessConfig.load(project_root)

    tmpl_dir = _get_template_dir()
    context = _build_context(cfg)
    count = 0

    typer.echo(t("native.generating"))

    # Skills → .cursor/skills/harness/<name>/SKILL.md
    skills_base = project_root / ".cursor" / "skills" / "harness"
    for tmpl_name, skill_name in _SKILL_TEMPLATES:
        skill_dir = skills_base / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        out_path = skill_dir / "SKILL.md"
        content = _render_template(tmpl_dir, tmpl_name, context)
        out_path.write_text(content, encoding="utf-8")
        typer.echo(t("native.generated_skill", path=_rel(project_root, out_path)))
        count += 1

    # Agents → .cursor/agents/<name>.md
    agents_dir = project_root / ".cursor" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for tmpl_name, agent_name in _AGENT_TEMPLATES:
        out_path = agents_dir / f"{agent_name}.md"
        content = _render_template(tmpl_dir, tmpl_name, context)
        out_path.write_text(content, encoding="utf-8")
        typer.echo(t("native.generated_agent", path=_rel(project_root, out_path)))
        count += 1

    # Rules → .cursor/rules/<name>.mdc
    rules_dir = project_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    for tmpl_name, rule_name in _RULE_TEMPLATES:
        out_path = rules_dir / f"{rule_name}.mdc"
        content = _render_template(tmpl_dir, tmpl_name, context)
        out_path.write_text(content, encoding="utf-8")
        typer.echo(t("native.generated_rule", path=_rel(project_root, out_path)))
        count += 1

    # Resources → .cursor/skills/harness/harness-eval/<path>
    eval_resource_dir = skills_base / "harness-eval"
    eval_resource_dir.mkdir(parents=True, exist_ok=True)
    for resource_path in _RESOURCE_FILES:
        src = tmpl_dir / resource_path
        if not src.exists():
            typer.echo(f"  [warn] resource not found: {resource_path}", err=True)
            continue
        dest = eval_resource_dir / resource_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        typer.echo(t("native.generated_skill", path=_rel(project_root, dest)))
        count += 1

    typer.echo(t("native.done", count=count))
    return count


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
