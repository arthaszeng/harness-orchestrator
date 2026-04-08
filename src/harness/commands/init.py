"""harness init — project initialization wizard + reinit mode"""

from __future__ import annotations

import subprocess
from pathlib import Path

import jinja2
import typer

from harness.core.scanner import format_scan_report, scan_project
from harness.core.model_selection import detect_cursor_recent_models, validate_model_name
from harness.core.ui import get_ui
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


def _cyber_step(console, step: int, total: int, title: str) -> None:
    """Print a cyberpunk-styled step header."""
    from rich.rule import Rule
    console.print()
    console.print(Rule(
        f"[cyber.magenta]◆ {t('init.step_label', step=step, total=total)}[/]  [cyber.cyan]{title}[/]",
        style="cyber.dim",
    ))


# ── Step 0: language selection ────────────────────────────────────

def _step_language() -> str:
    """Prompt user to choose language; returns 'en' or 'zh'."""
    console = get_ui().console
    console.print()
    console.print("  [cyber.cyan]Language / 语言:[/]")
    console.print("  [cyber.dim]1.[/] English [cyber.dim](default)[/]")
    console.print("  [cyber.dim]2.[/] 中文")
    choice = _prompt_choice("  Choose / 选择", 2, default=1)
    lang = "zh" if choice == 2 else "en"
    set_lang(lang)
    return lang


# ── Step 1: project info ──────────────────────────────────────────

def _step_project_info(
    project_root: Path, *, name_override: str = "",
) -> tuple[str, str]:
    console = get_ui().console
    _cyber_step(console, 1, 5, t("init.step1_label"))
    name = name_override or typer.prompt(
        t("init.project_name"), default=project_root.name,
    )
    description = typer.prompt(t("init.project_desc"), default="")
    return name, description


# ── Step 2: trunk branch ─────────────────────────────────────────

def _step_trunk_branch(project_root: Path) -> str:
    """Detect the current git branch and let the user confirm or change it."""
    import subprocess

    console = get_ui().console
    _cyber_step(console, 2, 5, t("init.step_trunk_label"))

    detected = "main"
    try:
        from harness.integrations.git_ops import current_branch
        branch = current_branch(project_root)
        if branch:
            detected = branch
    except (OSError, subprocess.TimeoutExpired):
        pass

    trunk = typer.prompt(t("init.trunk_prompt"), default=detected)
    return trunk


# ── Step 3: CI gate ───────────────────────────────────────────────

def _default_ci_for_non_interactive(project_root: Path) -> str:
    """First scanner suggestion, or empty string (matches interactive skip)."""
    scan = scan_project(project_root)
    if scan.suggested_commands:
        return scan.suggested_commands[0][0]
    return ""


def _step_ci_command(
    project_root: Path,
    *,
    ci_override: str = "",
) -> str:
    if ci_override:
        return ci_override

    console = get_ui().console
    _cyber_step(console, 3, 5, t("init.step4_label"))
    console.print(f"  [cyber.dim]{t('init.scanning')}[/]")

    scan = scan_project(project_root)
    report = format_scan_report(scan)

    if report:
        for line in report:
            console.print(f"    [cyber.green]▸[/] {line}")
    else:
        console.print(f"  [cyber.dim]{t('init.no_ci_found')}[/]")

    suggestions = scan.suggested_commands
    if suggestions:
        console.print(f"\n  [cyber.cyan]{t('init.recommended_ci')}[/]")
        for i, (cmd, desc) in enumerate(suggestions, 1):
            label = f" [cyber.green]{t('init.recommended_label')}[/]" if i == 1 else ""
            console.print(f"  [cyber.dim]{i}.[/] {cmd} [cyber.dim]-- {desc}[/]{label}")

        custom_idx = len(suggestions) + 1
        console.print(f"  [cyber.dim]{custom_idx}.[/] {t('init.custom_input_label')}")

        choice = _prompt_choice(t("init.choose"), custom_idx, default=1)

        if choice <= len(suggestions):
            selected = suggestions[choice - 1][0]
            console.print(f"  [cyber.green]→[/] {selected}")
            return selected
        return typer.prompt(t("init.enter_ci"))

    console.print(f"\n  [cyber.dim]{t('init.no_suggestions')}[/]")
    console.print(f"  [cyber.dim]1.[/] {t('init.custom_input_label')}")
    console.print(f"  [cyber.dim]2.[/] {t('init.skip_label')}")

    choice = _prompt_choice(t("init.choose"), 2, default=2)

    if choice == 1:
        return typer.prompt(t("init.enter_ci"))
    return ""


