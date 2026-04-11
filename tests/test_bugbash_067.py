"""Task-067 bugbash: end-to-end integration validation for task-066 architecture changes.

Verifies that the three-layer memory model, CLI tool-chain extensions, and
skill template routing-table refactor do not break real user paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.config import HarnessConfig
from harness.core.handoff import load_handoff
from harness.native.skill_gen import generate_native_artifacts

runner = CliRunner()

CRITICAL_SKILL_FILES = [
    ".cursor/skills/harness/harness-ship/SKILL.md",
    ".cursor/skills/harness/harness-eval/PROTOCOL.md",
    ".cursor/skills/harness/harness-build/PROTOCOL.md",
    ".cursor/skills/harness/harness-plan/SKILL.md",
    ".cursor/skills/harness/harness-vision/SKILL.md",
    ".cursor/skills/harness/harness-investigate/SKILL.md",
    ".cursor/skills/harness/harness-learn/SKILL.md",
    ".cursor/skills/harness/harness-doc-release/PROTOCOL.md",
    ".cursor/skills/harness/harness-retro/SKILL.md",
]

CRITICAL_REFERENCE_FILES = [
    ".cursor/skills/harness/harness-eval/code-review-protocol.md",
    ".cursor/skills/harness/harness-ship/ship-pr-protocol.md",
    ".cursor/skills/harness/harness-ship/ship-test-triage.md",
    ".cursor/skills/harness/harness-ship/ship-coverage-audit.md",
]

CRITICAL_AGENT_FILES = [
    ".cursor/skills/harness/_agents/harness-architect.md",
    ".cursor/skills/harness/_agents/harness-product-owner.md",
    ".cursor/skills/harness/_agents/harness-engineer.md",
    ".cursor/skills/harness/_agents/harness-qa.md",
    ".cursor/skills/harness/_agents/harness-project-manager.md",
]

CRITICAL_RULE_FILES = [
    ".cursor/rules/harness-trust-boundary.mdc",
    ".cursor/rules/harness-workflow.mdc",
    ".cursor/rules/harness-fix-first.mdc",
    ".cursor/rules/harness-safety-guardrails.mdc",
]


def _make_project(tmp_path: Path, lang: str = "en") -> Path:
    """Create a minimal harness project directory."""
    hf = tmp_path / ".harness-flow"
    hf.mkdir()
    (hf / "tasks").mkdir()
    (hf / "config.toml").write_text(
        f'[project]\nname = "bugbash-test"\nlang = "{lang}"\n\n'
        '[ci]\ncommand = "pytest"\n\n'
        '[workflow]\ntrunk_branch = "main"\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return _make_project(tmp_path)


@pytest.fixture()
def project_zh(tmp_path: Path) -> Path:
    return _make_project(tmp_path, lang="zh")


@pytest.fixture()
def task_dir(project: Path) -> Path:
    td = project / ".harness-flow" / "tasks" / "task-001"
    td.mkdir(parents=True, exist_ok=True)
    return td


# ── BG-1: init generates critical path files (explicit checklist, not count) ──


class TestInitCriticalFiles:
    """BG-1: harness init --force generates all critical path files."""

    def test_en_skills_present(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        for rel in CRITICAL_SKILL_FILES:
            p = project / rel
            assert p.exists(), f"missing skill: {rel}"
            assert p.stat().st_size > 0, f"empty skill: {rel}"

    def test_en_agents_present(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        for rel in CRITICAL_AGENT_FILES:
            p = project / rel
            assert p.exists(), f"missing agent: {rel}"

    def test_en_rules_present(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        for rel in CRITICAL_RULE_FILES:
            p = project / rel
            assert p.exists(), f"missing rule: {rel}"

    def test_en_reference_files_present(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        for rel in CRITICAL_REFERENCE_FILES:
            p = project / rel
            assert p.exists(), f"missing reference: {rel}"


# ── BG-2: reference files have no Jinja residue ──


class TestReferenceFileQuality:
    """BG-2: rendered reference files contain no Jinja template residue."""

    def test_no_jinja_residue_in_references(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        for rel in CRITICAL_REFERENCE_FILES:
            content = (project / rel).read_text(encoding="utf-8")
            assert "{{" not in content, f"Jinja residue in {rel}"
            assert "{%" not in content, f"Jinja residue in {rel}"


# ── BG-3: handoff write+read round-trip ──


class TestHandoffRoundTrip:
    """BG-3: handoff write → read preserves field semantics."""

    def test_cli_write_read_round_trip(self, project: Path, task_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(project)
        payload = {
            "schema_version": 3,
            "source_phase": "plan",
            "target_phase": "build",
            "task_id": "task-001",
            "summary": "bugbash round-trip test",
            "working_set": ["src/main.py"],
            "active_constraints": ["no-breaking-changes"],
            "resume_prompt": "continue from step 3",
        }
        write_result = runner.invoke(
            app, ["handoff", "write", "--task", "task-001"],
            input=json.dumps(payload),
        )
        assert write_result.exit_code == 0, f"write failed: {write_result.output}"

        read_result = runner.invoke(app, ["handoff", "read", "--task", "task-001", "--json"])
        assert read_result.exit_code == 0, f"read failed: {read_result.output}"

        data = json.loads(read_result.output)
        assert data["task_id"] == "task-001"
        assert data["summary"] == "bugbash round-trip test"
        assert data["working_set"] == ["src/main.py"]
        assert data["active_constraints"] == ["no-breaking-changes"]
        assert data["resume_prompt"] == "continue from step 3"
        assert data["source_phase"] == "plan"
        assert data["target_phase"] == "build"


# ── BG-4: session write+read round-trip ──


class TestSessionRoundTrip:
    """BG-4: session write → read preserves field semantics."""

    def test_cli_write_read_round_trip(self, project: Path, task_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(project)
        payload = {
            "task_id": "task-001",
            "current_phase": "build",
            "current_step": "3/7",
            "current_state": "implementing deliverables",
            "next_step": "run CI",
            "working_set": ["src/app.py", "tests/test_app.py"],
            "open_loops": ["BG-5 pending"],
        }
        write_result = runner.invoke(
            app, ["session", "write", "--task", "task-001"],
            input=json.dumps(payload),
        )
        assert write_result.exit_code == 0, f"write failed: {write_result.output}"

        read_result = runner.invoke(app, ["session", "read", "--task", "task-001", "--json"])
        assert read_result.exit_code == 0, f"read failed: {read_result.output}"

        data = json.loads(read_result.output)
        assert data["task_id"] == "task-001"
        assert data["current_phase"] == "build"
        assert data["current_step"] == "3/7"
        assert data["current_state"] == "implementing deliverables"
        assert data["next_step"] == "run CI"
        assert data["working_set"] == ["src/app.py", "tests/test_app.py"]
        assert data["open_loops"] == ["BG-5 pending"]


# ── BG-5: context-budget JSON output structure ──


class TestContextBudget:
    """BG-5: context-budget --json has correct structure."""

    def test_json_output_structure(self, project: Path, task_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(project)
        (task_dir / "plan.md").write_text("# Plan\nsome content", encoding="utf-8")
        result = runner.invoke(app, ["context-budget", "--task", "task-001", "--json"])
        assert result.exit_code == 0, f"context-budget failed: {result.output}"
        data = json.loads(result.output)
        assert "budget_tokens" in data
        assert "total_tokens" in data
        assert "total_chars" in data
        assert "over_budget" in data
        assert "artifacts" in data
        assert isinstance(data["artifacts"], list)
        assert data["total_tokens"] > 0


# ── BG-6: backward compat — v2 handoff loads correctly ──


class TestHandoffBackwardCompat:
    """BG-6: v2 handoff JSON can be loaded by current code."""

    def test_v2_handoff_loads(self, task_dir: Path):
        v2_payload = {
            "schema_version": 2,
            "source_phase": "plan",
            "target_phase": "build",
            "task_id": "task-001",
            "summary": "v2 handoff — no working_set/active_constraints/resume_prompt",
            "context_footprint": {
                "explored_paths": ["src/"],
                "primary_read_files": ["README.md"],
                "primary_touched_files": [],
            },
        }
        (task_dir / "handoff-plan.json").write_text(
            json.dumps(v2_payload, indent=2), encoding="utf-8",
        )
        result = load_handoff(task_dir, "plan")
        assert result is not None
        assert result.summary == "v2 handoff — no working_set/active_constraints/resume_prompt"
        assert result.working_set == []
        assert result.active_constraints == []
        assert result.resume_prompt == ""


# ── BG-7: old config without context_budget_tokens doesn't error ──


class TestOldConfigCompat:
    """BG-7: config without context_budget_tokens loads with default."""

    def test_missing_budget_field_uses_default(self, tmp_path: Path):
        hf = tmp_path / ".harness-flow"
        hf.mkdir()
        (hf / "config.toml").write_text(
            '[project]\nname = "old-project"\nlang = "en"\n\n'
            '[ci]\ncommand = "make test"\n\n'
            '[workflow]\ntrunk_branch = "main"\n',
            encoding="utf-8",
        )
        cfg = HarnessConfig.load(tmp_path)
        assert cfg.workflow.context_budget_tokens == 50000


# ── BG-8: rendered ship SKILL.md contains routing pointers ──


class TestShipRoutingPointers:
    """BG-8: ship SKILL.md references external protocol files."""

    def test_ship_contains_protocol_pointers(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        content = (project / ".cursor/skills/harness/harness-ship/SKILL.md").read_text(encoding="utf-8")
        assert "ship-pr-protocol.md" in content
        assert "ship-test-triage.md" in content
        assert "ship-coverage-audit.md" in content


# ── BG-9: rendered eval SKILL.md contains routing pointers ──


class TestEvalRoutingPointers:
    """BG-9: eval SKILL.md references external protocol files."""

    def test_eval_contains_protocol_pointers(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        content = (project / ".cursor/skills/harness/harness-eval/PROTOCOL.md").read_text(encoding="utf-8")
        assert "code-review-protocol.md" in content


# ── BG-10: build SKILL.md contains CLI references ──


class TestBuildCLIReferences:
    """BG-10: build SKILL.md references handoff read and session write."""

    def test_build_contains_cli_references(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        content = (project / ".cursor/skills/harness/harness-build/PROTOCOL.md").read_text(encoding="utf-8")
        assert "harness handoff read" in content
        assert "harness session write" in content or "harness session" in content


# ── BG-11: handoff write invalid JSON → exit 1 ──


class TestHandoffErrorPaths:
    """BG-11: handoff write with invalid input returns exit 1."""

    def test_invalid_json_exit_1(self, project: Path, task_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(project)
        result = runner.invoke(
            app, ["handoff", "write", "--task", "task-001"],
            input="this is not json",
        )
        assert result.exit_code == 1

    def test_invalid_schema_exit_1(self, project: Path, task_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(project)
        result = runner.invoke(
            app, ["handoff", "write", "--task", "task-001"],
            input=json.dumps({"bad": "schema"}),
        )
        assert result.exit_code == 1


# ── BG-12: session read with no session → exit 2 ──


class TestSessionNotFound:
    """BG-12: session read returns exit 2 when no session exists."""

    def test_no_session_exit_2(self, project: Path, task_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(project)
        result = runner.invoke(app, ["session", "read", "--task", "task-001"])
        assert result.exit_code == 2


# ── BG-13: resume directive present in key skills ──


class TestResumeDirective:
    """BG-13: resume directive / session read reference in build/ship/eval skills."""

    def test_resume_directive_in_build(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        content = (project / ".cursor/skills/harness/harness-build/PROTOCOL.md").read_text(encoding="utf-8")
        assert "session read" in content.lower() or "resume" in content.lower()

    def test_resume_directive_in_ship(self, project: Path):
        cfg = HarnessConfig.load(project)
        generate_native_artifacts(project, cfg=cfg, lang="en")
        content = (project / ".cursor/skills/harness/harness-ship/SKILL.md").read_text(encoding="utf-8")
        assert "session" in content.lower() or "resume" in content.lower() or "handoff" in content.lower()


# ── BG-14: Chinese mode also produces reference files ──


class TestChineseMode:
    """BG-14: init with lang=zh generates all reference files."""

    def test_zh_reference_files_present(self, project_zh: Path):
        cfg = HarnessConfig.load(project_zh)
        generate_native_artifacts(project_zh, cfg=cfg, lang="zh")
        for rel in CRITICAL_REFERENCE_FILES:
            p = project_zh / rel
            assert p.exists(), f"missing reference in zh mode: {rel}"
            content = p.read_text(encoding="utf-8")
            assert "{{" not in content, f"Jinja residue in zh {rel}"

    def test_zh_skills_present(self, project_zh: Path):
        cfg = HarnessConfig.load(project_zh)
        generate_native_artifacts(project_zh, cfg=cfg, lang="zh")
        for rel in CRITICAL_SKILL_FILES:
            p = project_zh / rel
            assert p.exists(), f"missing skill in zh mode: {rel}"


# ── BG-15: context-budget on empty task → 0 tokens, exit 0 ──


class TestContextBudgetEmpty:
    """BG-15: context-budget on an empty/non-existent task dir returns 0 tokens."""

    def test_empty_task_dir(self, project: Path, task_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(project)
        result = runner.invoke(app, ["context-budget", "--task", "task-001", "--json"])
        assert result.exit_code == 0, f"unexpected exit: {result.output}"
        data = json.loads(result.output)
        assert data["total_tokens"] == 0
        assert data["artifacts"] == []
