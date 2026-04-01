"""harness init — smart project initialization wizard"""

from __future__ import annotations

from pathlib import Path

import jinja2
import typer

from harness.core.scanner import format_scan_report, scan_project
from harness.i18n import set_lang, t


def _load_template(name: str) -> jinja2.Template:
    import importlib.resources
    pkg = importlib.resources.files("harness") / "templates"
    tmpl_path = Path(str(pkg)) / name
    return jinja2.Template(tmpl_path.read_text(encoding="utf-8"))


def _prompt_choice(prompt_text: str, n_options: int, default: int = 1) -> int:
    """Numbered choice prompt; returns 1-based option index."""
    while True:
        raw = typer.prompt(prompt_text, default=str(default)).strip()
        try:
            choice = int(raw)
            if 1 <= choice <= n_options:
                return choice
        except ValueError:
            pass
        typer.echo(t("init.enter_range", n=n_options))


# ── Step 0: language selection ────────────────────────────────────

def _step_language() -> str:
    """Prompt user to choose language; returns 'en' or 'zh'."""
    typer.echo("\n  Language / 语言:")
    typer.echo("  1. English (default)")
    typer.echo("  2. 中文")
    choice = _prompt_choice("  Choose / 选择", 2, default=1)
    lang = "zh" if choice == 2 else "en"
    set_lang(lang)
    return lang


# ── Step 1: project info ──────────────────────────────────────────

def _step_project_info(
    project_root: Path, *, name_override: str = "",
) -> tuple[str, str]:
    typer.echo(t("init.step1_title"))
    name = name_override or typer.prompt(
        t("init.project_name"), default=project_root.name,
    )
    description = typer.prompt(t("init.project_desc"), default="")
    return name, description


# ── Step 2: trunk branch ─────────────────────────────────────────

def _step_trunk_branch(project_root: Path) -> str:
    """Detect the current git branch and let the user confirm or change it."""
    import subprocess

    typer.echo(t("init.step_trunk_title"))

    detected = "main"
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=str(project_root), timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            detected = result.stdout.strip()
    except Exception:
        pass

    trunk = typer.prompt(t("init.trunk_prompt"), default=detected)
    return trunk


# ── Step 3: CI gate ───────────────────────────────────────────────

def _step_ci_command(
    project_root: Path,
    *,
    ci_override: str = "",
) -> str:
    if ci_override:
        return ci_override

    typer.echo(t("init.step4_title"))
    typer.echo(t("init.scanning"))

    scan = scan_project(project_root)
    report = format_scan_report(scan)

    if report:
        for line in report:
            typer.echo(t("init.found", line=line))
    else:
        typer.echo(t("init.no_ci_found"))

    suggestions = scan.suggested_commands
    if suggestions:
        typer.echo(t("init.recommended_ci"))
        for i, (cmd, desc) in enumerate(suggestions, 1):
            label = t("init.recommended_label") if i == 1 else ""
            typer.echo(f"  {i}. {cmd} -- {desc}{label}")

        custom_idx = len(suggestions) + 1
        typer.echo(t("init.custom_input", idx=custom_idx))

        choice = _prompt_choice(t("init.choose"), custom_idx, default=1)

        if choice <= len(suggestions):
            selected = suggestions[choice - 1][0]
            typer.echo(f"  -> {selected}")
            return selected
        return typer.prompt(t("init.enter_ci"))

    typer.echo(t("init.no_suggestions"))
    typer.echo(t("init.custom_input", idx=1))
    skip_label = t("init.opt_skip").replace("3.", "2.", 1)
    typer.echo(skip_label)

    choice = _prompt_choice(t("init.choose"), 2, default=2)

    if choice == 1:
        return typer.prompt(t("init.enter_ci"))
    return ""


# ── Step 4: Memverse ──────────────────────────────────────────────

def _step_memverse(project_root: Path) -> tuple[bool, str]:
    """Return (enabled, domain_prefix)."""
    typer.echo(t("init.step5_title"))
    typer.echo(t("init.memverse_desc"))
    typer.echo(t("init.opt_enable"))
    typer.echo(t("init.opt_disable"))
    choice = _prompt_choice(t("init.choose"), 2, default=2)

    if choice == 2:
        return False, ""

    domain = typer.prompt(t("init.domain_prefix"), default=project_root.name)

    return True, domain


