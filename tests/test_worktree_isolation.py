"""Tests for worktree isolation — concurrent safety, idempotency, and edge cases.

Focuses on gaps NOT covered by existing test_worktree.py / test_worktree_lifecycle.py:
- Concurrent registry writes (multi-threaded last-writer-wins behavior)
- Artifact copy idempotency (consecutive double-invoke)
- Concurrent create_worktree with same task key (race condition)
- detect_worktree edge cases (malformed git output)
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.core.worktree_lifecycle import (
    REGISTRY_VERSION,
    WorktreeLifecycleManager,
)
from harness.integrations.git_ops import GitOperationResult


def _make_config(tmp_path: Path) -> None:
    hf = tmp_path / ".harness-flow"
    hf.mkdir(parents=True, exist_ok=True)
    (hf / "config.toml").write_text(
        "[project]\nname = 'test-proj'\nlang = 'en'\n\n"
        "[workflow]\nbranch_prefix = 'agent'\ntrunk_branch = 'main'\n\n"
        "[ci]\ncommand = 'echo ok'\n",
        encoding="utf-8",
    )


def _ok_result(**kw: object) -> GitOperationResult:
    return GitOperationResult(ok=True, code="OK", message="ok", **kw)


class TestConcurrentRegistryWrite:
    """Registry writes under concurrent access — documented behavior: last-writer-wins.

    The registry uses tempfile + os.replace for single-write atomicity.
    It does NOT use file locks, so concurrent read-modify-write may lose updates.
    These tests verify the invariant: final file is always valid JSON, never corrupt.
    """

    def test_concurrent_writes_produce_valid_json(self, tmp_path: Path):
        """Two threads writing registry simultaneously must not corrupt the file."""
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        barrier = threading.Barrier(2, timeout=5)
        errors: list[Exception] = []

        def write_entry(task_num: int) -> None:
            try:
                barrier.wait()
                entries = mgr._read_registry()
                entries.append({
                    "task_key": f"task-{task_num:03d}",
                    "branch": f"agent/task-{task_num:03d}",
                    "path": f"/tmp/wt-{task_num}",
                    "created_at": "2026-01-01T00:00:00Z",
                    "status": "active",
                })
                mgr._write_registry(entries)
            except Exception as exc:
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(write_entry, i) for i in (1, 2)]
            for f in as_completed(futures):
                f.result()

        assert not errors, f"Thread errors: {errors}"

        raw = mgr._registry_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, dict)
        assert "version" in data
        assert data["version"] == REGISTRY_VERSION
        assert isinstance(data.get("worktrees"), list)

        entries = data["worktrees"]
        assert len(entries) >= 1, "At least one write must survive"
        for entry in entries:
            assert "task_key" in entry

    def test_rapid_sequential_writes_no_corruption(self, tmp_path: Path):
        """Many rapid sequential writes must all produce valid JSON."""
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        for i in range(20):
            entries = mgr._read_registry()
            entries.append({
                "task_key": f"task-{i:03d}",
                "branch": f"agent/task-{i:03d}",
                "path": f"/tmp/wt-{i}",
            })
            mgr._write_registry(entries)

        final = mgr._read_registry()
        assert len(final) == 20
        keys = {e["task_key"] for e in final}
        assert len(keys) == 20


class TestArtifactCopyIdempotency:
    """Consecutive _copy_artifacts calls must not corrupt or duplicate content."""

    def test_double_copy_preserves_content(self, tmp_path: Path):
        """Calling _copy_artifacts twice keeps files intact with correct content."""
        _make_config(tmp_path)

        (tmp_path / ".cursor" / "skills" / "harness").mkdir(parents=True)
        (tmp_path / ".cursor" / "skills" / "harness" / "SKILL.md").write_text("skill-v1")
        (tmp_path / ".cursor" / "agents").mkdir(parents=True)
        (tmp_path / ".cursor" / "agents" / "arch.md").write_text("architect")
        (tmp_path / ".cursor" / "rules").mkdir(parents=True)
        (tmp_path / ".cursor" / "rules" / "wf.mdc").write_text("rule")
        (tmp_path / ".cursor" / "worktrees.json").write_text('{"v":1}')
        (tmp_path / ".harness-flow" / "vision.md").write_text("vision-content")

        mgr = WorktreeLifecycleManager(tmp_path)
        target = tmp_path / "wt-target"
        target.mkdir()

        mgr._copy_artifacts(target)
        mgr._copy_artifacts(target)

        assert (target / ".cursor" / "skills" / "harness" / "SKILL.md").read_text() == "skill-v1"
        assert (target / ".cursor" / "agents" / "arch.md").read_text() == "architect"
        assert (target / ".cursor" / "rules" / "wf.mdc").read_text() == "rule"
        assert (target / ".cursor" / "worktrees.json").read_text() == '{"v":1}'
        assert (target / ".harness-flow" / "config.toml").is_file()
        assert (target / ".harness-flow" / "vision.md").read_text() == "vision-content"

    def test_copy_with_preexisting_modified_target(self, tmp_path: Path):
        """If target already has a locally modified file, copy overwrites it."""
        _make_config(tmp_path)

        (tmp_path / ".cursor").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".cursor" / "worktrees.json").write_text('{"source":true}')

        mgr = WorktreeLifecycleManager(tmp_path)
        target = tmp_path / "wt-target"
        target.mkdir()
        (target / ".cursor").mkdir(parents=True)
        (target / ".cursor" / "worktrees.json").write_text('{"local_edit":true}')

        mgr._copy_artifacts(target)

        assert json.loads((target / ".cursor" / "worktrees.json").read_text()) == {"source": True}


class TestConcurrentCreateWorktreeSameKey:
    """Two threads calling create_worktree with the same task key concurrently.

    Under full mock (run_git_result always ok), the path-exists guard is the
    primary mutual exclusion mechanism.  With Barrier-synced reads, both threads
    may pass the registry-duplicate check simultaneously (known LWW limitation).

    Invariants tested:
    - Both threads complete without crash
    - Final registry is valid JSON with correct schema
    - At least one task-099 entry exists in registry
    """

    def test_concurrent_create_same_key_no_corruption(self, tmp_path: Path):
        _make_config(tmp_path)
        mgr = WorktreeLifecycleManager(tmp_path)

        barrier = threading.Barrier(2, timeout=5)
        results: list[object] = [None, None]

        original_read = mgr._read_registry

        def delayed_read_registry() -> list[dict]:
            data = original_read()
            barrier.wait()
            return data

        def create_in_thread(idx: int) -> None:
            with (
                patch.object(mgr, "_read_registry", side_effect=delayed_read_registry),
                patch("harness.core.worktree_lifecycle.run_git_result", return_value=_ok_result()),
                patch.object(mgr, "_copy_artifacts"),
            ):
                results[idx] = mgr.create_worktree("task-099", short_desc="race")

        wt_path = tmp_path.parent / f"{tmp_path.name}-wt-task-099"

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(create_in_thread, i) for i in range(2)]
                for f in as_completed(futures):
                    f.result()

            assert all(r is not None for r in results), "Both threads must complete"

            reg_text = mgr._registry_path.read_text(encoding="utf-8")
            data = json.loads(reg_text)
            assert isinstance(data, dict)
            assert data.get("version") == REGISTRY_VERSION
            assert isinstance(data.get("worktrees"), list)

            task_099_entries = [e for e in data["worktrees"] if e.get("task_key") == "task-099"]
            assert len(task_099_entries) >= 1, "At least one registration must exist"
        finally:
            import shutil
            if wt_path.exists():
                shutil.rmtree(wt_path)


class TestDetectWorktreeEdgeCases:
    """Edge cases for detect_worktree not covered by test_worktree.py.

    Existing coverage: normal repo, worktree, git failure, exception, relative paths.
    New cases: malformed stdout, empty stdout, whitespace-only output.
    """

    def test_malformed_git_output_with_null_bytes(self, tmp_path: Path):
        """Git returning null bytes causes ValueError in Path.resolve().

        BUG FOUND: detect_worktree wraps run_git in try/except but does NOT
        catch exceptions from subsequent Path operations (strip/resolve).
        Null bytes in stdout → ValueError: embedded null byte.
        This test documents the current (broken) behavior.
        """
        import subprocess
        from harness.core.worktree import detect_worktree

        def mock_run(args, cwd, *, timeout=30):
            return subprocess.CompletedProcess(args, 0, stdout="\x00\xff\n")

        with patch("harness.core.worktree.run_git", side_effect=mock_run):
            with pytest.raises(ValueError, match="null byte"):
                detect_worktree(tmp_path)

    def test_malformed_git_output_no_null(self, tmp_path: Path):
        """Git returning non-path garbage (no null bytes) should not crash.

        When both common_dir and git_dir resolve to different garbage paths,
        detect_worktree may return a WorktreeInfo with those paths.  The key
        invariant: no unhandled exception.
        """
        import subprocess
        from harness.core.worktree import detect_worktree

        def mock_run(args, cwd, *, timeout=30):
            return subprocess.CompletedProcess(args, 0, stdout="!@#$%^&*()\n")

        with patch("harness.core.worktree.run_git", side_effect=mock_run):
            result = detect_worktree(tmp_path)
            assert result is None

    def test_empty_stdout(self, tmp_path: Path):
        """Git returning empty output should return None."""
        import subprocess
        from harness.core.worktree import detect_worktree

        def mock_run(args, cwd, *, timeout=30):
            return subprocess.CompletedProcess(args, 0, stdout="")

        with patch("harness.core.worktree.run_git", side_effect=mock_run):
            result = detect_worktree(tmp_path)
            assert result is None

    def test_whitespace_only_stdout(self, tmp_path: Path):
        """Git returning whitespace-only output should not crash.

        After strip(), both paths resolve to the same dir (cwd), so
        common_dir == git_dir → returns None.
        """
        import subprocess
        from harness.core.worktree import detect_worktree

        def mock_run(args, cwd, *, timeout=30):
            return subprocess.CompletedProcess(args, 0, stdout="   \n  \t  ")

        with patch("harness.core.worktree.run_git", side_effect=mock_run):
            result = detect_worktree(tmp_path)
            assert result is None
