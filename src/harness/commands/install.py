"""harness install — install agent definitions to local IDE"""

from __future__ import annotations

import importlib.resources
import shutil
import subprocess
import sys
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


_AGENT_BIN_DIR = Path.home() / ".local" / "bin"

def _detect_shell_rc() -> str:
    """Return the appropriate shell rc filename for the current user."""
    import os

    shell_name = Path(os.environ.get("SHELL", "/bin/bash")).name
    if shell_name == "zsh":
        return ".zshrc"
    if shell_name == "bash":
        if (Path.home() / ".bash_profile").exists():
            return ".bash_profile"
        return ".bashrc"
    return ".profile"


def _run_cli_install(cmd: list[str], label: str) -> bool:
    """Run an external CLI install command with live output. Returns True on success."""
    typer.echo(t("install.cli_running", label=label))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=sys.stderr,
            stderr=sys.stderr,
        )
        proc.wait(timeout=120)
        if proc.returncode == 0:
            typer.echo(t("install.cli_ok", label=label))
            return True
        typer.echo(t("install.cli_fail", label=label), err=True)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        typer.echo(t("install.cli_timeout", label=label), err=True)
    except Exception as exc:
        typer.echo(t("install.cli_error", label=label, error=str(exc)), err=True)
    return False


def _ensure_path(bin_dir: Path) -> bool:
    """Add *bin_dir* to the user's shell rc and current process PATH.

    Returns True if a shell rc file was modified (caller should remind user to source).
    """
    import os

    bin_str = str(bin_dir)
    modified_rc = False

    rc_name = _detect_shell_rc()
    rc_path = Path.home() / rc_name

    already_in_rc = False
    if rc_path.exists():
        content = rc_path.read_text(encoding="utf-8")
        if bin_str in content:
            already_in_rc = True

    if not already_in_rc:
        export_line = f'export PATH="{bin_str}:$PATH"'
        with open(rc_path, "a", encoding="utf-8") as f:
            f.write(f"\n# Added by harness install\n{export_line}\n")
        typer.echo(t("install.path_added", rc=rc_name, dir=bin_str))
        modified_rc = True

    if bin_str not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{bin_str}:{os.environ.get('PATH', '')}"

    return modified_rc


_needs_shell_reload = False


def _try_install_cursor_agent() -> bool:
    """Install cursor-agent: download binary, fix PATH, guide sign-in."""
    global _needs_shell_reload

    if not shutil.which("curl"):
        typer.echo(t("install.curl_missing"))
        return False
    if not typer.confirm(t("install.cursor_agent_confirm"), default=True):
        return False

    ok = _run_cli_install(
        ["bash", "-c", "curl https://cursor.com/install -fsS | bash"],
        "Cursor Agent",
    )
    if not ok:
        return False

    if _ensure_path(_AGENT_BIN_DIR):
        _needs_shell_reload = True

    if not shutil.which("cursor"):
        typer.echo(t("install.cursor_signin_skip"))
        return True

    typer.echo(t("install.cursor_signin_hint"))
    return True


def _try_install_codex_cli() -> bool:
    """Install Codex CLI via npm, then run interactive auth."""
    npm = shutil.which("npm")
    if not npm:
        typer.echo(t("install.npm_missing"))
        return False
    if not typer.confirm(t("install.codex_cli_confirm"), default=True):
        return False

    ok = _run_cli_install(["npm", "install", "-g", "@openai/codex"], "Codex CLI")
    if not ok:
        return False

    if not typer.confirm(t("install.codex_auth_confirm"), default=True):
        typer.echo(t("install.codex_auth_skip"))
        return True

    typer.echo(t("install.codex_auth_running"))
    try:
        subprocess.run(["codex", "auth"], check=False, timeout=120)
        typer.echo(t("install.codex_auth_done"))
    except subprocess.TimeoutExpired:
        typer.echo(t("install.codex_auth_timeout"))
    except Exception:
        typer.echo(t("install.codex_auth_fail"))

    return True


def _probe_ides(ides: dict[str, bool]) -> dict[str, bool]:
    """Run functional probes, offer guided install for missing/broken CLIs.

    Returns a dict with functional readiness (may upgrade False → True after install).
    """
    from harness.drivers.codex import CodexDriver
    from harness.drivers.cursor import CursorDriver

    ready = dict(ides)

    # ── Cursor ────────────────────────────────────────────────────
    if ides["cursor"]:
        probe = CursorDriver().probe()
        if probe.available:
            typer.echo(t("install.cursor_ok"))
        else:
            typer.echo(t("install.cursor_not_ready"))
            if _try_install_cursor_agent():
                reprobe = CursorDriver().probe()
                if reprobe.available:
                    typer.echo(t("install.cursor_ok"))
                else:
                    ready["cursor"] = False
            else:
                ready["cursor"] = False
    else:
        typer.echo(t("install.cursor_missing"))

    # ── Codex ─────────────────────────────────────────────────────
    if ides["codex"]:
        probe = CodexDriver().probe()
        if probe.available:
            typer.echo(t("install.codex_ok"))
        else:
            typer.echo(t("install.codex_not_ready"))
            if _try_install_codex_cli():
                reprobe = CodexDriver().probe()
                if reprobe.available:
                    typer.echo(t("install.codex_ok"))
                else:
                    ready["codex"] = False
            else:
                ready["codex"] = False
    else:
        typer.echo(t("install.codex_missing"))
        if _try_install_codex_cli():
            ides["codex"] = True
            ready["codex"] = True
            typer.echo(t("install.codex_ok"))

    return ready


