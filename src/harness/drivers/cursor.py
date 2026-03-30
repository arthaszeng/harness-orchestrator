"""Cursor CLI subprocess 驱动

使用 `cursor agent --print --output-format stream-json --stream-partial-output`
获取流式 JSON 事件，实时展示进度。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from harness.drivers.base import AgentResult

_ROLE_FILES = {
    "harness-builder": "builder.md",
    "harness-reflector": "reflector.md",
}

_STREAM_PREFIX = "    │ "
_HEARTBEAT_INTERVAL = 10


def _format_event(evt: dict) -> str | None:
    """将 cursor stream-json 事件转为可读的单行文本，无关事件返回 None"""
    t = evt.get("type", "")
    sub = evt.get("subtype", "")

    if t == "tool_call" and sub == "started":
        tc = evt.get("tool_call", {})
        # MCP tool call
        mcp = tc.get("mcpToolCall", {})
        if mcp:
            return f"[tool] {mcp.get('toolName', '?')}"
        # Shell / file tool
        shell = tc.get("shellToolCall", {})
        if shell:
            cmd_str = shell.get("command", "")[:80]
            return f"[shell] {cmd_str}"
        file_edit = tc.get("fileEditToolCall", {})
        if file_edit:
            return f"[edit] {file_edit.get('filePath', '?')}"
        file_read = tc.get("fileReadToolCall", {})
        if file_read:
            return f"[read] {file_read.get('filePath', '?')}"
        return f"[tool] {list(tc.keys())}"

    if t == "tool_call" and sub == "completed":
        tc = evt.get("tool_call", {})
        mcp = tc.get("mcpToolCall", {})
        if mcp and mcp.get("result", {}).get("rejected"):
            reason = mcp["result"]["rejected"].get("reason", "")
            return f"[tool] rejected: {reason[:60]}"
        return None

    if t == "assistant":
        content = evt.get("message", {}).get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        text = " ".join(texts).strip()
        if text:
            first_line = text.split("\n")[0][:120]
            return f"[out] {first_line}"
        return None

    if t == "result":
        ok = "ok" if not evt.get("is_error") else "error"
        dur = evt.get("duration_ms", 0) / 1000
        return f"[result] {ok} ({dur:.0f}s)"

    return None


def _compose_full_output(event_log: list[str], final_result: str) -> str:
    """将事件日志和最终结果合并为完整的 build log 输出"""
    parts: list[str] = []
    if event_log:
        parts.append("== EVENT LOG ==")
        parts.extend(event_log)
        parts.append("")
    parts.append("== RESULT ==")
    parts.append(final_result if final_result else "(empty)")
    return "\n".join(parts)


@dataclass
class DriverProbe:
    available: bool
    version: str = ""
    warnings: list[str] = field(default_factory=list)


class CursorDriver:
    """通过 Cursor CLI (stream-json) 调用 agent"""

    def __init__(self) -> None:
        self._probe_result: DriverProbe | None = None

    @property
    def name(self) -> str:
        return "cursor"

    def is_available(self) -> bool:
        return shutil.which("cursor") is not None

    def probe(self) -> DriverProbe:
        """Detect CLI version and validate required flags."""
        if self._probe_result is not None:
            return self._probe_result

        if not self.is_available():
            self._probe_result = DriverProbe(available=False)
            return self._probe_result

        warnings: list[str] = []
        version = ""
        try:
            result = subprocess.run(
                ["cursor", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            version = result.stdout.strip() or result.stderr.strip()
        except Exception:
            warnings.append("could not detect cursor version")

        try:
            help_result = subprocess.run(
                ["cursor", "agent", "--help"],
                capture_output=True, text=True, timeout=10,
            )
            help_text = help_result.stdout + help_result.stderr
            for flag in ("--print", "--output-format", "--stream-partial-output"):
                if flag not in help_text:
                    warnings.append(f"cursor agent may not support {flag}")
        except Exception:
            warnings.append("could not probe cursor agent flags")

        self._probe_result = DriverProbe(available=True, version=version, warnings=warnings)
        return self._probe_result

    def invoke(
        self,
        agent_name: str,
        prompt: str,
        cwd: Path,
        *,
        readonly: bool = False,
        timeout: int = 600,
        on_output: Callable[[str], None] | None = None,
    ) -> AgentResult:
        full_prompt = self._compose_prompt(agent_name, prompt, readonly=readonly)

        cmd = [
            "cursor", "agent",
            "--print",
            "--trust",
            "--workspace", str(cwd),
            "--approve-mcps",
            "--output-format", "stream-json",
            "--stream-partial-output",
        ]

        if readonly:
            cmd.extend(["--mode", "plan"])
        else:
            cmd.append("--force")

        cmd.append(full_prompt)

        try:
            return self._run_stream_json(cmd, cwd, timeout, on_output)
        except FileNotFoundError:
            return AgentResult(success=False, output="Cursor CLI 未找到", exit_code=-1)

    def _run_stream_json(
        self,
        cmd: list[str],
        cwd: Path,
        timeout: int,
        on_output: Callable[[str], None] | None = None,
    ) -> AgentResult:
        """解析 stream-json 事件流，实时输出进度，并记录完整事件日志"""
        start = time.monotonic()
        final_result = ""
        event_log: list[str] = []
        got_first_event = threading.Event()
        heartbeat_stop = threading.Event()

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd),
        )

        def _emit(text: str) -> None:
            if on_output:
                on_output(text + "\n")
            else:
                sys.stderr.write(f"{_STREAM_PREFIX}{text}\n")
                sys.stderr.flush()

        # 心跳线程：Cursor 冷启动时无 stream 事件，避免用户以为卡住
        def _heartbeat() -> None:
            while not heartbeat_stop.is_set():
                heartbeat_stop.wait(_HEARTBEAT_INTERVAL)
                if heartbeat_stop.is_set():
                    break
                if not got_first_event.is_set():
                    elapsed = time.monotonic() - start
                    _emit(f"[thinking] {elapsed:.0f}s...")

        heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
        heartbeat_thread.start()

        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                if not got_first_event.is_set():
                    got_first_event.set()

                try:
                    evt = json.loads(raw_line)
                except json.JSONDecodeError:
                    _emit(raw_line)
                    event_log.append(raw_line)
                    continue

                msg = _format_event(evt)
                if msg:
                    _emit(msg)
                    event_log.append(msg)

                if evt.get("type") == "result":
                    final_result = evt.get("result", "")
                    if evt.get("is_error"):
                        final_result = f"ERROR: {final_result}"

            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return AgentResult(success=False, output="Cursor agent 超时", exit_code=-1)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)

        if not on_output:
            elapsed = time.monotonic() - start
            sys.stderr.write(f"{_STREAM_PREFIX}✓ 完成 ({elapsed:.0f}s)\n")
            sys.stderr.flush()

        is_error = proc.returncode != 0
        full_output = _compose_full_output(event_log, final_result)

        return AgentResult(
            success=not is_error,
            output=full_output,
            exit_code=proc.returncode or 0,
        )

    # ── prompt 组装 ──────────────────────────────────────────────

    def _compose_prompt(self, agent_name: str, prompt: str, *, readonly: bool) -> str:
        developer_instructions = self._load_developer_instructions(agent_name)
        readonly_block = (
            "\n\n## 执行约束\n你当前是只读角色，不要修改代码或执行会改变工作区的操作。"
            if readonly
            else ""
        )
        if not developer_instructions:
            return prompt + readonly_block

        return (
            "## System Context\n"
            "以下内容是 Harness 为当前角色注入的 developer instructions。"
            " 这些约束优先于后续任务描述。\n\n"
            f"{developer_instructions.strip()}"
            "\n\n## Task Input\n"
            f"{prompt.strip()}"
            f"{readonly_block}\n"
        )

    def _load_developer_instructions(self, agent_name: str) -> str:
        role_file = _ROLE_FILES.get(agent_name)
        if not role_file:
            return ""

        agents_dir = Path(__file__).resolve().parents[3] / "agents" / "cursor"
        path = agents_dir / role_file
        if not path.exists():
            return ""

        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
