"""harness install — install agent definitions to local IDE"""

from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path

import typer

from harness.core.config import HarnessConfig
from harness.i18n import get_lang, t

# agent file → target path mapping
_CURSOR_AGENTS = {
    "builder.md": "harness-builder.md",
    "reflector.md": "harness-reflector.md",
}
_CODEX_AGENTS = {
    "planner.toml": "harness-planner.toml",
    "evaluator.toml": "harness-evaluator.toml",
    "strategist.toml": "harness-strategist.toml",
    "reflector.toml": "harness-reflector.toml",
    "advisor.toml": "harness-advisor.toml",
    "alignment_evaluator.toml": "harness-alignment-evaluator.toml",
}


def _agents_pkg_dir() -> Path:
    """Return the packaged agents/ directory path."""
    pkg = importlib.resources.files("harness")
    return Path(str(pkg)).parent.parent / "agents"


def _resolve_install_lang(lang: str | None) -> str:
    """Pick install language: explicit arg, then config, then UI lang, else en."""
    if lang is not None:
        return lang if lang in ("en", "zh") else "en"
    try:
        cfg = HarnessConfig.load()
        pl = cfg.project.lang
        if pl in ("en", "zh"):
            return pl
    except Exception:
        pass
    gl = get_lang()
    return gl if gl in ("en", "zh") else "en"


def _detect_ide() -> dict[str, bool]:
    """Detect locally installed IDE CLIs."""
    return {
        "cursor": shutil.which("cursor") is not None,
        "codex": shutil.which("codex") is not None,
    }


def _install_cursor_agents(source_dir: Path, *, force: bool, lang: str) -> int:
    """Install Cursor agent definitions."""
    target_dir = Path.home() / ".cursor" / "agents"
    target_dir.mkdir(parents=True, exist_ok=True)

    installed = 0
    src_dir = source_dir / "cursor"
    if lang == "zh":
        zh_dir = src_dir / "zh"
        if zh_dir.is_dir():
            src_dir = zh_dir
    for src_name, dst_name in _CURSOR_AGENTS.items():
        src = src_dir / src_name
        dst = target_dir / dst_name
        if not src.exists():
            typer.echo(t("install.warn_missing", src=src), err=True)
            continue
        if dst.exists() and not force:
            typer.echo(t("install.skip_exists", dst=dst))
            continue
        shutil.copy2(src, dst)
        typer.echo(f"  [ok] {dst}")
        installed += 1
    return installed


def _install_codex_agents(source_dir: Path, *, force: bool, lang: str) -> int:
    """Install Codex agent definitions."""
    target_dir = Path.home() / ".codex" / "agents"
    target_dir.mkdir(parents=True, exist_ok=True)

    installed = 0
    src_dir = source_dir / "codex"
    if lang == "zh":
        zh_dir = src_dir / "zh"
        if zh_dir.is_dir():
            src_dir = zh_dir
    for src_name, dst_name in _CODEX_AGENTS.items():
        src = src_dir / src_name
        dst = target_dir / dst_name
        if not src.exists():
            typer.echo(t("install.warn_missing", src=src), err=True)
            continue
        if dst.exists() and not force:
            typer.echo(t("install.skip_exists", dst=dst))
            continue
        shutil.copy2(src, dst)
        typer.echo(f"  [ok] {dst}")
        installed += 1
    return installed


def _probe_ides(ides: dict[str, bool]) -> dict[str, bool]:
    """Run functional probes and display status with guidance for non-ready CLIs.

    Returns a dict with functional readiness (may downgrade True → False).
    """
    from harness.drivers.codex import CodexDriver
    from harness.drivers.cursor import CursorDriver

    ready = dict(ides)
    if ides["cursor"]:
        probe = CursorDriver().probe()
        if probe.available:
            typer.echo(t("install.cursor_ok"))
        else:
            typer.echo(t("install.cursor_not_ready"))
            ready["cursor"] = False
    else:
        typer.echo(t("install.cursor_missing"))

    if ides["codex"]:
        probe = CodexDriver().probe()
        if probe.available:
            typer.echo(t("install.codex_ok"))
        else:
            typer.echo(t("install.codex_not_ready"))
            ready["codex"] = False
    else:
        typer.echo(t("install.codex_missing"))

    return ready


def run_install(*, force: bool = False, lang: str | None = None) -> None:
    """Run install: preflight, then copy agent files."""
    resolved = _resolve_install_lang(lang)
    typer.echo(t("install.title"))

    ides = _detect_ide()
    typer.echo(t("install.env_check"))
    _probe_ides(ides)

    if not any(ides.values()):
        typer.echo(t("install.no_ide"), err=True)
        raise typer.Exit(1)

    source_dir = _agents_pkg_dir()
    if not source_dir.exists():
        typer.echo(t("install.no_source", path=source_dir), err=True)
        raise typer.Exit(1)

    total = 0
    typer.echo()

    if ides["cursor"]:
        typer.echo(t("install.cursor_agents"))
        total += _install_cursor_agents(source_dir, force=force, lang=resolved)

    if ides["codex"]:
        typer.echo(t("install.codex_agents"))
        total += _install_codex_agents(source_dir, force=force, lang=resolved)

    typer.echo(t("install.done", count=total))
