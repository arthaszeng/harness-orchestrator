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
    except (OSError, json.JSONDecodeError, ValueError, KeyError):
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
    except (OSError, subprocess.TimeoutExpired):
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
    except (OSError, subprocess.TimeoutExpired):
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


def _check_other_python_envs(current_version: str) -> list[tuple[str, str]]:
    """Detect other pyenv Python versions with outdated harness-flow installs.

    Returns list of (python_version, harness_version) tuples for mismatched envs.
    """
    mismatched: list[tuple[str, str]] = []
    pyenv_root_raw = subprocess.run(
        ["pyenv", "root"], capture_output=True, text=True, timeout=5,
    ).stdout.strip() if _has_pyenv() else ""
    if not pyenv_root_raw:
        return mismatched

    pyenv_root = Path(pyenv_root_raw)
    versions_dir = pyenv_root / "versions"
    if not versions_dir.is_dir():
        return mismatched

    current_prefix = Path(sys.prefix).resolve()

    for ver_dir in sorted(versions_dir.iterdir()):
        if not ver_dir.is_dir():
            continue
        python_bin = ver_dir / "bin" / "python"
        if not python_bin.exists():
            continue
        if ver_dir.resolve() == current_prefix or str(current_prefix).startswith(str(ver_dir.resolve())):
            continue
        try:
            result = subprocess.run(
                [
                    str(python_bin), "-c",
                    "from importlib.metadata import version; print(version('harness-flow'))",
                ],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                installed = result.stdout.strip()
                if installed and installed != current_version:
                    mismatched.append((ver_dir.name, installed))
        except (OSError, subprocess.TimeoutExpired):
            continue

    return mismatched


def _has_pyenv() -> bool:
    try:
        result = subprocess.run(
            ["pyenv", "--version"], capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


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
    except (OSError, ValueError, KeyError):
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


def run_update(*, check: bool = False, force: bool = False, target_version: str | None = None) -> None:
    """Execute the harness update workflow."""
    project_root = Path.cwd()
    ui = get_ui()
    console = ui.console

    ui.banner("update", __version__)

    upgraded = False
    pypi_unreachable = False

    if target_version:
        # Pinned version mode — skip PyPI latest check, install directly
        console.print()
        if target_version == __version__:
            console.print(f"  [cyber.green]✓[/] Already at version {target_version}")
        else:
            console.print(f"  [cyber.cyan]▸[/] Installing harness-flow=={target_version}")
            if not _pip_upgrade(target_version):
                console.print(f"  [cyber.dim]{t('update.skip_reinstall')}[/]")
                raise typer.Exit(1)
            upgraded = True
    else:
        # Standard mode — check PyPI for latest
        console.print()
        console.print(f"  [cyber.magenta]▸[/] {t('update.checking')}")
        latest = _get_latest_version()

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

    # Step 4: Check other Python environments for stale harness-flow
    effective_version = _installed_distribution_version() or __version__
    mismatched = _check_other_python_envs(effective_version)
    if mismatched:
        console.print()
        console.print("  [cyber.warn]![/] Other Python environments have outdated harness-flow:")
        for py_ver, hf_ver in mismatched:
            console.print(
                f"    [cyber.dim]Python {py_ver}[/] → harness-flow [cyber.warn]{hf_ver}[/]"
                f"  [cyber.dim](run: pyenv shell {py_ver} && pip install harness-flow=={effective_version})[/]"
            )

    console.print()
    status = "[cyber.green]✓[/] clean" if warning_count == 0 else f"[cyber.warn]{warning_count}[/] warning(s)"
    env_status = f" · [cyber.warn]{len(mismatched)} stale env(s)[/]" if mismatched else ""
    console.print(Panel(
        f"  Status: {status}{env_status}",
        title="[cyber.header]UPDATE COMPLETE[/]",
        border_style="cyber.border",
        padding=(0, 1),
    ))
