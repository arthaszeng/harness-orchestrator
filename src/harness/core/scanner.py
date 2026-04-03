"""Project scanner — analyze layout, detect CI-related config, and suggest commands."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectScan:
    """Results of a project scan."""
    has_makefile: bool = False
    make_targets: list[str] = field(default_factory=list)
    has_pytest: bool = False
    pytest_dir: str = ""
    has_package_json: bool = False
    npm_scripts: list[str] = field(default_factory=list)
    has_pyproject: bool = False
    has_tox: bool = False
    has_architecture_check: bool = False
    suggested_commands: list[tuple[str, str]] = field(default_factory=list)


def scan_project(project_root: Path) -> ProjectScan:
    """Scan project layout and return CI-related findings."""
    scan = ProjectScan()

    _detect_makefile(project_root, scan)
    _detect_pytest(project_root, scan)
    _detect_npm(project_root, scan)
    _detect_pyproject(project_root, scan)
    _detect_tox(project_root, scan)
    _detect_architecture_check(project_root, scan)

    _build_suggestions(scan)
    return scan


def _detect_makefile(root: Path, scan: ProjectScan) -> None:
    makefile = root / "Makefile"
    if not makefile.exists():
        return
    scan.has_makefile = True
    content = makefile.read_text(encoding="utf-8", errors="ignore")

    scan.make_targets.extend(_parse_phony_targets(content))
    _append_declared_targets(content, scan.make_targets)


def _parse_phony_targets(content: str) -> list[str]:
    targets: list[str] = []
    for m in re.finditer(r"\.PHONY:\s*(.+)", content):
        targets.extend(m.group(1).split())
    return targets


def _append_declared_targets(content: str, target_list: list[str]) -> None:
    for m in re.finditer(r"^([a-zA-Z_][\w-]*):", content, re.MULTILINE):
        target = m.group(1)
        if target not in target_list:
            target_list.append(target)


def _detect_pytest(root: Path, scan: ProjectScan) -> None:
    for candidate in ["tests", "test"]:
        d = root / candidate
        if d.is_dir():
            scan.has_pytest = True
            scan.pytest_dir = candidate
            return

    if (root / "pytest.ini").exists() or (root / "conftest.py").exists():
        scan.has_pytest = True


def _detect_npm(root: Path, scan: ProjectScan) -> None:
    pkg = root / "package.json"
    if not pkg.exists():
        # Check frontend/ subdirectory
        pkg = root / "frontend" / "package.json"
    if not pkg.exists():
        return

    scan.has_package_json = True
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        scan.npm_scripts = list(scripts.keys())
    except (json.JSONDecodeError, OSError):
        pass


def _detect_pyproject(root: Path, scan: ProjectScan) -> None:
    scan.has_pyproject = (root / "pyproject.toml").exists()


def _detect_tox(root: Path, scan: ProjectScan) -> None:
    scan.has_tox = (root / "tox.ini").exists()


def _detect_architecture_check(root: Path, scan: ProjectScan) -> None:
    for candidate in [
        root / "scripts" / "check_architecture.py",
        root / "scripts" / "check_arch.py",
        root / "tools" / "check_architecture.py",
    ]:
        if candidate.exists():
            scan.has_architecture_check = True
            return


def _build_suggestions(scan: ProjectScan) -> None:
    """Build CI command suggestions from scan results, sorted by preference."""
    suggestions: list[tuple[int, str, str]] = []  # (priority, command, description)

    targets = set(scan.make_targets)

    if scan.has_makefile:
        # make check test (arch + tests) is the best combo when both exist
        if "check" in targets and "test" in targets:
            suggestions.append((10, "make check test", "architecture check + unit tests"))
        # make ci if present (may include smoke, heavier)
        if "ci" in targets:
            suggestions.append((5, "make ci", "full CI (may include smoke tests, slower)"))
        # make test alone
        if "test" in targets and "check" not in targets:
            suggestions.append((8, "make test", "unit tests"))
        elif "test" in targets:
            suggestions.append((6, "make test", "unit tests only"))
        # make lint
        if "lint" in targets:
            suggestions.append((4, "make lint", "linting"))

    if scan.has_pytest:
        dir_arg = f" {scan.pytest_dir}/" if scan.pytest_dir else ""
        suggestions.append((3, f"python -m pytest{dir_arg} -v", "run pytest directly"))

    if scan.has_tox:
        suggestions.append((2, "tox", "tox tests"))

    # Sort by priority descending
    suggestions.sort(key=lambda x: -x[0])
    scan.suggested_commands = [(cmd, desc) for _, cmd, desc in suggestions]


def format_scan_report(scan: ProjectScan) -> list[str]:
    """Format scan findings as display lines."""
    lines: list[str] = []
    if scan.has_makefile:
        relevant = [t for t in scan.make_targets if t in {
            "test", "check", "ci", "lint", "smoke", "smoke-backend", "smoke-frontend",
        }]
        if relevant:
            lines.append(f"Makefile (targets: {', '.join(relevant)})")
        else:
            lines.append("Makefile")

    if scan.has_pytest:
        lines.append(f"pytest ({scan.pytest_dir}/)" if scan.pytest_dir else "pytest")

    if scan.has_architecture_check:
        lines.append("scripts/check_architecture.py")

    if scan.has_package_json:
        relevant = [s for s in scan.npm_scripts if s in {"test", "lint", "build"}]
        if relevant:
            lines.append(f"package.json (scripts: {', '.join(relevant)})")
        else:
            lines.append("package.json")

    if scan.has_pyproject:
        lines.append("pyproject.toml")

    if scan.has_tox:
        lines.append("tox.ini")

    return lines
