"""Generate Cursor-native mode artifacts (skills, subagents, rules).

Reads SSOT from roles.py + i18n prompts + config, renders Jinja2 templates,
and writes the results to .cursor/skills/harness/, .cursor/agents/,
and .cursor/rules/.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import jinja2
import typer

from harness.core.config import HarnessConfig
from harness.i18n import t


_TEMPLATE_DIR = "native"

_SKILL_TEMPLATES = [
    ("skill-plan.md.j2", "harness-plan"),
    ("skill-build.md.j2", "harness-build"),
    ("skill-eval.md.j2", "harness-eval"),
    ("skill-ship.md.j2", "harness-ship"),
    ("skill-investigate.md.j2", "harness-investigate"),
    ("skill-learn.md.j2", "harness-learn"),
    ("skill-doc-release.md.j2", "harness-doc-release"),
]

_AGENT_TEMPLATES = [
    ("agent-adversarial-reviewer.md.j2", "harness-adversarial-reviewer"),
    ("agent-evaluator.md.j2", "harness-evaluator"),
]

_RULE_TEMPLATES = [
    ("rule-trust-boundary.mdc.j2", "harness-trust-boundary"),
    ("rule-workflow.mdc.j2", "harness-workflow"),
    ("rule-fix-first.mdc.j2", "harness-fix-first"),
    ("rule-safety-guardrails.mdc.j2", "harness-safety-guardrails"),
]


def _get_template_dir() -> Path:
    pkg = importlib.resources.files("harness") / "templates" / _TEMPLATE_DIR
    return Path(str(pkg))


def _build_context(cfg: HarnessConfig) -> dict[str, str]:
    """Build the Jinja2 template context from config + i18n."""
    return {
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
    }


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


def _render_template(tmpl_dir: Path, tmpl_name: str, context: dict[str, str]) -> str:
    tmpl_path = tmpl_dir / tmpl_name
    tmpl = jinja2.Template(tmpl_path.read_text(encoding="utf-8"))
    return tmpl.render(**context)


def generate_native_artifacts(
    project_root: Path,
    *,
    lang: str = "en",
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

    typer.echo(t("native.done", count=count))
    return count


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
