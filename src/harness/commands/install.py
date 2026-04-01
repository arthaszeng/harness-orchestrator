"""harness install — generate Cursor-native mode artifacts"""

from __future__ import annotations

from pathlib import Path

import typer

from harness.core.config import HarnessConfig
from harness.i18n import get_lang, t


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


def _install_native_mode(project_root: Path, *, lang: str, force: bool = False) -> int:
    """Generate Cursor-native artifacts under .cursor/ (skills, agents, rules)."""
    from harness.native.skill_gen import generate_native_artifacts

    try:
        cfg = HarnessConfig.load(project_root)
    except Exception:
        return 0
    return generate_native_artifacts(project_root, lang=lang, cfg=cfg, force=force)


def run_install(*, force: bool = False, lang: str | None = None) -> None:
    """Regenerate native-mode Cursor artifacts for the current project."""
    resolved = _resolve_install_lang(lang)
    typer.echo(t("install.title"))
    count = _install_native_mode(Path.cwd(), lang=resolved, force=force)
    typer.echo(t("install.done", count=count))
