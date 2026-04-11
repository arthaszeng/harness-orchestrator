"""EventEmitter tests — verify JSONL backward compatibility.

The ``runtime`` parameter in Python is serialized as ``driver`` in JSONL
to preserve backward compatibility with existing audit logs.
"""

from __future__ import annotations

import json
from pathlib import Path

from harness.core.events import EventEmitter


class TestJSONLBackwardCompat:
    """JSONL output must contain the ``driver`` key, not ``runtime``."""

    def _read_events(self, agents_dir: Path) -> list[dict]:
        jsonl = agents_dir / "runs" / "test-session" / "events.jsonl"
        return [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]

    def test_agent_start_emits_driver_key(self, tmp_path: Path) -> None:
        emitter = EventEmitter(tmp_path, "test-session")
        emitter.agent_start(role="builder", runtime="cursor", agent_name="b", iteration=1)
        events = self._read_events(tmp_path)
        assert len(events) == 1
        assert "driver" in events[0], "JSONL must use 'driver' key for backward compat"
        assert "runtime" not in events[0], "JSONL must NOT use 'runtime' key"
        assert events[0]["driver"] == "cursor"

    def test_agent_end_emits_driver_key(self, tmp_path: Path) -> None:
        emitter = EventEmitter(tmp_path, "test-session")
        emitter.agent_end(
            role="builder", runtime="cursor", agent_name="b", iteration=1,
            exit_code=0, success=True, output_len=100, elapsed_ms=500,
        )
        events = self._read_events(tmp_path)
        assert len(events) == 1
        assert "driver" in events[0]
        assert "runtime" not in events[0]
        assert events[0]["driver"] == "cursor"

    def test_default_runtime_value(self, tmp_path: Path) -> None:
        emitter = EventEmitter(tmp_path, "test-session")
        emitter.agent_start(role="builder", agent_name="b", iteration=0)
        events = self._read_events(tmp_path)
        assert events[0]["driver"] == "cursor"


class TestEventEmitterHandleReuse:
    """EventEmitter should reuse a single file handle and support close."""

    def _read_events(self, agents_dir: Path) -> list[dict]:
        jsonl = agents_dir / "runs" / "test-session" / "events.jsonl"
        return [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]

    def test_multiple_emits_reuse_single_handle(self, tmp_path: Path) -> None:
        emitter = EventEmitter(tmp_path, "test-session")
        emitter.agent_start(role="builder", agent_name="b", iteration=1)
        handle_after_first = emitter._file
        assert handle_after_first is not None

        emitter.ci_result(command="test", exit_code=0, verdict="PASS", elapsed_ms=100)
        assert emitter._file is handle_after_first

        events = self._read_events(tmp_path)
        assert len(events) == 2
        emitter.close()

    def test_close_then_reopen_on_next_emit(self, tmp_path: Path) -> None:
        emitter = EventEmitter(tmp_path, "test-session")
        emitter.agent_start(role="builder", agent_name="b", iteration=1)
        first_handle = emitter._file
        emitter.close()
        assert emitter._file is None

        emitter.ci_result(command="test", exit_code=0, verdict="PASS", elapsed_ms=100)
        assert emitter._file is not None
        assert emitter._file is not first_handle

        events = self._read_events(tmp_path)
        assert len(events) == 2
        emitter.close()

    def test_context_manager(self, tmp_path: Path) -> None:
        with EventEmitter(tmp_path, "test-session") as emitter:
            emitter.agent_start(role="builder", agent_name="b", iteration=1)
            assert emitter._file is not None
        assert emitter._file is None

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        emitter = EventEmitter(tmp_path, "test-session")
        emitter.agent_start(role="builder", agent_name="b", iteration=1)
        emitter.close()
        emitter.close()  # should not raise
