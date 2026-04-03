"""Tests for structured stage handoff contract (core/handoff.py)."""

from __future__ import annotations

import json
from pathlib import Path

from harness.core.handoff import (
    HANDOFF_SCHEMA_VERSION,
    PHASE_ORDER,
    Decision,
    OpenItem,
    Risk,
    StageHandoff,
    load_handoff,
    load_latest_handoff,
    save_handoff,
)


def _make_handoff(**overrides) -> StageHandoff:
    defaults = dict(
        source_phase="plan",
        target_phase="build",
        task_id="task-001",
        summary="Plan summary for testing.",
    )
    defaults.update(overrides)
    return StageHandoff(**defaults)


class TestSchemaRoundTrip:
    def test_basic_round_trip(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        handoff = _make_handoff(
            decisions=[Decision(what="use JSON", why="consistency", classification="mechanical")],
            risks=[Risk(description="schema drift", mitigation="versioning", severity="low")],
            open_items=[OpenItem(description="edge case", owner="builder", priority="medium")],
            artifacts_produced=["plan.md"],
            scope_changes=["added D7"],
        )

        path = save_handoff(task_dir, handoff)
        assert path.exists()
        assert path.name == "handoff-plan.json"

        loaded = load_handoff(task_dir, "plan")
        assert loaded is not None
        assert loaded.source_phase == "plan"
        assert loaded.target_phase == "build"
        assert loaded.task_id == "task-001"
        assert loaded.summary == "Plan summary for testing."
        assert len(loaded.decisions) == 1
        assert loaded.decisions[0].what == "use JSON"
        assert len(loaded.risks) == 1
        assert len(loaded.open_items) == 1
        assert loaded.artifacts_produced == ["plan.md"]
        assert loaded.scope_changes == ["added D7"]

    def test_created_at_auto_populated(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        handoff = _make_handoff()
        save_handoff(task_dir, handoff)

        loaded = load_handoff(task_dir, "plan")
        assert loaded is not None
        assert loaded.created_at != ""

    def test_explicit_created_at_preserved(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        handoff = _make_handoff(created_at="2026-04-01T00:00:00+00:00")
        save_handoff(task_dir, handoff)

        loaded = load_handoff(task_dir, "plan")
        assert loaded is not None
        assert loaded.created_at == "2026-04-01T00:00:00+00:00"

    def test_non_ascii_content_round_trip(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        handoff = _make_handoff(summary="中文摘要：计划已完成，包含关键决策。")
        save_handoff(task_dir, handoff)

        loaded = load_handoff(task_dir, "plan")
        assert loaded is not None
        assert "中文摘要" in loaded.summary


class TestLoadHandoff:
    def test_missing_file_returns_none(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        assert load_handoff(task_dir, "plan") is None

    def test_corrupted_json_returns_none(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        (task_dir / "handoff-plan.json").write_text("{broken", encoding="utf-8")
        assert load_handoff(task_dir, "plan") is None

    def test_valid_json_invalid_schema_returns_none(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        (task_dir / "handoff-plan.json").write_text(
            json.dumps({"schema_version": HANDOFF_SCHEMA_VERSION, "source_phase": "plan"}),
            encoding="utf-8",
        )
        assert load_handoff(task_dir, "plan") is None

    def test_wrong_schema_version_still_loads_when_shape_valid(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        handoff = _make_handoff()
        save_handoff(task_dir, handoff)
        path = task_dir / "handoff-plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["schema_version"] = 999
        path.write_text(json.dumps(data), encoding="utf-8")

        loaded = load_handoff(task_dir, "plan")
        assert loaded is not None
        assert loaded.source_phase == "plan"
        assert loaded.target_phase == "build"

    def test_unknown_extra_fields_ignored(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        handoff = _make_handoff()
        save_handoff(task_dir, handoff)
        path = task_dir / "handoff-plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["future_field"] = "should be ignored"
        path.write_text(json.dumps(data), encoding="utf-8")

        loaded = load_handoff(task_dir, "plan")
        assert loaded is not None
        assert loaded.source_phase == "plan"

    def test_non_dict_json_returns_none(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        (task_dir / "handoff-plan.json").write_text("[1, 2, 3]", encoding="utf-8")
        assert load_handoff(task_dir, "plan") is None

    def test_non_utf8_json_returns_none(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        (task_dir / "handoff-plan.json").write_bytes(b"\xff\xfe")
        assert load_handoff(task_dir, "plan") is None


class TestSaveHandoff:
    def test_creates_task_dir(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        assert not task_dir.exists()
        handoff = _make_handoff()
        save_handoff(task_dir, handoff)
        assert task_dir.exists()
        assert (task_dir / "handoff-plan.json").exists()

    def test_each_phase_produces_correct_filename(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        for phase in PHASE_ORDER:
            target = PHASE_ORDER[(PHASE_ORDER.index(phase) + 1) % len(PHASE_ORDER)]
            h = _make_handoff(source_phase=phase, target_phase=target)
            path = save_handoff(task_dir, h)
            assert path.name == f"handoff-{phase}.json"


class TestSummaryMaxLength:
    def test_overlength_summary_rejected_on_validation(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _make_handoff(summary="x" * 2001)


class TestLoadLatestHandoff:
    def test_returns_most_advanced_phase(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        save_handoff(task_dir, _make_handoff(source_phase="plan", target_phase="build"))
        save_handoff(task_dir, _make_handoff(source_phase="eval", target_phase="ship"))

        latest = load_latest_handoff(task_dir)
        assert latest is not None
        assert latest.source_phase == "eval"

    def test_skips_corrupted_and_returns_next(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        save_handoff(task_dir, _make_handoff(source_phase="plan", target_phase="build"))
        save_handoff(task_dir, _make_handoff(source_phase="build", target_phase="eval"))
        (task_dir / "handoff-eval.json").write_text("{broken", encoding="utf-8")

        latest = load_latest_handoff(task_dir)
        assert latest is not None
        assert latest.source_phase == "build"

    def test_no_handoffs_returns_none(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        assert load_latest_handoff(task_dir) is None

    def test_nonexistent_dir_returns_none(self, tmp_path: Path):
        task_dir = tmp_path / "task-999"
        assert load_latest_handoff(task_dir) is None

    def test_all_corrupted_returns_none(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        for phase in PHASE_ORDER:
            (task_dir / f"handoff-{phase}.json").write_text("{bad", encoding="utf-8")
        assert load_latest_handoff(task_dir) is None


class TestPhaseOrder:
    def test_phase_order_is_canonical(self):
        assert PHASE_ORDER == ("plan", "build", "eval", "ship")

    def test_all_phases_produce_valid_handoff(self, tmp_path: Path):
        task_dir = tmp_path / "task-001"
        for i, phase in enumerate(PHASE_ORDER):
            target = PHASE_ORDER[(i + 1) % len(PHASE_ORDER)]
            h = _make_handoff(source_phase=phase, target_phase=target)
            save_handoff(task_dir, h)
            loaded = load_handoff(task_dir, phase)
            assert loaded is not None
            assert loaded.source_phase == phase