# ── Step 5: Vision ────────────────────────────────────────────────

def _step_vision(agents_dir: Path) -> bool:
    """Return True if the user chose to generate vision now."""
    typer.echo(t("init.step6_title"))
    typer.echo(t("init.opt_vision_now"))
    typer.echo(t("init.opt_vision_later"))
    choice = _prompt_choice(t("init.choose"), 2, default=1)
    return choice == 1


# ── Main flow ─────────────────────────────────────────────────────

def run_init(
    *,
    name: str = "",
    ci_command: str = "",
    non_interactive: bool = False,
) -> None:
    """Run the smart initialization wizard."""
    project_root = Path.cwd()
    agents_dir = project_root / ".agents"

    if non_interactive:
        lang_norm = "en"
        set_lang(lang_norm)
    else:
        lang_norm = _step_language()

    if (agents_dir / "config.toml").exists():
        overwrite = typer.confirm(
            t("init.config_exists"), default=False,
        )
        if not overwrite:
            typer.echo(t("init.cancelled"))
            raise typer.Exit(0)

    typer.echo(t("init.wizard_title"))

    if non_interactive:
        proj_name = name or project_root.name
        description = ""
        trunk_branch = "main"
        ci = ci_command or "make test"
        memverse_enabled, memverse_domain = False, ""
        launch_vision = False
    else:
        proj_name, description = _step_project_info(project_root, name_override=name)
        trunk_branch = _step_trunk_branch(project_root)
        ci = _step_ci_command(project_root, ci_override=ci_command)
        memverse_enabled, memverse_domain = _step_memverse(project_root)
        launch_vision = _step_vision(agents_dir)

    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "tasks").mkdir(exist_ok=True)
    (agents_dir / "archive").mkdir(exist_ok=True)

    tmpl = _load_template("config.toml.j2")
    config_content = tmpl.render(
        project_name=proj_name,
        description=description,
        lang=lang_norm,
        ci_command=ci,
        adversarial_model="gpt-4.1",
        trunk_branch=trunk_branch,
        gate_full_review_min=5,
        gate_summary_confirm_min=3,
        memverse_enabled="true" if memverse_enabled else "false",
        memverse_domain=memverse_domain,
    )
    (agents_dir / "config.toml").write_text(config_content, encoding="utf-8")

    vision_path = agents_dir / "vision.md"
    if not vision_path.exists() and not launch_vision:
        vision_tmpl_name = "vision.zh.md.j2" if lang_norm == "zh" else "vision.md.j2"
        tmpl = _load_template(vision_tmpl_name)
        vision_content = tmpl.render(project_name=proj_name)
        vision_path.write_text(vision_content, encoding="utf-8")

    from harness.native.skill_gen import generate_native_artifacts
    generate_native_artifacts(project_root, lang=lang_norm)

    _update_gitignore(project_root)

    typer.echo(t("init.done"))
    typer.echo(t("init.config_generated"))
    if not launch_vision and vision_path.exists():
        typer.echo(t("init.vision_generated"))
    typer.echo(t("init.gitignore_updated"))
    typer.echo(t("native.init_hint"))
    typer.echo(t("native.hint_brainstorm"))
    typer.echo(t("native.hint_vision"))
    typer.echo(t("native.hint_plan"))
    typer.echo(t("native.hint_build"))
    typer.echo(t("native.hint_eval"))
    typer.echo(t("native.hint_ship"))
    typer.echo(t("native.hint_parallel"))

    if launch_vision:
        typer.echo(t("init.launch_vision"))
        typer.echo(t("native.hint_vision"))

    # harness vision CLI removed; native flow uses Cursor skills (see hint above)


def _update_gitignore(project_root: Path) -> None:
    gitignore = project_root / ".gitignore"
    marker = ".agents/state.json"
    comment = t("init.gitignore_comment")
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if marker not in content:
            with gitignore.open("a", encoding="utf-8") as f:
                f.write(f"\n{comment}\n")
                f.write(".agents/state.json\n")
                f.write(".agents/.stop\n")
    else:
        gitignore.write_text(
            f"{comment}\n.agents/state.json\n.agents/.stop\n",
            encoding="utf-8",
        )
