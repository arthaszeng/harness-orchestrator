"""Tests for the failure pattern library (task-062 + Memverse payload builder)."""

from __future__ import annotations

from pathlib import Path
import pytest

from harness.core.failure_patterns import (
    FAILURE_PATTERNS_FILENAME,
    FailurePattern,
    FailurePatternLoadResult,
    load_failure_patterns,
    save_failure_pattern,
    search_failure_patterns,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save(task_dir: Path, **overrides) -> FailurePattern:
    defaults = dict(
        task_id=task_dir.name,
        phase="build",
        category="test-failure",
        summary="AssertionError in test_foo",
    )
    defaults.update(overrides)
    return save_failure_pattern(task_dir, **defaults)


def _make_agents_dir(tmp_path: Path, task_ids: list[str]) -> Path:
    """Create a .harness-flow directory with multiple task directories."""
    agents_dir = tmp_path / ".harness-flow"
    for tid in task_ids:
        (agents_dir / "tasks" / tid).mkdir(parents=True)
    return agents_dir


# ---------------------------------------------------------------------------
# D1: FailurePattern Pydantic model
# ---------------------------------------------------------------------------

class TestFailurePatternModel:
    def test_valid_model_serialization(self):
        fp = FailurePattern(
            id="fp-abc123",
            task_id="task-001",
            phase="build",
            category="test-failure",
            signature="ASSERTIONERROR IN TEST FOO",
            summary="AssertionError in test_foo",
            first_seen="2026-04-09T00:00:00+00:00",
            last_seen="2026-04-09T00:00:00+00:00",
        )
        data = fp.model_dump()
        assert data["id"] == "fp-abc123"
        assert data["recurrence_count"] == 1
        roundtrip = FailurePattern.model_validate(data)
        assert roundtrip == fp

    def test_model_rejects_empty_summary(self):
        with pytest.raises(Exception):
            FailurePattern(
                id="fp-abc123",
                task_id="task-001",
                phase="build",
                category="test-failure",
                summary="",
            )

    def test_model_rejects_empty_id(self):
        with pytest.raises(Exception):
            FailurePattern(
                id="",
                task_id="task-001",
                phase="build",
                category="test-failure",
                summary="some error",
            )

    def test_recurrence_count_must_be_positive(self):
        with pytest.raises(Exception):
            FailurePattern(
                id="fp-abc",
                task_id="task-001",
                phase="build",
                category="test-failure",
                summary="error",
                recurrence_count=0,
            )

    def test_extra_fields_ignored(self):
        fp = FailurePattern.model_validate({
            "id": "fp-abc",
            "task_id": "task-001",
            "phase": "build",
            "category": "test-failure",
            "summary": "error",
            "unknown_field": "ignored",
        })
        assert fp.id == "fp-abc"

    def test_memverse_sync_excluded_from_dump(self):
        fp = FailurePattern(
            id="fp-abc",
            task_id="task-001",
            phase="build",
            category="test-failure",
            summary="error",
            memverse_sync={"content": "x"},
        )
        data = fp.model_dump()
        assert "memverse_sync" not in data
        assert fp.memverse_sync == {"content": "x"}


# ---------------------------------------------------------------------------
# D2: save / load functions
# ---------------------------------------------------------------------------

class TestSaveAndLoad:
    def test_save_creates_jsonl(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        _save(task_dir, task_id="task-001")

        path = task_dir / FAILURE_PATTERNS_FILENAME
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_save_appends(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        _save(task_dir, task_id="task-001", summary="error one")
        _save(task_dir, task_id="task-001", summary="error two")

        result = load_failure_patterns(task_dir)
        assert len(result.items) == 2
        assert result.items[0].summary == "error one"
        assert result.items[1].summary == "error two"

    def test_save_generates_signature(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        fp = _save(task_dir, task_id="task-001", summary="TypeError: NoneType has no attribute 'foo'")
        assert fp.signature
        assert "TYPEERROR" in fp.signature

    def test_save_generates_unique_ids(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        fp1 = _save(task_dir, task_id="task-001", summary="err1")
        fp2 = _save(task_dir, task_id="task-001", summary="err2")
        assert fp1.id != fp2.id

    def test_load_empty_dir(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir(parents=True)
        result = load_failure_patterns(task_dir)
        assert isinstance(result, FailurePatternLoadResult)
        assert result.items == []
        assert result.errors == []

    def test_load_skips_corrupted_lines(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        _save(task_dir, task_id="task-001", summary="good line")

        path = task_dir / FAILURE_PATTERNS_FILENAME
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"id":"broken"}\n')

        result = load_failure_patterns(task_dir)
        assert len(result.items) == 1
        assert result.items[0].summary == "good line"
        assert len(result.errors) == 1
        assert "line 2" in result.errors[0]

    def test_load_handles_empty_lines(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        _save(task_dir, task_id="task-001", summary="valid")

        path = task_dir / FAILURE_PATTERNS_FILENAME
        content = path.read_text(encoding="utf-8")
        path.write_text("\n" + content + "\n\n", encoding="utf-8")

        result = load_failure_patterns(task_dir)
        assert len(result.items) == 1
        assert result.errors == []

    def test_load_non_utf8_reports_file_error(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / FAILURE_PATTERNS_FILENAME).write_bytes(b"\xff\xfe")

        result = load_failure_patterns(task_dir)
        assert result.items == []
        assert result.errors
        assert result.errors[0].startswith("file:")


# ---------------------------------------------------------------------------
# D3: cross-task search
# ---------------------------------------------------------------------------

class TestSearchFailurePatterns:
    def test_search_across_tasks(self, tmp_path: Path):
        agents_dir = _make_agents_dir(tmp_path, ["task-001", "task-002"])
        t1 = agents_dir / "tasks" / "task-001"
        t2 = agents_dir / "tasks" / "task-002"

        _save(t1, task_id="task-001", summary="ImportError: no module named foo")
        _save(t1, task_id="task-001", summary="TypeError in handler")
        _save(t2, task_id="task-002", summary="ImportError: no module named bar")

        results = search_failure_patterns(agents_dir, query="ImportError")
        assert len(results) == 2
        summaries = {r.summary for r in results}
        assert "ImportError: no module named foo" in summaries
        assert "ImportError: no module named bar" in summaries

    def test_search_category_filter(self, tmp_path: Path):
        agents_dir = _make_agents_dir(tmp_path, ["task-001"])
        t1 = agents_dir / "tasks" / "task-001"

        _save(t1, task_id="task-001", category="ci-failure", summary="CI timeout")
        _save(t1, task_id="task-001", category="test-failure", summary="assert failed")

        results = search_failure_patterns(agents_dir, category="ci-failure")
        assert len(results) == 1
        assert results[0].category == "ci-failure"

    def test_search_category_case_insensitive(self, tmp_path: Path):
        agents_dir = _make_agents_dir(tmp_path, ["task-001"])
        t1 = agents_dir / "tasks" / "task-001"
        _save(t1, task_id="task-001", category="CI-Failure", summary="timeout")

        results = search_failure_patterns(agents_dir, category="ci-failure")
        assert len(results) == 1

    def test_search_empty_query_returns_all(self, tmp_path: Path):
        agents_dir = _make_agents_dir(tmp_path, ["task-001"])
        t1 = agents_dir / "tasks" / "task-001"
        _save(t1, task_id="task-001", summary="error one")
        _save(t1, task_id="task-001", summary="error two")

        results = search_failure_patterns(agents_dir)
        assert len(results) == 2

    def test_search_limit(self, tmp_path: Path):
        agents_dir = _make_agents_dir(tmp_path, ["task-001"])
        t1 = agents_dir / "tasks" / "task-001"
        for i in range(5):
            _save(t1, task_id="task-001", summary=f"error {i}")

        results = search_failure_patterns(agents_dir, limit=2)
        assert len(results) == 2

    def test_search_no_results(self, tmp_path: Path):
        agents_dir = _make_agents_dir(tmp_path, ["task-001"])
        t1 = agents_dir / "tasks" / "task-001"
        _save(t1, task_id="task-001", summary="some error")

        results = search_failure_patterns(agents_dir, query="nonexistent")
        assert results == []

    def test_search_includes_archive(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        (agents_dir / "tasks" / "task-001").mkdir(parents=True)
        (agents_dir / "archive" / "task-000").mkdir(parents=True)

        _save(agents_dir / "archive" / "task-000", task_id="task-000", summary="old failure")
        _save(agents_dir / "tasks" / "task-001", task_id="task-001", summary="new failure")

        results = search_failure_patterns(agents_dir)
        assert len(results) == 2

    def test_search_empty_agents_dir(self, tmp_path: Path):
        agents_dir = tmp_path / ".harness-flow"
        agents_dir.mkdir(parents=True)
        results = search_failure_patterns(agents_dir)
        assert results == []


# ---------------------------------------------------------------------------
# D5: workflow-state sync
# ---------------------------------------------------------------------------

class TestWorkflowStateSync:
    def test_save_updates_workflow_state_artifact_ref(self, tmp_path: Path):
        from harness.core.workflow_state import WorkflowState, load_workflow_state

        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        WorkflowState(task_id="task-001").save(task_dir)

        _save(task_dir, task_id="task-001")

        state = load_workflow_state(task_dir)
        assert state is not None
        assert state.artifacts.failure_patterns == f".harness-flow/tasks/task-001/{FAILURE_PATTERNS_FILENAME}"


# ---------------------------------------------------------------------------
# D4: CLI integration
# ---------------------------------------------------------------------------

class TestCLI:
    def test_save_failure_cli(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from typer.testing import CliRunner

        from harness.cli import app

        agents_dir = tmp_path / ".harness-flow"
        task_dir = agents_dir / "tasks" / "task-001"
        task_dir.mkdir(parents=True)

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow" / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = ""\n'
            '[models]\ndefault = ""\n[workflow]\n[native]\n'
            '[integrations.memverse]\nenabled = false\n',
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(app, [
            "save-failure",
            "--task", "task-001",
            "--phase", "build",
            "--category", "test-failure",
            "--summary", "AssertionError in test_foo",
        ])
        assert result.exit_code == 0, result.output
        assert "saved" in result.output.lower() or "✓" in result.output

        loaded = load_failure_patterns(task_dir)
        assert len(loaded.items) == 1
        assert loaded.items[0].summary == "AssertionError in test_foo"

    def test_search_failures_cli(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from typer.testing import CliRunner

        from harness.cli import app

        agents_dir = tmp_path / ".harness-flow"
        task_dir = agents_dir / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        _save(task_dir, task_id="task-001", summary="lint error in module X")

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow" / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = ""\n'
            '[models]\ndefault = ""\n[workflow]\n[native]\n'
            '[integrations.memverse]\nenabled = false\n',
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(app, [
            "search-failures",
            "--query", "lint error",
        ])
        assert result.exit_code == 0, result.output
        assert "lint error" in result.output.lower()

    def test_search_failures_no_results(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from typer.testing import CliRunner

        from harness.cli import app

        agents_dir = tmp_path / ".harness-flow"
        (agents_dir / "tasks").mkdir(parents=True)

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow" / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = ""\n'
            '[models]\ndefault = ""\n[workflow]\n[native]\n'
            '[integrations.memverse]\nenabled = false\n',
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(app, ["search-failures"])
        assert result.exit_code == 0, result.output
        assert "no matching" in result.output.lower()


# ---------------------------------------------------------------------------
# Memverse payload builder (MCP-mediated, no network)
# ---------------------------------------------------------------------------

class TestMemversePayloadBuilder:
    """Tests for Memverse upsert payload generation."""

    def test_save_with_memverse_enabled_attaches_sync(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        fp = _save(task_dir, task_id="task-001", memverse_enabled=True)
        assert fp.memverse_sync is not None
        assert fp.memverse_sync["content"].startswith("[failure-pattern]")
        assert fp.memverse_sync["upsert_key"] == "signature"
        assert fp.memverse_sync["domain"] == "harness-flow"

    def test_save_with_memverse_disabled_no_sync(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        fp = _save(task_dir, task_id="task-001", memverse_enabled=False)
        assert fp.memverse_sync is None

    def test_memverse_sync_excluded_from_json(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        fp = _save(task_dir, task_id="task-001", memverse_enabled=True)
        json_str = fp.model_dump_json()
        assert "memverse_sync" not in json_str

    def test_memverse_sync_metadata_has_required_fields(self, tmp_path: Path):
        import json

        task_dir = tmp_path / "task-001"
        fp = _save(
            task_dir,
            task_id="task-001",
            category="ci-failure",
            summary="some CI error",
            memverse_enabled=True,
        )
        meta = json.loads(fp.memverse_sync["metadata"])
        assert meta["type"] == "failure-pattern"
        assert meta["category"] == "ci-failure"
        assert meta["task_id"] == "task-001"
        assert meta["fp_id"] == fp.id
        assert "signature" in meta

    def test_memverse_sync_content_includes_optional_fields(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        fp = save_failure_pattern(
            task_dir,
            task_id="task-001",
            phase="build",
            category="ci-failure",
            summary="import error",
            root_cause="module renamed",
            fix_applied="update import path",
            error_output="ImportError: no module",
            memverse_enabled=True,
        )
        content = fp.memverse_sync["content"]
        assert "Root cause: module renamed" in content
        assert "Fix: update import path" in content
        assert "Error: ImportError: no module" in content

    def test_auto_detect_memverse_disabled(self, tmp_path: Path):
        """Without config, memverse_enabled=None resolves to False."""
        task_dir = tmp_path / "task-001"
        fp = _save(task_dir, task_id="task-001")
        assert fp.memverse_sync is None

    def test_jsonl_always_written_regardless_of_memverse(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        _save(task_dir, task_id="task-001", memverse_enabled=True)
        loaded = load_failure_patterns(task_dir)
        assert len(loaded.items) == 1


class TestCLIJsonOutput:
    """Tests for save-failure --json and memverse_sync output."""

    def _make_config(self, tmp_path: Path, memverse_enabled: bool = False) -> None:
        (tmp_path / ".harness-flow").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".harness-flow" / "tasks" / "task-001").mkdir(parents=True, exist_ok=True)
        enabled = "true" if memverse_enabled else "false"
        (tmp_path / ".harness-flow" / "config.toml").write_text(
            f'[project]\nname = "test"\n[ci]\ncommand = ""\n'
            f'[models]\ndefault = ""\n[workflow]\n[native]\n'
            f'[integrations.memverse]\nenabled = {enabled}\ndomain_prefix = "test-domain"\n',
            encoding="utf-8",
        )

    def test_json_output_memverse_off(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import json
        from typer.testing import CliRunner
        from harness.cli import app
        from harness.core.failure_patterns import _memverse_enabled_cached

        _memverse_enabled_cached.cache_clear()
        self._make_config(tmp_path, memverse_enabled=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, [
            "save-failure", "--json",
            "--task", "task-001", "--phase", "build",
            "--category", "test-failure", "--summary", "some error",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output.strip())
        assert data["task_id"] == "task-001"
        assert data["memverse_sync"] is None
        _memverse_enabled_cached.cache_clear()

    def test_json_output_memverse_on(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import json
        from typer.testing import CliRunner
        from harness.cli import app
        from harness.core.failure_patterns import _memverse_enabled_cached

        _memverse_enabled_cached.cache_clear()
        self._make_config(tmp_path, memverse_enabled=True)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, [
            "save-failure", "--json",
            "--task", "task-001", "--phase", "build",
            "--category", "ci-failure", "--summary", "CI timeout",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output.strip())
        assert data["memverse_sync"] is not None
        assert data["memverse_sync"]["domain"] == "test-domain"
        assert data["memverse_sync"]["upsert_key"] == "signature"
        _memverse_enabled_cached.cache_clear()

    def test_non_json_memverse_on_shows_sync_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from typer.testing import CliRunner
        from harness.cli import app
        from harness.core.failure_patterns import _memverse_enabled_cached

        _memverse_enabled_cached.cache_clear()
        self._make_config(tmp_path, memverse_enabled=True)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, [
            "save-failure",
            "--task", "task-001", "--phase", "build",
            "--category", "ci-failure", "--summary", "lint error",
        ])
        assert result.exit_code == 0, result.output
        assert "MEMVERSE_SYNC:" in result.output
        _memverse_enabled_cached.cache_clear()

    def test_non_json_memverse_off_no_sync_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from typer.testing import CliRunner
        from harness.cli import app
        from harness.core.failure_patterns import _memverse_enabled_cached

        _memverse_enabled_cached.cache_clear()
        self._make_config(tmp_path, memverse_enabled=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, [
            "save-failure",
            "--task", "task-001", "--phase", "build",
            "--category", "ci-failure", "--summary", "some lint error",
        ])
        assert result.exit_code == 0, result.output
        assert "MEMVERSE_SYNC:" not in result.output
        _memverse_enabled_cached.cache_clear()


class TestMemverseCachePerformance:
    """Tests for _is_memverse_enabled lru_cache behavior."""

    def test_cache_avoids_repeated_config_reads(self, tmp_path: Path):
        from harness.core.failure_patterns import _is_memverse_enabled, _memverse_enabled_cached

        _memverse_enabled_cached.cache_clear()

        project_root = tmp_path
        (project_root / ".harness-flow").mkdir(parents=True)
        (project_root / ".harness-flow" / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = ""\n'
            '[models]\ndefault = ""\n[workflow]\n[native]\n'
            '[integrations.memverse]\nenabled = true\n',
            encoding="utf-8",
        )

        result1 = _is_memverse_enabled(project_root / "some-task")
        info_after_first = _memverse_enabled_cached.cache_info()
        assert info_after_first.misses == 1
        assert info_after_first.hits == 0

        result2 = _is_memverse_enabled(project_root / "another-task")
        info_after_second = _memverse_enabled_cached.cache_info()
        assert info_after_second.misses == 1
        assert info_after_second.hits == 1

        assert result1 is True
        assert result2 is True

        _memverse_enabled_cached.cache_clear()

    def test_cache_clear_resets(self, tmp_path: Path):
        from harness.core.failure_patterns import _is_memverse_enabled, _memverse_enabled_cached

        _memverse_enabled_cached.cache_clear()

        project_root = tmp_path
        (project_root / ".harness-flow").mkdir(parents=True)
        (project_root / ".harness-flow" / "config.toml").write_text(
            '[project]\nname = "test"\n[ci]\ncommand = ""\n'
            '[models]\ndefault = ""\n[workflow]\n[native]\n'
            '[integrations.memverse]\nenabled = false\n',
            encoding="utf-8",
        )

        assert _is_memverse_enabled(project_root / "task") is False
        assert _memverse_enabled_cached.cache_info().currsize == 1

        _memverse_enabled_cached.cache_clear()
        assert _memverse_enabled_cached.cache_info().currsize == 0

        assert _is_memverse_enabled(project_root / "task") is False
        assert _memverse_enabled_cached.cache_info().misses == 1


class TestTemplateRendering:
    """Tests for failure pattern template sections in rendered skills."""

    def _render_skill(self, name: str, memverse_enabled: bool = True, lang: str = "en") -> str:
        """Render a single skill template and return its content."""
        from harness.native.skill_gen import _build_full_context, _filter_context, _render_template
        from harness.core.config import HarnessConfig

        cfg = HarnessConfig.model_validate({
            "project": {"name": "test", "lang": lang},
            "ci": {"command": "make test"},
            "integrations": {"memverse": {"enabled": memverse_enabled, "domain_prefix": "test-proj"}},
        })

        full_ctx = _build_full_context(cfg, lang=lang)
        ctx = _filter_context(full_ctx, "skill", f"harness-{name}")

        tmpl_dir = Path(__file__).resolve().parent.parent / "src" / "harness" / "templates" / "native"
        if lang != "en":
            tmpl_name = f"{lang}/skill-{name}.md.j2"
        else:
            tmpl_name = f"skill-{name}.md.j2"
        return _render_template(tmpl_dir, tmpl_name, ctx)

    def test_build_skill_contains_failure_pattern_includes(self):
        content = self._render_skill("build", memverse_enabled=True)
        assert "harness save-failure" in content
        assert "harness search-failures" in content

    def test_build_skill_zh_contains_failure_pattern_includes(self):
        content = self._render_skill("build", memverse_enabled=True, lang="zh")
        assert "harness save-failure" in content

    def test_memverse_disabled_no_upsert_in_build(self):
        content = self._render_skill("build", memverse_enabled=False)
        assert "harness save-failure" in content
        assert "upsert_memory" not in content


class TestMemversePayloadModule:
    """Unit tests for harness.integrations.memverse payload builders."""

    def test_build_upsert_payload(self):
        from harness.integrations.memverse import build_upsert_payload
        sync = build_upsert_payload(
            summary="test error",
            category="ci-failure",
            phase="build",
            task_id="task-001",
            fp_id="fp-abc",
            signature="TEST ERROR",
            first_seen="2026-04-09T00:00:00+00:00",
        )
        d = sync.payload.as_dict()
        assert d["domain"] == "harness-flow"
        assert d["upsert_key"] == "signature"
        assert "[failure-pattern] test error" in d["content"]

    def test_build_search_payload(self):
        from harness.integrations.memverse import build_search_payload
        payload = build_search_payload(query="import error", category="ci-failure")
        d = payload.as_dict()
        assert d["query"] == "import error"
        assert d["domains"] == "harness-flow"
        assert '"type": "failure-pattern"' in d["metadata_filter"]
        assert '"category": "ci-failure"' in d["metadata_filter"]

    def test_payload_as_dict_is_json_serializable(self):
        import json
        from harness.integrations.memverse import build_upsert_payload
        sync = build_upsert_payload(
            summary="x", category="y", phase="z", task_id="t",
            fp_id="fp", signature="SIG", first_seen="now",
        )
        serialized = json.dumps(sync.payload.as_dict())
        assert isinstance(serialized, str)