# ── Step 4: Memverse ──────────────────────────────────────────────

def _step_memverse(project_root: Path) -> tuple[bool, str]:
    """Return (enabled, domain_prefix)."""
    console = get_ui().console
    _cyber_step(console, 4, 5, t("init.step5_label"))
    console.print(f"  [cyber.dim]{t('init.memverse_desc')}[/]")
    console.print(f"  [cyber.dim]1.[/] {t('init.enable_label')}")
    console.print(f"  [cyber.dim]2.[/] {t('init.disable_label')} [cyber.dim](default)[/]")
    choice = _prompt_choice(t("init.choose"), 2, default=2)

    if choice == 2:
        return False, ""

    domain = typer.prompt(t("init.domain_prefix"), default=project_root.name)

    return True, domain


# ── Step 5: Evaluator Model ───────────────────────────────────────


def _step_evaluator_model() -> str:
    """Prompt user to pick evaluator model from recent Cursor models or custom input."""
    console = get_ui().console
    _cyber_step(console, 5, 5, t("init.step_evaluator_label"))
    console.print(f"  [cyber.dim]{t('init.evaluator_desc')}[/]")
    console.print(f"  [cyber.dim]{t('init.evaluator_rule_vs_agents')}[/]")
    console.print(f"  [cyber.dim]{t('init.evaluator_fallback_note')}[/]")

    recent_models = detect_cursor_recent_models()

    console.print(
        f"\n  [cyber.dim]1.[/] inherit [cyber.dim]({t('init.evaluator_inherit_hint')})[/]"
        f" [cyber.green]({t('init.recommended_label')})[/]",
    )

    next_index = 2
    for model in recent_models:
        console.print(
            f"  [cyber.dim]{next_index}.[/] {model} "
            f"[cyber.dim]({t('init.evaluator_detected_label')})[/]",
        )
        next_index += 1

    if not recent_models:
        console.print(f"  [cyber.dim]{t('init.evaluator_detected_none')}[/]")

    custom_idx = next_index
    console.print(f"  [cyber.dim]{custom_idx}.[/] {t('init.custom_input_label')}")

    choice = _prompt_choice(t("init.choose"), custom_idx, default=1)

    if choice == 1:
        return "inherit"

    list_idx = choice - 2
    if 0 <= list_idx < len(recent_models):
        selected = recent_models[list_idx]
        console.print(f"  [cyber.green]→[/] {selected}")
        return selected

    while True:
        value = typer.prompt(t("init.evaluator_prompt"), default="inherit").strip()
        if validate_model_name(value):
            return value
        console.print(f"  [cyber.fail]{t('init.evaluator_invalid')}[/]")


# ── Reinit mode ───────────────────────────────────────────────────

def _run_reinit(project_root: Path) -> None:
    """Config exists — skip wizard, regenerate artifacts from existing config."""
    from rich.panel import Panel

    from harness.core.config import HarnessConfig
    from harness.native.skill_gen import generate_native_artifacts, resolve_native_lang

    ui = get_ui()
    console = ui.console

    try:
        cfg = HarnessConfig.load(project_root)
    except Exception as exc:
        console.print(f"  [cyber.fail]✗[/] {t('init.reinit_config_error', error=str(exc))}")
        raise typer.Exit(1) from exc

    lang = resolve_native_lang(project_root)
    set_lang(lang)

    console.print()
    console.print(Panel(
        f"[cyber.cyan]{t('init.reinit_title')}[/]",
        border_style="cyber.border",
        padding=(0, 1),
    ))
    count = generate_native_artifacts(project_root, lang=lang, cfg=cfg, force=True)
    _update_gitignore(project_root)
    console.print()
    console.print(Panel(
        f"  [cyber.green]✓[/] {t('init.reinit_done', count=count)}\n"
        f"  [cyber.dim]{t('init.reinit_hint')}[/]",
        title=f"[cyber.header]{t('init.reinit_complete_title')}[/]",
        border_style="cyber.border",
        padding=(0, 1),
    ))
    console.print(f"  [cyber.yellow]✨[/] {t('init.easter_egg')}")


