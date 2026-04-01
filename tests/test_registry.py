"""registry / tracker 写库边界测试。

验证 SQLite 文本列在接收 MagicMock、Path 及任意可 str() 化对象时
不触发 sqlite3.ProgrammingError，并能以可读字符串形式落库。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.core.events import NullEventEmitter
from harness.core.registry import Registry
from harness.core.tracker import RunTracker


@pytest.fixture()
def registry(tmp_path: Path) -> Registry:
    return Registry(tmp_path / ".agents")


class _Stringable:
    """仅实现 __str__ 的自定义对象，模拟非基础类型输入。"""

    def __init__(self, label: str) -> None:
        self._label = label

    def __str__(self) -> str:
        return self._label


# ── Registry.register ─────────────────────────────────────────


class TestRegisterNormalization:
    """register() 接收非基础类型参数时正常入库。"""

    def test_mock_runtime_and_agent_name(self, registry: Registry) -> None:
        run_id = registry.register(
            role="builder",
            runtime=MagicMock(),          # type: ignore[arg-type]
            agent_name=MagicMock(),      # type: ignore[arg-type]
        )
        row = registry.get(run_id)
        assert row is not None
        assert isinstance(row.driver, str)
        assert isinstance(row.agent_name, str)

    def test_path_cwd_and_branch(self, registry: Registry) -> None:
        run_id = registry.register(
            role="planner",
            runtime="cursor",
            agent_name="harness-planner",
            cwd=Path("/tmp/workspace"),      # type: ignore[arg-type]
            branch=Path("feature/test"),     # type: ignore[arg-type]
        )
        row = registry.get(run_id)
        assert row is not None
        assert row.cwd == "/tmp/workspace"
        assert row.branch == "feature/test"

    def test_stringable_task_id(self, registry: Registry) -> None:
        run_id = registry.register(
            role="evaluator",
            runtime="cursor",
            agent_name="harness-evaluator",
            task_id=_Stringable("task-099"),     # type: ignore[arg-type]
        )
        row = registry.get(run_id)
        assert row is not None
        assert row.task_id == "task-099"

    def test_all_text_columns_mixed(self, registry: Registry) -> None:
        run_id = registry.register(
            role=_Stringable("builder"),         # type: ignore[arg-type]
            runtime=MagicMock(),                 # type: ignore[arg-type]
            agent_name=Path("agent.toml"),       # type: ignore[arg-type]
            task_id=MagicMock(),                 # type: ignore[arg-type]
            cwd=Path("/workspace"),              # type: ignore[arg-type]
            branch=_Stringable("main"),          # type: ignore[arg-type]
        )
        row = registry.get(run_id)
        assert row is not None
        assert row.role == "builder"
        assert row.branch == "main"


# ── Registry.complete ─────────────────────────────────────────


class TestCompleteNormalization:
    """complete() 接收 Path / Mock 等类型的 log_path、session_id。"""

    def test_path_log_path(self, registry: Registry) -> None:
        run_id = registry.register(role="builder", runtime="cursor", agent_name="b")
        registry.complete(
            run_id,
            log_path=Path("/logs/run.log"),  # type: ignore[arg-type]
        )
        row = registry.get(run_id)
        assert row is not None
        assert row.log_path == "/logs/run.log"
        assert row.status == "completed"

    def test_mock_session_id(self, registry: Registry) -> None:
        run_id = registry.register(role="builder", runtime="cursor", agent_name="b")
        registry.complete(run_id, session_id=MagicMock())  # type: ignore[arg-type]
        row = registry.get(run_id)
        assert row is not None
        assert isinstance(row.session_id, str)

    def test_stringable_log_path_and_session_id(self, registry: Registry) -> None:
        run_id = registry.register(role="builder", runtime="cursor", agent_name="b")
        registry.complete(
            run_id,
            log_path=_Stringable("/var/log/agent.log"),  # type: ignore[arg-type]
            session_id=_Stringable("sess-42"),           # type: ignore[arg-type]
        )
        row = registry.get(run_id)
        assert row is not None
        assert row.log_path == "/var/log/agent.log"
        assert row.session_id == "sess-42"


# ── Registry.fail ─────────────────────────────────────────────


class TestFailNormalization:
    """fail() 接收非基础类型的 error / log_path。"""

    def test_path_log_path(self, registry: Registry) -> None:
        run_id = registry.register(role="builder", runtime="cursor", agent_name="b")
        registry.fail(run_id, log_path=Path("/logs/err.log"))  # type: ignore[arg-type]
        row = registry.get(run_id)
        assert row is not None
        assert row.log_path == "/logs/err.log"
        assert row.status == "failed"

    def test_mock_error(self, registry: Registry) -> None:
        run_id = registry.register(role="builder", runtime="cursor", agent_name="b")
        registry.fail(run_id, error=MagicMock())  # type: ignore[arg-type]
        row = registry.get(run_id)
        assert row is not None
        assert isinstance(row.error, str)


# ── Registry.set_session_id ───────────────────────────────────


class TestSetSessionIdNormalization:
    """set_session_id() 接收 Path / Mock / Stringable。"""

    def test_path_session_id(self, registry: Registry) -> None:
        run_id = registry.register(role="builder", runtime="cursor", agent_name="b")
        registry.set_session_id(run_id, Path("/sessions/abc"))  # type: ignore[arg-type]
        row = registry.get(run_id)
        assert row is not None
        assert row.session_id == "/sessions/abc"

    def test_mock_session_id(self, registry: Registry) -> None:
        run_id = registry.register(role="builder", runtime="cursor", agent_name="b")
        registry.set_session_id(run_id, MagicMock())  # type: ignore[arg-type]
        row = registry.get(run_id)
        assert row is not None
        assert isinstance(row.session_id, str)

    def test_stringable_session_id(self, registry: Registry) -> None:
        run_id = registry.register(role="builder", runtime="cursor", agent_name="b")
        registry.set_session_id(run_id, _Stringable("sess-77"))  # type: ignore[arg-type]
        row = registry.get(run_id)
        assert row is not None
        assert row.session_id == "sess-77"


# ── RunTracker.track — 真实 Registry 路径 ─────────────────────


class TestTrackerWithRealRegistry:
    """RunTracker 透传非基础类型元数据不会在写库阶段报错。"""

    def test_track_success_branch(self, tmp_path: Path) -> None:
        reg = Registry(tmp_path / ".agents")
        tracker = RunTracker(registry=reg, events=NullEventEmitter(), task_id="t-1")

        with tracker.track(
            "builder",
            "cursor",
            "harness-builder",
            1,
            cwd=Path("/work"),           # type: ignore[arg-type]
            branch=_Stringable("dev"),   # type: ignore[arg-type]
        ) as info:
            info.success = True
            info.exit_code = 0
            info.log_path = str(Path("/logs/ok.log"))

        row = reg.get(info.run_id)
        assert row is not None
        assert row.status == "completed"
        assert row.cwd == "/work"
        assert row.branch == "dev"

    def test_track_failure_branch(self, tmp_path: Path) -> None:
        reg = Registry(tmp_path / ".agents")
        tracker = RunTracker(registry=reg, events=NullEventEmitter(), task_id="t-2")

        with tracker.track(
            "evaluator",
            MagicMock(),        # type: ignore[arg-type]
            MagicMock(),        # type: ignore[arg-type]
        ) as info:
            info.success = False
            info.error = "timeout"

        row = reg.get(info.run_id)
        assert row is not None
        assert row.status == "failed"

    def test_track_exception_branch(self, tmp_path: Path) -> None:
        reg = Registry(tmp_path / ".agents")
        tracker = RunTracker(registry=reg, events=NullEventEmitter(), task_id="t-3")

        with pytest.raises(RuntimeError, match="boom"):
            with tracker.track(
                "builder",
                _Stringable("cursor"),   # type: ignore[arg-type]
                "agent-x",
                cwd=MagicMock(),         # type: ignore[arg-type]
            ) as info:
                info.log_path = str(Path("/logs/crash.log"))
                raise RuntimeError("boom")

        row = reg.get(info.run_id)
        assert row is not None
        assert row.status == "failed"
        assert "boom" in (row.error or "")
