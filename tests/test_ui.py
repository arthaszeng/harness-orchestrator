"""HarnessUI 单元测试"""

from __future__ import annotations

import io
import time

from rich.console import Console

from harness.core.ui import (
    CYBER_THEME,
    HarnessUI,
    _TailRenderable,
    get_ui,
    init_ui,
)


class TestTailRenderable:
    def test_add_lines_respects_maxlen(self):
        tail = _TailRenderable("test", "codex", time.monotonic())
        for i in range(20):
            tail.add_line(f"line {i}")
        assert tail.line_count == 20
        assert len(tail.lines) == 5
        assert "line 19" in list(tail.lines)[-1]

    def test_renders_with_prefix(self):
        tail = _TailRenderable("test", "codex", time.monotonic())
        tail.add_line("hello world")
        console = Console(file=io.StringIO(), force_terminal=True, width=80)
        console.print(tail)
        output = console.file.getvalue()
        assert "┊" in output
        assert "hello world" in output

    def test_shows_line_count(self):
        tail = _TailRenderable("test", "codex", time.monotonic())
        tail.add_line("a")
        tail.add_line("b")
        console = Console(file=io.StringIO(), force_terminal=True, width=80)
        console.print(tail)
        output = console.file.getvalue()
        assert "2 lines" in output


class TestHarnessUI:
    def _make_ui(self, verbose: bool = False) -> tuple[HarnessUI, io.StringIO]:
        buf = io.StringIO()
        ui = HarnessUI(verbose=verbose)
        ui.console = Console(
            file=buf, force_terminal=True, width=100,
            theme=CYBER_THEME,
            highlight=False,
        )
        return ui, buf

    def test_banner_contains_harness(self):
        ui, buf = self._make_ui()
        ui.banner("auto", "0.1.0")
        output = buf.getvalue()
        assert "HARNESS" in output or "██" in output
        assert "0.1.0" in output
        assert "auto" in output

    def test_system_status_shows_ide(self):
        ui, buf = self._make_ui()
        ui.system_status()
        output = buf.getvalue()
        assert "Cursor" in output

    def test_task_panel_shows_info(self):
        ui, buf = self._make_ui()
        ui.task_panel("task-001", "implement feature", "agent/feature")
        output = buf.getvalue()
        assert "task-001" in output
        assert "implement feature" in output
        assert "agent/feature" in output

    def test_step_done_success(self):
        ui, buf = self._make_ui()
        ui.step_done("[1/3 planner]", 38.0, True, "locked")
        output = buf.getvalue()
        assert "✓" in output
        assert "planner" in output
        assert "38s" in output
        assert "locked" in output

    def test_step_done_failure_with_tail(self):
        ui, buf = self._make_ui()
        ui.step_done(
            "[2/3 builder]", 45.0, False, "failed",
            fail_tail=["line 1", "line 2", "error: something broke"],
        )
        output = buf.getvalue()
        assert "✗" in output
        assert "builder" in output
        assert "error: something broke" in output

    def test_task_complete(self):
        ui, buf = self._make_ui()
        ui.task_complete("task-001", 4.2, 235.0)
        output = buf.getvalue()
        assert "TASK COMPLETE" in output
        assert "task-001" in output
        assert "4.2" in output

    def test_task_blocked(self):
        ui, buf = self._make_ui()
        ui.task_blocked("task-001", 3)
        output = buf.getvalue()
        assert "TASK BLOCKED" in output
        assert "task-001" in output

    def test_session_end(self):
        ui, buf = self._make_ui()
        ui.session_end(5, 1, 3.8)
        output = buf.getvalue()
        assert "SESSION END" in output
        assert "5" in output

    def test_agent_step_verbose_yields_none(self):
        ui, _ = self._make_ui(verbose=True)
        with ui.agent_step("[test]", "codex") as on_out:
            assert on_out is None

    def test_agent_step_default_yields_callback(self):
        ui, _ = self._make_ui(verbose=False)
        with ui.agent_step("[test]", "codex") as on_out:
            assert callable(on_out)
            on_out("test line\n")

    def test_info_warn_error(self):
        ui, buf = self._make_ui()
        ui.info("info msg")
        ui.warn("warn msg")
        ui.error("error msg")
        output = buf.getvalue()
        assert "info msg" in output
        assert "warn msg" in output
        assert "error msg" in output


class TestSingleton:
    def test_init_and_get(self):
        ui1 = init_ui(verbose=True)
        ui2 = get_ui()
        assert ui1 is ui2
        assert ui1.verbose is True

    def test_get_creates_default(self):
        import harness.core.ui as ui_mod
        ui_mod._ui = None
        ui = get_ui()
        assert ui is not None
        assert ui.verbose is False
