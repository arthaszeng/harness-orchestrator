"""cursor.py tests — stream-json parsing and prompt composition"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from harness.drivers.cursor import CursorDriver, _format_event, _compose_full_output


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture_events() -> list[dict]:
    """Load cursor stream-json fixture as parsed events."""
    path = FIXTURES_DIR / "cursor-stream-json-sample.jsonl"
    events = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            events.append(json.loads(line))
    return events


def test_format_event_file_read() -> None:
    evt = {"type": "tool_call", "subtype": "started", "tool_call": {"fileReadToolCall": {"filePath": "foo.py"}}}
    assert _format_event(evt) == "[read] foo.py"


def test_format_event_file_edit() -> None:
    evt = {"type": "tool_call", "subtype": "started", "tool_call": {"fileEditToolCall": {"filePath": "bar.py"}}}
    assert _format_event(evt) == "[edit] bar.py"


def test_format_event_shell() -> None:
    evt = {"type": "tool_call", "subtype": "started", "tool_call": {"shellToolCall": {"command": "pytest"}}}
    assert _format_event(evt) == "[shell] pytest"


def test_format_event_mcp_tool() -> None:
    evt = {"type": "tool_call", "subtype": "started", "tool_call": {"mcpToolCall": {"toolName": "search_memory"}}}
    assert _format_event(evt) == "[tool] search_memory"


def test_format_event_mcp_rejected() -> None:
    evt = {
        "type": "tool_call", "subtype": "completed",
        "tool_call": {"mcpToolCall": {"toolName": "x", "result": {"rejected": {"reason": "not configured"}}}},
    }
    assert "rejected" in _format_event(evt)


def test_format_event_assistant() -> None:
    evt = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello world"}]}}
    assert _format_event(evt) == "[out] Hello world"


def test_format_event_result() -> None:
    evt = {"type": "result", "result": "done", "is_error": False, "duration_ms": 5000}
    result = _format_event(evt)
    assert "[result] ok" in result
    assert "5s" in result


def test_format_event_result_error() -> None:
    evt = {"type": "result", "result": "failed", "is_error": True, "duration_ms": 1000}
    assert "[result] error" in _format_event(evt)


def test_format_event_ignores_completed_tool_calls() -> None:
    evt = {"type": "tool_call", "subtype": "completed", "tool_call": {"fileEditToolCall": {}}}
    assert _format_event(evt) is None


def test_compose_full_output() -> None:
    log = ["[read] foo.py", "[edit] bar.py"]
    result = _compose_full_output(log, "All done")
    assert "== EVENT LOG ==" in result
    assert "[read] foo.py" in result
    assert "== RESULT ==" in result
    assert "All done" in result


def test_compose_full_output_empty_log() -> None:
    result = _compose_full_output([], "Result text")
    assert "== EVENT LOG ==" not in result
    assert "Result text" in result


def test_fixture_events_parse_correctly() -> None:
    """Verify that the golden fixture can be fully parsed and produces expected event log."""
    events = _load_fixture_events()
    assert len(events) == 10

    formatted = [_format_event(evt) for evt in events]
    non_none = [f for f in formatted if f is not None]
    assert len(non_none) >= 5

    result_events = [e for e in events if e.get("type") == "result"]
    assert len(result_events) == 1
    assert result_events[0]["result"] == "Feature implemented and tests pass."
    assert result_events[0]["is_error"] is False


def test_compose_prompt_includes_instructions_for_builder() -> None:
    driver = CursorDriver()
    prompt = driver._compose_prompt("harness-builder", "build this", readonly=False)
    assert "build this" in prompt


def test_compose_prompt_readonly_adds_constraint() -> None:
    driver = CursorDriver()
    prompt = driver._compose_prompt("harness-builder", "review", readonly=True)
    assert "只读角色" in prompt


def test_compose_prompt_unknown_role_passthrough() -> None:
    driver = CursorDriver()
    prompt = driver._compose_prompt("unknown-agent", "raw prompt", readonly=False)
    assert prompt == "raw prompt"


@patch("harness.drivers.cursor.subprocess.Popen")
def test_invoke_parses_stream_json(mock_popen: Mock, tmp_path: Path) -> None:
    """Feed the golden fixture into invoke and verify result extraction."""
    fixture_path = FIXTURES_DIR / "cursor-stream-json-sample.jsonl"
    fixture_content = fixture_path.read_text(encoding="utf-8")

    proc = MagicMock()
    proc.stdout = iter(fixture_content.strip().split("\n"))
    proc.stderr = MagicMock()
    proc.returncode = 0
    proc.wait = Mock(return_value=0)
    mock_popen.return_value = proc

    driver = CursorDriver()
    result = driver.invoke("harness-builder", "build feature", tmp_path)

    assert result.success is True
    assert "Feature implemented and tests pass." in result.output
    assert result.exit_code == 0


@patch("harness.drivers.cursor.subprocess.Popen")
def test_invoke_handles_error_result(mock_popen: Mock, tmp_path: Path) -> None:
    error_line = json.dumps({
        "type": "result", "result": "Something went wrong", "is_error": True, "duration_ms": 1000,
    })

    proc = MagicMock()
    proc.stdout = iter([error_line])
    proc.stderr = MagicMock()
    proc.returncode = 1
    proc.wait = Mock(return_value=1)
    mock_popen.return_value = proc

    driver = CursorDriver()
    result = driver.invoke("harness-builder", "fail", tmp_path)

    assert result.success is False
    assert "ERROR:" in result.output
