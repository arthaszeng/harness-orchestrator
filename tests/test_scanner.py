"""项目扫描器单元测试"""

from __future__ import annotations

import json

import pytest

from harness.core.scanner import (
    ProjectScan,
    format_scan_report,
    scan_project,
)


@pytest.fixture()
def project_dir(tmp_path):
    """空项目目录"""
    return tmp_path


class TestScanProject:
    def test_empty_project(self, project_dir):
        scan = scan_project(project_dir)
        assert not scan.has_makefile
        assert not scan.has_pytest
        assert not scan.has_package_json
        assert scan.suggested_commands == []

    def test_detects_makefile(self, project_dir):
        makefile = project_dir / "Makefile"
        makefile.write_text(
            ".PHONY: check test ci smoke\n"
            "check:\n\tpython scripts/check.py\n"
            "test:\n\tpytest\n"
            "ci: check test smoke\n"
            "smoke:\n\techo smoke\n"
        )
        scan = scan_project(project_dir)
        assert scan.has_makefile
        assert "check" in scan.make_targets
        assert "test" in scan.make_targets
        assert "ci" in scan.make_targets
        assert "smoke" in scan.make_targets

    def test_detects_pytest_directory(self, project_dir):
        (project_dir / "tests").mkdir()
        scan = scan_project(project_dir)
        assert scan.has_pytest
        assert scan.pytest_dir == "tests"

    def test_detects_pytest_via_conftest(self, project_dir):
        (project_dir / "conftest.py").write_text("# conftest\n")
        scan = scan_project(project_dir)
        assert scan.has_pytest

    def test_detects_package_json(self, project_dir):
        (project_dir / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest", "lint": "eslint .", "build": "next build"}})
        )
        scan = scan_project(project_dir)
        assert scan.has_package_json
        assert "test" in scan.npm_scripts
        assert "lint" in scan.npm_scripts
        assert "build" in scan.npm_scripts

    def test_detects_frontend_package_json(self, project_dir):
        frontend = project_dir / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(
            json.dumps({"scripts": {"build": "next build"}})
        )
        scan = scan_project(project_dir)
        assert scan.has_package_json
        assert "build" in scan.npm_scripts

    def test_detects_pyproject(self, project_dir):
        (project_dir / "pyproject.toml").write_text("[build-system]\n")
        scan = scan_project(project_dir)
        assert scan.has_pyproject

    def test_detects_tox(self, project_dir):
        (project_dir / "tox.ini").write_text("[tox]\n")
        scan = scan_project(project_dir)
        assert scan.has_tox

    def test_detects_architecture_check(self, project_dir):
        scripts = project_dir / "scripts"
        scripts.mkdir()
        (scripts / "check_architecture.py").write_text("# arch check\n")
        scan = scan_project(project_dir)
        assert scan.has_architecture_check

    def test_make_targets_keep_phony_order_and_dedup_declared_targets(self, project_dir):
        makefile = project_dir / "Makefile"
        makefile.write_text(
            ".PHONY: test test lint\n"
            "test:\n\tpytest\n"
            "lint:\n\techo lint\n"
        )
        scan = scan_project(project_dir)
        assert scan.make_targets[:3] == ["test", "test", "lint"]
        assert scan.make_targets.count("test") == 2


class TestBuildSuggestions:
    def test_makefile_check_test_is_top_priority(self, project_dir):
        makefile = project_dir / "Makefile"
        makefile.write_text(".PHONY: check test ci\ncheck:\ntest:\nci:\n")
        scan = scan_project(project_dir)
        assert len(scan.suggested_commands) > 0
        top_cmd = scan.suggested_commands[0][0]
        assert top_cmd == "make check test"

    def test_pytest_only(self, project_dir):
        (project_dir / "tests").mkdir()
        scan = scan_project(project_dir)
        assert len(scan.suggested_commands) == 1
        assert "pytest" in scan.suggested_commands[0][0]

    def test_tox_only(self, project_dir):
        (project_dir / "tox.ini").write_text("[tox]\n")
        scan = scan_project(project_dir)
        assert any("tox" in cmd for cmd, _ in scan.suggested_commands)

    def test_combined_suggestions_sorted(self, project_dir):
        makefile = project_dir / "Makefile"
        makefile.write_text(".PHONY: check test ci lint\ncheck:\ntest:\nci:\nlint:\n")
        (project_dir / "tests").mkdir()
        (project_dir / "tox.ini").write_text("[tox]\n")
        scan = scan_project(project_dir)
        # 应按 priority 降序
        assert scan.suggested_commands[0][0] == "make check test"
        assert len(scan.suggested_commands) >= 4


class TestFormatScanReport:
    def test_empty_scan(self):
        scan = ProjectScan()
        assert format_scan_report(scan) == []

    def test_full_scan(self, project_dir):
        makefile = project_dir / "Makefile"
        makefile.write_text(".PHONY: check test ci\ncheck:\ntest:\nci:\n")
        (project_dir / "tests").mkdir()
        scripts = project_dir / "scripts"
        scripts.mkdir()
        (scripts / "check_architecture.py").write_text("# arch\n")
        (project_dir / "pyproject.toml").write_text("[build-system]\n")

        scan = scan_project(project_dir)
        report = format_scan_report(scan)
        assert any("Makefile" in line for line in report)
        assert any("pytest" in line for line in report)
        assert any("check_architecture" in line for line in report)
        assert any("pyproject" in line for line in report)

    def test_report_respects_make_target_order(self, project_dir):
        makefile = project_dir / "Makefile"
        makefile.write_text(".PHONY: lint test ci\nlint:\ntest:\nci:\n")
        scan = scan_project(project_dir)
        report = format_scan_report(scan)
        assert report[0] == "Makefile (targets: lint, test, ci)"