# ── Main flow ─────────────────────────────────────────────────────

def run_init(
    *,
    name: str = "",
    ci_command: str = "",
    non_interactive: bool = False,
    force: bool = False,
    auto_commit: bool = False,
) -> None:
    """Run the initialization wizard, or reinit with --force."""
    from harness import __version__

    project_root = Path.cwd()
    agents_dir = project_root / ".harness-flow"
    config_exists = (agents_dir / "config.toml").exists()

    ui = get_ui()
    console = ui.console
    ui.banner("init", __version__)

    git_clean_before = _git_is_clean(project_root)

    if force and config_exists:
        _run_reinit(project_root)
        return

    if config_exists and not non_interactive:
        overwrite = typer.confirm(t("init.config_exists"), default=False)
        if not overwrite:
            console.print(f"  [cyber.dim]{t('init.cancelled')}[/]")
            raise typer.Exit(0)

    if non_interactive:
        lang_norm = "en"
        set_lang(lang_norm)
    else:
        lang_norm = _step_language()

    if non_interactive:
        proj_name = name or project_root.name
        description = ""
        trunk_branch = "main"
        ci = ci_command if ci_command else _default_ci_for_non_interactive(project_root)
        memverse_enabled, memverse_domain = False, ""
        evaluator_model = "inherit"
    else:
        proj_name, description = _step_project_info(project_root, name_override=name)
        trunk_branch = _step_trunk_branch(project_root)
        ci = _step_ci_command(project_root, ci_override=ci_command)
        memverse_enabled, memverse_domain = _step_memverse(project_root)
        evaluator_model = _step_evaluator_model()

    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "tasks").mkdir(exist_ok=True)
    (agents_dir / "archive").mkdir(exist_ok=True)

    tmpl = _load_template("config.toml.j2")
    config_content = tmpl.render(
        project_name=proj_name,
        description=description,
        lang=lang_norm,
        ci_command=ci,
        evaluator_model=evaluator_model,
        trunk_branch=trunk_branch,
        gate_full_review_min=5,
        gate_summary_confirm_min=3,
        memverse_enabled="true" if memverse_enabled else "false",
        memverse_domain=memverse_domain,
    )
    (agents_dir / "config.toml").write_text(config_content, encoding="utf-8")

    vision_path = agents_dir / "vision.md"
    if not vision_path.exists():
        vision_tmpl_name = "vision.zh.md.j2" if lang_norm == "zh" else "vision.md.j2"
        tmpl = _load_template(vision_tmpl_name)
        vision_content = tmpl.render(project_name=proj_name)
        vision_path.write_text(vision_content, encoding="utf-8")

    from harness.native.skill_gen import generate_native_artifacts
    count = generate_native_artifacts(project_root, lang=lang_norm)

    _update_gitignore(project_root)

    from rich.panel import Panel
    _gen = t("init.summary_generated")
    _upd = t("init.summary_updated")
    summary_lines = [
        f"  [cyber.green]✓[/] .harness-flow/config.toml  [cyber.dim]{_gen}[/]",
    ]
    if vision_path.exists():
        summary_lines.append(
            f"  [cyber.green]✓[/] .harness-flow/vision.md    [cyber.dim]{_gen}[/]",
        )
    summary_lines.append(
        f"  [cyber.green]✓[/] .gitignore           [cyber.dim]{_upd}[/]",
    )
    summary_lines.append(
        f"  [cyber.green]✓[/] [cyber.cyan]{t('init.summary_artifacts', count=count)}[/]"
        f"  [cyber.dim]{_gen}[/]",
    )
    console.print()
    console.print(Panel(
        "\n".join(summary_lines),
        title=f"[cyber.header]{t('init.complete_title')}[/]",
        border_style="cyber.border",
        padding=(0, 1),
    ))

    console.print()
    console.print(f"  [cyber.cyan]{t('init.guide_ready')}[/]")
    console.print("  [cyber.dim]─────────────────────────────────────────────────────[/]")
    console.print(f"  [cyber.magenta]/harness-vision[/]      [cyber.dim]{t('init.guide_vision')}[/]")
    console.print(
        f"  [bold magenta]/harness-plan[/]        [cyber.dim]{t('init.guide_plan')}[/]"
        f"  [cyber.dim]({t('init.guide_default_starter')})[/]",
    )
    console.print(f"  [cyber.magenta]/harness-build[/]       [cyber.dim]{t('init.guide_build')}[/]")
    console.print(f"  [cyber.magenta]/harness-eval[/]        [cyber.dim]{t('init.guide_eval')}[/]")
    console.print(f"  [cyber.magenta]/harness-ship[/]        [cyber.dim]{t('init.guide_ship')}[/]")
    console.print("  [cyber.dim]─────────────────────────────────────────────────────[/]")

    console.print()
    console.print(f"  [cyber.yellow]▸[/] [cyber.cyan]{t('init.guide_edit_vision')}[/]")
    console.print(f"    [cyber.magenta]{t('init.guide_use_vision')}[/]")
    console.print(f"  [cyber.yellow]▸[/] [cyber.cyan]{t('init.next_step_commit_hint')}[/]")
    console.print(f"    [cyber.dim]{t('init.next_step_commit_cmd')}[/]")
    console.print(f"  [cyber.yellow]✨[/] {t('init.easter_egg')}")

    if auto_commit:
        _auto_commit_init_artifacts(project_root, git_clean_before=git_clean_before)


