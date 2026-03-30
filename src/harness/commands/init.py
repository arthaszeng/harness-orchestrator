"""harness init — smart project initialization wizard"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import jinja2
import typer

from harness.core.scanner import ProjectScan, format_scan_report, scan_project
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


# ── Step 2: IDE environment ───────────────────────────────────────

def _step_ide_setup() -> dict[str, bool]:
    typer.echo(t("init.step2_title"))
    ides = {
        "cursor": shutil.which("cursor") is not None,
        "codex": shutil.which("codex") is not None,
    }
    cursor_st = "ok" if ides["cursor"] else t("init.ide_not_detected")
    codex_st = "ok" if ides["codex"] else t("init.ide_not_detected")
    typer.echo(t("init.cursor_status", status=cursor_st))
    typer.echo(t("init.codex_status", status=codex_st))

    if not any(ides.values()):
        typer.echo(t("init.ide_error"), err=True)
        raise typer.Exit(1)

    do_install = typer.confirm(t("init.install_agents_confirm"), default=True)
    if do_install:
        from harness.commands.install import run_install
        run_install(force=True)

    return ides


# ── Step 3: driver mode ───────────────────────────────────────────

def _step_driver_mode(ides: dict[str, bool]) -> tuple[str, dict[str, str]]:
    """Return (mode, roles_dict)."""
    typer.echo(t("init.step3_title"))

    both = ides["cursor"] and ides["codex"]
    cursor_only = ides["cursor"] and not ides["codex"]
    codex_only = ides["codex"] and not ides["cursor"]

    if both:
        typer.echo(t("init.both_detected"))
        typer.echo(t("init.opt_auto"))
        typer.echo(t("init.opt_cursor"))
        typer.echo(t("init.opt_codex"))
        choice = _prompt_choice(t("init.choose"), 3, default=1)
        mode = ["auto", "cursor", "codex"][choice - 1]
    elif cursor_only:
        typer.echo(t("init.cursor_only"))
        mode = "cursor"
    else:
        typer.echo(t("init.codex_only"))
        mode = "codex"

    roles: dict[str, str] = {}
    if mode == "auto" and both:
        roles = {
            "planner": "codex",
            "builder": "cursor",
            "evaluator": "codex",
        }

    return mode, roles


# ── Step 4: CI gate ───────────────────────────────────────────────

def _step_ci_command(
    project_root: Path,
    ides: dict[str, bool],
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

        ai_idx = len(suggestions) + 1
        custom_idx = ai_idx + 1
        typer.echo(t("init.ai_analyze", idx=ai_idx))
        typer.echo(t("init.custom_input", idx=custom_idx))

        choice = _prompt_choice(t("init.choose"), custom_idx, default=1)

        if choice <= len(suggestions):
            selected = suggestions[choice - 1][0]
            typer.echo(f"  -> {selected}")
            return selected
        if choice == ai_idx:
            return _ai_suggest_ci(project_root, ides, scan)
        return typer.prompt(t("init.enter_ci"))
    typer.echo(t("init.no_suggestions"))
    typer.echo(t("init.opt_ai_analyze"))
    typer.echo(t("init.opt_custom"))
    typer.echo(t("init.opt_skip"))
    choice = _prompt_choice(t("init.choose"), 3, default=1)

    if choice == 1:
        return _ai_suggest_ci(project_root, ides, scan)
    if choice == 2:
        return typer.prompt(t("init.enter_ci"))
    return ""


def _ai_suggest_ci(
    project_root: Path, ides: dict[str, bool], scan: ProjectScan,
) -> str:
    """Use an AI agent to analyze the project and suggest a CI command."""
    from harness.drivers.codex import CodexDriver
    from harness.drivers.cursor import CursorDriver

    driver = None
    if ides.get("codex"):
        driver = CodexDriver()
    elif ides.get("cursor"):
        driver = CursorDriver()

    if not driver:
        typer.echo(t("init.ai_no_ide"))
        return typer.prompt(t("init.enter_ci"), default="make test")

    report_lines = format_scan_report(scan)
    report_text = "\n".join(f"- {l}" for l in report_lines) if report_lines else "(none)"

    prompt = t(
        "prompt.ai_ci",
        project_root=str(project_root),
        report=report_text,
    )

    typer.echo(t("init.ai_analyzing"))
    t0 = time.monotonic()
    result = driver.invoke("harness-advisor", prompt, project_root, readonly=True, timeout=120)
    elapsed = time.monotonic() - t0
    typer.echo(t("init.ai_done", elapsed=elapsed))

    if result.success and result.output.strip():
        for line in result.output.strip().split("\n"):
            line = line.strip().strip("`").strip()
            if line and not line.startswith("#"):
                typer.echo(t("init.ai_recommend", line=line))
                use_it = typer.confirm(t("init.use_command"), default=True)
                if use_it:
                    return line
                break

    return typer.prompt(t("init.enter_ci"), default="make test")


# ── Step 5: Memverse ──────────────────────────────────────────────

def _step_memverse(
    project_root: Path,
    driver_mode: str,
) -> tuple[bool, str, str]:
    """Return (enabled, driver, domain_prefix)."""
    typer.echo(t("init.step5_title"))
    typer.echo(t("init.memverse_desc"))
    typer.echo(t("init.opt_enable"))
    typer.echo(t("init.opt_disable"))
    choice = _prompt_choice(t("init.choose"), 2, default=2)

    if choice == 2:
        return False, "auto", ""

    mv_driver = driver_mode
    typer.echo(t("init.memverse_driver", mode=driver_mode))
    typer.echo(t("init.memverse_all_ides"))

    domain = typer.prompt(t("init.domain_prefix"), default=project_root.name)

    return True, mv_driver, domain


# ── Step 6: Vision ────────────────────────────────────────────────

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
        ides = {
            "cursor": shutil.which("cursor") is not None,
            "codex": shutil.which("codex") is not None,
        }
        driver_mode = "auto"
        roles: dict[str, str] = {}
        ci = ci_command or "make test"
        memverse_enabled, memverse_driver, memverse_domain = False, "auto", ""
        launch_vision = False
    else:
        proj_name, description = _step_project_info(project_root, name_override=name)
        ides = _step_ide_setup()
        driver_mode, roles = _step_driver_mode(ides)
        ci = _step_ci_command(project_root, ides, ci_override=ci_command)
        memverse_enabled, memverse_driver, memverse_domain = _step_memverse(
            project_root, driver_mode,
        )
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
        driver_mode=driver_mode,
        roles=roles,
        memverse_enabled="true" if memverse_enabled else "false",
        memverse_driver=memverse_driver,
        memverse_domain=memverse_domain,
    )
    (agents_dir / "config.toml").write_text(config_content, encoding="utf-8")

    vision_path = agents_dir / "vision.md"
    if not vision_path.exists() and not launch_vision:
        vision_tmpl_name = "vision.zh.md.j2" if lang_norm == "zh" else "vision.md.j2"
        tmpl = _load_template(vision_tmpl_name)
        vision_content = tmpl.render(project_name=proj_name)
        vision_path.write_text(vision_content, encoding="utf-8")

    _update_gitignore(project_root)

    typer.echo(t("init.done"))
    typer.echo(t("init.config_generated"))
    if not launch_vision and vision_path.exists():
        typer.echo(t("init.vision_generated"))
    typer.echo(t("init.gitignore_updated"))
    typer.echo(t("init.next_auto"))
    typer.echo(t("init.next_status"))

    if launch_vision:
        typer.echo(t("init.launch_vision"))
        from harness.commands.vision_cmd import run_vision
        run_vision()


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
