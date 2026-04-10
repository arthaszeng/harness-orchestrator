"""Task-066 architecture tests: references, session, handoff v3, CLIs, context budget, templates."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.config import HarnessConfig, WorkflowConfig
from harness.core.handoff import (
    HANDOFF_SCHEMA_VERSION,
    StageHandoff,
    load_handoff,
    save_handoff,
)
from harness.core.session_context import SessionContext, load_session_context, save_session_context
from harness.native.skill_gen import generate_native_artifacts

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_J2_DIR = REPO_ROOT / "src" / "harness" / "templates" / "native" / "references"
_REFERENCE_NAMES = (
    "code-review-protocol.md.j2",
    "ship-pr-protocol.md.j2",
    "ship-test-triage.md.j2",
    "ship-coverage-audit.md.j2",
)


def _setup_project(tmp_path: Path) -> Path:
    """Create minimal harness project for rendering tests."""
    harness_dir = tmp_path / ".harness-flow"
    harness_dir.mkdir()
    config_content = """
[project]
name = "test-project"
lang = "en"

[ci]
command = "pytest"

[workflow]
trunk_branch = "main"
"""
    (harness_dir / "config.toml").write_text(config_content.strip() + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    harness_dir = tmp_path / ".harness-flow"
    harness_dir.mkdir()
    (harness_dir / "config.toml").write_text(
        '[project]\nname = "test"\nlang = "en"\n\n[ci]\ncommand = "pytest"\n\n[workflow]\ntrunk_branch = "main"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --- D1: Reference files ---


def test_reference_j2_templates_exist():
    # D1
    for name in _REFERENCE_NAMES:
        p = REFERENCE_J2_DIR / name
        assert p.is_file(), f"missing {p}"


def test_reference_files_render_no_jinja_residue(tmp_path: Path):
    # D1
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    base = root / ".cursor" / "skills" / "harness"
    rendered = [
        base / "harness-eval" / "code-review-protocol.md",
        base / "harness-ship" / "ship-pr-protocol.md",
        base / "harness-ship" / "ship-test-triage.md",
        base / "harness-ship" / "ship-coverage-audit.md",
    ]
    for path in rendered:
        text = path.read_text(encoding="utf-8")
        assert "{{" not in text, path
        assert "{%" not in text, path


def test_reference_files_have_anchors(tmp_path: Path):
    # D1
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    base = root / ".cursor" / "skills" / "harness"
    code_review = (base / "harness-eval" / "code-review-protocol.md").read_text(encoding="utf-8")
    assert "5-Role" in code_review
    assert "PR Creation Protocol" in (base / "harness-ship" / "ship-pr-protocol.md").read_text(
        encoding="utf-8"
    )
    assert "Test Failure Triage Protocol" in (base / "harness-ship" / "ship-test-triage.md").read_text(
        encoding="utf-8"
    )
    assert "Test Coverage Audit Protocol" in (base / "harness-ship" / "ship-coverage-audit.md").read_text(
        encoding="utf-8"
    )


def test_reference_files_size_floor(tmp_path: Path):
    # D1
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    base = root / ".cursor" / "skills" / "harness"
    for rel in (
        "harness-eval/code-review-protocol.md",
        "harness-ship/ship-pr-protocol.md",
        "harness-ship/ship-test-triage.md",
        "harness-ship/ship-coverage-audit.md",
    ):
        text = (base / rel).read_text(encoding="utf-8")
        assert len(text) > 500, rel


# --- D2: Session context ---


def test_session_context_round_trip(tmp_path: Path):
    # D2
    task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    ctx = SessionContext(
        task_id="task-001",
        current_phase="build",
        current_step="3/7",
        current_state="coding",
        next_step="run ci",
        working_set=["a.py", "b.py"],
        active_constraints=["no breaking api"],
        open_loops=["verify edge case"],
    )
    save_session_context(task_dir, ctx)
    loaded = load_session_context(task_dir)
    assert loaded is not None
    assert loaded.task_id == ctx.task_id
    assert loaded.current_phase == ctx.current_phase
    assert loaded.current_step == ctx.current_step
    assert loaded.current_state == ctx.current_state
    assert loaded.next_step == ctx.next_step
    assert loaded.working_set == ctx.working_set
    assert loaded.active_constraints == ctx.active_constraints
    assert loaded.open_loops == ctx.open_loops


def test_session_context_truncation(tmp_path: Path):
    # D2
    task_dir = tmp_path / "t"
    task_dir.mkdir()
    items = [f"f{i}.py" for i in range(25)]
    ctx = SessionContext(task_id="t", working_set=items)
    save_session_context(task_dir, ctx)
    loaded = load_session_context(task_dir)
    assert loaded is not None
    assert len(loaded.working_set) <= 20


def test_session_context_missing_returns_none(tmp_path: Path):
    # D2
    empty = tmp_path / "no_session_here"
    empty.mkdir()
    assert load_session_context(empty) is None


def test_session_context_corrupt_returns_none(tmp_path: Path):
    # D2
    task_dir = tmp_path / "t"
    task_dir.mkdir()
    (task_dir / "session-context.json").write_text("not-json{{{", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        assert load_session_context(task_dir) is None


def test_session_context_atomic_write(tmp_path: Path):
    # D2
    task_dir = tmp_path / "t"
    task_dir.mkdir()
    ctx = SessionContext(task_id="t", current_phase="plan", current_step="1", current_state="x", next_step="y")
    save_session_context(task_dir, ctx)
    tmp = task_dir / ".session-context.json.tmp"
    assert not tmp.exists()


# --- D3: Handoff v3 ---


def test_handoff_v2_payload_loads():
    # D3
    raw = {
        "schema_version": 2,
        "source_phase": "plan",
        "target_phase": "build",
        "task_id": "task-001",
        "summary": "legacy handoff",
    }
    h = StageHandoff.model_validate(raw)
    assert h.task_id == "task-001"
    assert h.working_set == []
    assert h.active_constraints == []
    assert h.resume_prompt == ""


def test_handoff_v3_new_fields(tmp_path: Path):
    # D3
    task_dir = tmp_path / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    h = StageHandoff(
        schema_version=3,
        source_phase="plan",
        target_phase="build",
        task_id="task-001",
        summary="s",
        working_set=["x.py"],
        active_constraints=["c1"],
        resume_prompt="continue here",
    )
    save_handoff(task_dir, h)
    loaded = load_handoff(task_dir, "plan")
    assert loaded is not None
    assert loaded.working_set == ["x.py"]
    assert loaded.active_constraints == ["c1"]
    assert loaded.resume_prompt == "continue here"


def test_handoff_v3_empty_fields_compat():
    # D3
    v2_style = StageHandoff.model_validate(
        {
            "schema_version": 2,
            "source_phase": "eval",
            "target_phase": "ship",
            "task_id": "TASK-42",
            "summary": "x",
        }
    )
    v3_empty = StageHandoff.model_validate(
        {
            "schema_version": 3,
            "source_phase": "eval",
            "target_phase": "ship",
            "task_id": "TASK-42",
            "summary": "x",
            "working_set": [],
            "active_constraints": [],
            "resume_prompt": "",
        }
    )
    assert v2_style.working_set == v3_empty.working_set
    assert v2_style.active_constraints == v3_empty.active_constraints
    assert v2_style.resume_prompt == v3_empty.resume_prompt


def test_handoff_schema_version_is_3():
    # D3
    assert HANDOFF_SCHEMA_VERSION == 3


# --- D4: Handoff CLI ---


def test_handoff_write_read_cli(project_dir: Path):
    # D4
    handoff_json = json.dumps(
        {
            "source_phase": "plan",
            "target_phase": "build",
            "task_id": "task-001",
            "summary": "test summary",
            "schema_version": 3,
        }
    )
    w = runner.invoke(app, ["handoff", "write", "--task", "task-001"], input=handoff_json)
    assert w.exit_code == 0, w.stdout + w.stderr
    r = runner.invoke(app, ["handoff", "read", "--task", "task-001", "--json"])
    assert r.exit_code == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["summary"] == "test summary"
    assert data["task_id"] == "task-001"


def test_handoff_write_invalid_json_exit_1(project_dir: Path):
    # D4
    result = runner.invoke(app, ["handoff", "write", "--task", "task-001"], input="not json at all")
    assert result.exit_code == 1


def test_handoff_write_empty_stdin_exit_1(project_dir: Path):
    # D4
    result = runner.invoke(app, ["handoff", "write", "--task", "task-001"], input="")
    assert result.exit_code == 1


def test_handoff_read_no_handoff_exit_2(project_dir: Path):
    # D4
    task_dir = project_dir / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    result = runner.invoke(app, ["handoff", "read", "--task", "task-001"])
    assert result.exit_code == 2


def test_handoff_read_returns_latest(project_dir: Path):
    # D4
    for phase_pair in (
        ("plan", "build"),
        ("build", "eval"),
    ):
        src, tgt = phase_pair
        payload = {
            "source_phase": src,
            "target_phase": tgt,
            "task_id": "task-001",
            "summary": f"from {src}",
            "schema_version": 3,
        }
        w = runner.invoke(app, ["handoff", "write", "--task", "task-001"], input=json.dumps(payload))
        assert w.exit_code == 0, w.stdout + w.stderr
    r = runner.invoke(app, ["handoff", "read", "--task", "task-001", "--json"])
    assert r.exit_code == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["source_phase"] == "build"
    assert data["summary"] == "from build"


# --- D5: Session CLI ---


def test_session_write_read_cli(project_dir: Path):
    # D5
    session_json = json.dumps(
        {
            "task_id": "task-001",
            "current_phase": "build",
            "current_step": "2/7",
            "current_state": "implementing",
            "next_step": "run tests",
        }
    )
    w = runner.invoke(app, ["session", "write", "--task", "task-001"], input=session_json)
    assert w.exit_code == 0, w.stdout + w.stderr
    r = runner.invoke(app, ["session", "read", "--task", "task-001"])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert "implementing" in r.stdout
    assert "run tests" in r.stdout


def test_session_read_json_output(project_dir: Path):
    # D5
    session_json = json.dumps(
        {
            "task_id": "task-001",
            "current_phase": "build",
            "current_step": "1",
            "current_state": "s",
            "next_step": "n",
        }
    )
    runner.invoke(app, ["session", "write", "--task", "task-001"], input=session_json)
    r = runner.invoke(app, ["session", "read", "--task", "task-001", "--json"])
    assert r.exit_code == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["current_phase"] == "build"
    assert data["task_id"] == "task-001"


def test_session_write_invalid_json_exit_1(project_dir: Path):
    # D5
    result = runner.invoke(app, ["session", "write", "--task", "task-001"], input="{")
    assert result.exit_code == 1


def test_session_read_no_session_exit_2(project_dir: Path):
    # D5
    task_dir = project_dir / ".harness-flow" / "tasks" / "task-002"
    task_dir.mkdir(parents=True)
    result = runner.invoke(app, ["session", "read", "--task", "task-002"])
    assert result.exit_code == 2


# --- D6: Context budget ---


def test_context_budget_normal(project_dir: Path):
    # D6
    task_dir = project_dir / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    body = "hello" * 100
    (task_dir / "plan.md").write_text(body, encoding="utf-8")
    r = runner.invoke(app, ["context-budget", "--task", "task-001", "--json"])
    assert r.exit_code == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["total_chars"] == len(body)
    assert data["total_tokens"] == len(body) // 4


def test_context_budget_empty_dir(project_dir: Path):
    # D6
    r = runner.invoke(app, ["context-budget", "--task", "task-999", "--json"])
    assert r.exit_code == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["total_tokens"] == 0
    assert data["artifacts"] == []


def test_context_budget_over_threshold_exit_1(project_dir: Path):
    # D6
    task_dir = project_dir / ".harness-flow" / "tasks" / "task-998"
    task_dir.mkdir(parents=True)
    # Default budget 50000 tokens → need >200000 chars
    (task_dir / "plan.md").write_text("x" * 200_004, encoding="utf-8")
    r = runner.invoke(app, ["context-budget", "--task", "task-998", "--json"])
    assert r.exit_code == 1, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["over_budget"] is True


def test_context_budget_json_output(project_dir: Path):
    # D6
    task_dir = project_dir / ".harness-flow" / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    r = runner.invoke(app, ["context-budget", "--task", "task-001", "--json"])
    assert r.exit_code == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    for key in ("task", "budget_tokens", "total_tokens", "over_budget", "artifacts"):
        assert key in data
    assert isinstance(data["artifacts"], list)


# --- D7: Config ---


def test_config_context_budget_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # D7
    monkeypatch.chdir(tmp_path)
    harness = tmp_path / ".harness-flow"
    harness.mkdir()
    (harness / "config.toml").write_text(
        '[project]\nname = "legacy"\n\n[ci]\ncommand = "pytest"\n\n[workflow]\ntrunk_branch = "main"\n',
        encoding="utf-8",
    )
    cfg = HarnessConfig.load(tmp_path)
    assert hasattr(cfg.workflow, "context_budget_tokens")
    assert cfg.workflow.context_budget_tokens == 50000
    assert WorkflowConfig().context_budget_tokens == 50000


# --- D8: Template routing ---


def test_ship_template_size(tmp_path: Path):
    # D8
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    ship = (root / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert len(ship) < 18_000


def test_eval_template_size(tmp_path: Path):
    # D8
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    eval_skill = (root / ".cursor" / "skills" / "harness" / "harness-eval" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert len(eval_skill) < 10_000


def test_ship_template_has_routing_pointers(tmp_path: Path):
    # D8
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    ship = (root / ".cursor" / "skills" / "harness" / "harness-ship" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "MUST read" in ship
    assert ".cursor/skills/harness/harness-ship/ship-test-triage.md" in ship
    assert ".cursor/skills/harness/harness-ship/ship-pr-protocol.md" in ship


# --- D9: Resume directive ---


def test_resume_directive_in_rendered_skills(tmp_path: Path):
    # D9
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    base = root / ".cursor" / "skills" / "harness"
    for name in ("harness-build", "harness-ship", "harness-eval"):
        text = (base / name / "SKILL.md").read_text(encoding="utf-8")
        assert "Recovery after interruption" in text


# --- D10: Build template ---


def test_build_template_has_handoff_read(tmp_path: Path):
    # D10
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    build = (root / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "harness handoff read" in build


def test_build_template_has_session_write(tmp_path: Path):
    # D10
    root = _setup_project(tmp_path)
    cfg = HarnessConfig.load(root)
    generate_native_artifacts(root, cfg=cfg, lang="en")
    build = (root / ".cursor" / "skills" / "harness" / "harness-build" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "harness session write" in build