def _git_is_clean(project_root: Path) -> bool:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    return completed.stdout.strip() == ""


def _auto_commit_init_artifacts(project_root: Path, *, git_clean_before: bool) -> None:
    ui = get_ui()
    if not git_clean_before:
        ui.warn(t("init.auto_commit_skipped_dirty"))
        return

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        ui.warn(t("init.auto_commit_failed", error=str(exc)))
        return

    if status.returncode != 0:
        ui.warn(t("init.auto_commit_failed", error=status.stderr.strip() or "git status failed"))
        return
    if status.stdout.strip() == "":
        ui.info(t("init.auto_commit_nothing_to_commit"))
        return

    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        ui.info(t("init.auto_commit_nothing_to_commit"))
        return

    add_gi = subprocess.run(
        ["git", "add", ".gitignore"],
        capture_output=True, text=True, cwd=str(project_root), timeout=20,
    )
    if add_gi.returncode != 0:
        ui.warn(t("init.auto_commit_failed", error=add_gi.stderr.strip() or "git add .gitignore failed"))
        return

    commit = subprocess.run(
        ["git", "commit", "-m", "chore(init): gitignore harness artifacts"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
        timeout=20,
    )
    if commit.returncode != 0:
        ui.warn(t("init.auto_commit_failed", error=commit.stderr.strip() or "git commit failed"))
        return

    ui.info(t("init.auto_commit_done"))


_GITIGNORE_RULES: list[str] = [
    ".harness-flow/",
    ".cursor/skills/harness/",
    ".cursor/agents/harness-*.md",
    ".cursor/rules/harness-*.mdc",
]


def _update_gitignore(project_root: Path) -> None:
    gitignore = project_root / ".gitignore"
    comment = t("init.gitignore_comment")

    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
    else:
        content = ""

    missing = [r for r in _GITIGNORE_RULES if r not in content]
    if not missing:
        return

    has_comment = comment in content
    lines: list[str] = []
    if not has_comment:
        lines.append(f"\n{comment}")
    for rule in missing:
        lines.append(rule)

    if content and not content.endswith("\n"):
        lines[0] = "\n" + lines[0]

    gitignore.write_text(
        content + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