def _probe_ides_force(ides: dict[str, bool]) -> dict[str, bool]:
    """Like _probe_ides but auto-accepts CLI installations (no confirmation prompts).

    Used by ``harness install --force`` to make reinstall a single-command fix.
    """
    from harness.drivers.codex import CodexDriver
    from harness.drivers.cursor import CursorDriver

    ready = dict(ides)

    # ── Cursor ────────────────────────────────────────────────────
    if ides["cursor"]:
        probe = CursorDriver().probe()
        if probe.available:
            typer.echo(t("install.cursor_ok"))
        else:
            typer.echo(t("install.cursor_not_ready"))
            if not shutil.which("curl"):
                typer.echo(t("install.curl_missing"))
                ready["cursor"] = False
            else:
                typer.echo(t("install.force_retry"))
                ok = _run_cli_install(
                    ["bash", "-c", "curl https://cursor.com/install -fsS | bash"],
                    "Cursor Agent",
                )
                if ok:
                    global _needs_shell_reload
                    if _ensure_path(_AGENT_BIN_DIR):
                        _needs_shell_reload = True
                    reprobe = CursorDriver().probe()
                    if reprobe.available:
                        typer.echo(t("install.cursor_ok"))
                    else:
                        ready["cursor"] = False
                else:
                    ready["cursor"] = False
    else:
        typer.echo(t("install.cursor_missing"))

    # ── Codex ─────────────────────────────────────────────────────
    if ides["codex"]:
        probe = CodexDriver().probe()
        if probe.available:
            typer.echo(t("install.codex_ok"))
        else:
            typer.echo(t("install.codex_not_ready"))
            typer.echo(t("install.force_retry"))
            npm = shutil.which("npm")
            if npm:
                ok = _run_cli_install(["npm", "install", "-g", "@openai/codex"], "Codex CLI")
                if ok:
                    reprobe = CodexDriver().probe()
                    if reprobe.available:
                        typer.echo(t("install.codex_ok"))
                    else:
                        ready["codex"] = False
                else:
                    ready["codex"] = False
            else:
                typer.echo(t("install.npm_missing"))
                ready["codex"] = False
    else:
        typer.echo(t("install.codex_missing"))
        npm = shutil.which("npm")
        if npm:
            ok = _run_cli_install(["npm", "install", "-g", "@openai/codex"], "Codex CLI")
            if ok:
                ready["codex"] = True
                typer.echo(t("install.codex_ok"))

    return ready


def _install_native_mode(project_root: Path, *, lang: str) -> int:
    """Generate Cursor-native mode artifacts if workflow.mode == cursor-native."""
    try:
        cfg = HarnessConfig.load(project_root)
    except Exception:
        return 0
    if cfg.workflow.mode != "cursor-native":
        return 0
    from harness.native.skill_gen import generate_native_artifacts
    return generate_native_artifacts(project_root, lang=lang, cfg=cfg)


def run_install(*, force: bool = False, lang: str | None = None) -> None:
    """Run install: preflight, then copy agent files.

    When *force* is True, overwrite existing agent files, re-run IDE probes,
    and re-attempt CLI installations without extra confirmation prompts.
    This makes ``harness install --force`` the canonical "fix my install" command.
    """
    global _needs_shell_reload

    resolved = _resolve_install_lang(lang)
    typer.echo(t("install.title"))

    ides = _detect_ide()
    typer.echo(t("install.env_check"))

    if force:
        ready = _probe_ides_force(ides)
    else:
        ready = _probe_ides(ides)

    native_count = _install_native_mode(Path.cwd(), lang=resolved)

    if not any(ready.values()) and native_count == 0:
        typer.echo(t("install.no_ide"), err=True)
        raise typer.Exit(1)

    source_dir = _agents_pkg_dir()
    if not source_dir.exists() and any(ready.values()):
        typer.echo(t("install.no_source", path=source_dir), err=True)
        raise typer.Exit(1)

    total = native_count
    skipped_any = False
    typer.echo()

    if ready.get("cursor") and source_dir.exists():
        typer.echo(t("install.cursor_agents"))
        expected = len(_CURSOR_AGENTS)
        count = _install_cursor_agents(source_dir, force=force, lang=resolved)
        if not force and count < expected:
            skipped_any = True
        total += count

    if ready.get("codex") and source_dir.exists():
        typer.echo(t("install.codex_agents"))
        expected = len(_CODEX_AGENTS)
        count = _install_codex_agents(source_dir, force=force, lang=resolved)
        if not force and count < expected:
            skipped_any = True
        total += count

    typer.echo(t("install.done", count=total))

    if skipped_any:
        typer.echo(t("install.force_hint"))

    if _needs_shell_reload:
        typer.echo(t("install.reload_hint", rc=_detect_shell_rc()))
        _needs_shell_reload = False
