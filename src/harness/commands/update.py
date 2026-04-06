"""harness update — self-update and run config migration checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.panel import Panel

from harness import __version__
from harness.core.ui import get_ui
from harness.i18n import t


def _get_latest_version() -> str | None:
    """Query PyPI for the latest harness-flow version.

    Prefers the stable JSON API; falls back to ``pip index`` subprocess.
    """
    version = _get_latest_version_http()
    if version is not None:
        return version
    return _get_latest_version_pip()


def _get_latest_version_http() -> str | None:
    """Query PyPI JSON API (fast, no subprocess)."""
    import json
    import urllib.request

    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/harness-flow/json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("info", {}).get("version")
    except Exception:
        return None


def _get_latest_version_pip() -> str | None:
    """Fallback: query via pip index subprocess."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", "harness-flow"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "harness-flow" in line and "(" in line:
                    return line.split("(")[1].split(")")[0].strip()
    except Exception:
        pass
    return None


def _installed_distribution_version() -> str | None:
    """Read installed harness-flow version in the current interpreter environment."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from importlib.metadata import version; print(version('harness-flow'))",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _pip_upgrade(target_version: str | None = None) -> bool:
    """Run pip upgrade and verify installed version with one force-reinstall fallback."""
    console = get_ui().console
    console.print(f"  [cyber.magenta]▸[/] {t('update.upgrading')}")
    package = f"harness-flow=={target_version}" if target_version else "harness-flow"
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", package],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        console.print(f"  [cyber.fail]✗[/] {t('update.upgrade_fail')}")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-3:]:
                console.print(f"    [cyber.dim]{line}[/]")
        return False

    if target_version:
        installed = _installed_distribution_version()
        if installed == target_version:
            console.print(f"  [cyber.green]✓[/] {t('update.upgrade_ok')}")
            return True
        console.print(
            f"  [cyber.warn]![/] "
            f"{t('update.version_verify_retry', expected=target_version, installed=installed or 'unknown')}"
        )
        retry = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--force-reinstall",
                "--no-cache-dir",
                package,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if retry.returncode != 0:
            console.print(f"  [cyber.fail]✗[/] {t('update.upgrade_fail')}")
            if retry.stderr:
                for line in retry.stderr.strip().splitlines()[-3:]:
                    console.print(f"    [cyber.dim]{line}[/]")
            return False
        installed_retry = _installed_distribution_version()
        if installed_retry == target_version:
            console.print(f"  [cyber.green]✓[/] {t('update.upgrade_ok')}")
            return True
        console.print(
            f"  [cyber.fail]✗[/] "
            f"{t('update.version_verify_failed', expected=target_version, installed=installed_retry or 'unknown')}"
        )
        return False

    console.print(f"  [cyber.green]✓[/] {t('update.upgrade_ok')}")
    return True


def _migrate_config(project_root: Path) -> int:
    """Check .harness-flow/config.toml for missing/deprecated keys. Returns count of warnings."""
    config_path = project_root / ".harness-flow" / "config.toml"
    if not config_path.exists():
        return 0

    console = get_ui().console

    try:
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        console.print(f"  [cyber.warn]![/] {t('update.config_parse_error', path=str(config_path))}")
        return 1

    warnings = 0

    recommended_sections = {
        "project": "project name and language",
        "ci": "CI gate command",
        "workflow": "iteration and branch settings",
    }
    for section, desc in recommended_sections.items():
        if section not in data:
            console.print(
                f"  [cyber.dim]ℹ[/] {t('update.config_missing_section', section=section, desc=desc)}"
            )
            warnings += 1

    deprecated: list[tuple[str, str, str]] = [
        ("native.adversarial_model", "native.evaluator_model", "0.4.0"),
    ]
    for old_key, replacement, since_version in deprecated:
        parts = old_key.split(".")
        section_data = data
        found = True
        for p in parts:
            if isinstance(section_data, dict) and p in section_data:
                section_data = section_data[p]
            else:
                found = False
                break
        if found:
            console.print(
                f"  [cyber.warn]![/] Deprecated key [cyber.cyan]{old_key}[/] "
                f"→ use [cyber.cyan]{replacement}[/] [cyber.dim](since {since_version})[/]"
            )
            warnings += 1

    if warnings == 0:
        console.print(f"  [cyber.green]✓[/] {t('update.config_ok')}")

    return warnings


def run_update(*, check: bool = False, force: bool = False) -> None:
    """Execute the harness update workflow."""
    project_root = Path.cwd()
    ui = get_ui()
    console = ui.console

    ui.banner("update", __version__)

    # Step 1: Check for new version
    console.print()
    console.print(f"  [cyber.magenta]▸[/] {t('update.checking')}")
    latest = _get_latest_version()

    upgraded = False
    pypi_unreachable = False

    if latest is None:
        console.print(f"  [cyber.warn]![/] {t('update.check_failed')}")
        pypi_unreachable = True
        if check:
            raise typer.Exit(1)
    elif latest == __version__:
        console.print(f"  [cyber.green]✓[/] {t('update.up_to_date')}")
        if check:
            raise typer.Exit(0)
    else:
        console.print(f"  [cyber.cyan]▸[/] {t('update.new_version', version=latest)}")
        if check:
            raise typer.Exit(0)
        if not _pip_upgrade(latest):
            console.print(f"  [cyber.dim]{t('update.skip_reinstall')}[/]")
            raise typer.Exit(1)
        upgraded = True

    if check:
        raise typer.Exit(0)

    # Step 2: Never write project artifacts from update.
    # Users should run `harness init --force` in the target repository.
    console.print()
    if upgraded:
        console.print(f"  [cyber.green]✓[/] {t('update.skip_reinstall_upgrade_ok')}")
        console.print(f"  [cyber.yellow]✨[/] {t('update.easter_egg')}")
    elif force:
        console.print(f"  [cyber.warn]![/] {t('update.force_no_project_write')}")
    elif pypi_unreachable:
        console.print(
            f"  [cyber.warn]![/] {t('update.skip_reinstall_unreachable')}"
        )
    else:
        console.print(
            f"  [cyber.green]✓[/] {t('update.skip_reinstall_up_to_date')}"
        )

    # Step 3: Config migration (always runs as lightweight health check)
    console.print()
    console.print(f"  [cyber.magenta]▸[/] {t('update.migrate_title')}")
    warning_count = _migrate_config(project_root)

    console.print()
    status = "[cyber.green]✓[/] clean" if warning_count == 0 else f"[cyber.warn]{warning_count}[/] warning(s)"
    console.print(Panel(
        f"  Status: {status}",
        title="[cyber.header]UPDATE COMPLETE[/]",
        border_style="cyber.border",
        padding=(0, 1),
    ))
