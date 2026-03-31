"""Cursor CLI subprocess driver.

Uses `cursor-agent -p --force --output-format stream-json` for streaming
JSON events and live progress.  Prompt is passed via stdin (not CLI arg).

Key design decisions (aligned with CodeMachine-CLI):
- Binary: ``cursor-agent`` (direct Node.js), not ``cursor agent`` (slow Electron shim)
- Prompt: written to stdin as one UTF-8 blob (no ARG_MAX limit, faster parsing)
- Flags: minimal — ``-p --force --output-format stream-json``; no --workspace/--approve-mcps
- stdout and stderr are consumed in parallel threads to avoid pipe deadlock
- Wall-clock timeout is enforced on the *overall* run, not just proc.wait()
- Process-group kill ensures no orphan node/LSP children survive
- Success is determined by combining returncode AND stream result.is_error
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from harness.drivers.base import AgentResult
from harness.drivers import process as proc_mgr
from harness.i18n import get_lang, t

log = logging.getLogger("harness.drivers.cursor")

_ROLE_FILES = {
    "harness-builder": "builder.md",
    "harness-reflector": "reflector.md",
}

_STREAM_PREFIX = "    │ "
_HEARTBEAT_INTERVAL = 10
_THINKING_REPORT_INTERVAL = 20  # show thinking progress every N deltas

# Time without any stdout activity before we consider the process hung
_IDLE_TIMEOUT = 300  # 5 minutes


class _ThinkingTracker:
    """Track extended-thinking deltas and emit periodic progress lines."""

    __slots__ = ("count", "_next_report")

    def __init__(self) -> None:
        self.count = 0
        self._next_report = _THINKING_REPORT_INTERVAL

    def tick(self) -> str | None:
        """Register one thinking/delta; return a progress string at intervals."""
        self.count += 1
        if self.count >= self._next_report:
            self._next_report += _THINKING_REPORT_INTERVAL
            return f"🧠 thinking… ({self.count} tokens)"
        if self.count == 1:
            return "🧠 thinking…"
        return None


def _format_event(evt: dict, thinking: _ThinkingTracker | None = None) -> str | None:
    """Turn a cursor stream-json event into one readable line; unrelated -> None."""
    evt_type = evt.get("type", "")
    sub = evt.get("subtype", "")

    if evt_type == "thinking":
        if thinking is not None:
            return thinking.tick()
        return None

    if evt_type == "tool_call" and sub == "started":
        tc = evt.get("tool_call", {})
        mcp = tc.get("mcpToolCall", {})
        if mcp:
            return f"[tool] {mcp.get('toolName', '?')}"
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

    if evt_type == "tool_call" and sub == "completed":
        tc = evt.get("tool_call", {})
        mcp = tc.get("mcpToolCall", {})
        if mcp and mcp.get("result", {}).get("rejected"):
            reason = mcp["result"]["rejected"].get("reason", "")
            return f"[tool] rejected: {reason[:60]}"
        return None

    if evt_type == "assistant":
        content = evt.get("message", {}).get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        text = " ".join(texts).strip()
        if text:
            first_line = text.split("\n")[0][:120]
            return f"[out] {first_line}"
        return None

    if evt_type == "result":
        ok = "ok" if not evt.get("is_error") else "error"
        dur = evt.get("duration_ms", 0) / 1000
        return f"[result] {ok} ({dur:.0f}s)"

    return None


def _compose_full_output(event_log: list[str], final_result: str) -> str:
    """Merge event log and final result into a full build log string."""
    parts: list[str] = []
    if event_log:
        parts.append("== EVENT LOG ==")
        parts.extend(event_log)
        parts.append("")
    parts.append("== RESULT ==")
    parts.append(final_result if final_result else "(empty)")
    return "\n".join(parts)


# ── Transient / not-ready error detection ────────────────────────────

_NOT_READY_PATTERNS = (
    "cursor-agent not found",
    "not found, installing",
)

_TRANSIENT_ERROR_PATTERNS = (
    "socket hang up",
    "econnreset",
    "econnrefused",
    "etimedout",
    "epipe",
    "rate limit",
    "429",
    "502",
    "503",
    "service unavailable",
    "internal server error",
)

_MAX_RETRIES = 2
_INITIAL_RETRY_DELAY = 3  # seconds; doubles each attempt (exponential backoff)

_PROBE_TIMEOUT = 8


@dataclass
class DriverProbe:
    available: bool
    version: str = ""
    warnings: list[str] = field(default_factory=list)


class CursorDriver:
    """Invoke agents via Cursor CLI (stream-json)."""

    def __init__(self) -> None:
        self._probe_result: DriverProbe | None = None

    @property
    def name(self) -> str:
        return "cursor"

    def is_available(self) -> bool:
        return shutil.which("cursor-agent") is not None

    def probe(self) -> DriverProbe:
        """Detect CLI version and validate that ``cursor-agent`` is functional."""
        if self._probe_result is not None:
            return self._probe_result

        if not self.is_available():
            self._probe_result = DriverProbe(available=False)
            return self._probe_result

        warnings: list[str] = []
        version = ""
        try:
            result = subprocess.run(
                ["cursor-agent", "--version"],
                capture_output=True, text=True, timeout=_PROBE_TIMEOUT,
            )
            version = result.stdout.strip() or result.stderr.strip()
        except Exception:
            warnings.append("could not detect cursor-agent version")

        functional = True
        try:
            help_result = subprocess.run(
                ["cursor-agent", "--help"],
                capture_output=True, text=True, timeout=_PROBE_TIMEOUT,
            )
            help_text = (help_result.stdout + help_result.stderr).lower()

            if help_result.returncode != 0:
                functional = False
                warnings.append(t("driver.cursor_not_ready"))
            else:
                for flag in ("-p", "--output-format", "--force"):
                    if flag not in help_text:
                        warnings.append(f"cursor-agent may not support {flag}")

        except subprocess.TimeoutExpired:
            functional = False
            warnings.append(t("driver.cursor_not_ready"))
        except Exception:
            warnings.append("could not probe cursor-agent flags")

        self._probe_result = DriverProbe(
            available=functional, version=version, warnings=warnings,
        )
        return self._probe_result

    # ── public entry point ────────────────────────────────────────

    def invoke(
        self,
        agent_name: str,
        prompt: str,
        cwd: Path,
        *,
        readonly: bool = False,
        timeout: int = 600,
        on_output: Callable[[str], None] | None = None,
        model: str = "",
    ) -> AgentResult:
        full_prompt = self._compose_prompt(agent_name, prompt, readonly=readonly)

        cmd = [
            "cursor-agent",
            "-p",
            "--force",
            "--output-format", "stream-json",
            "--stream-partial-output",
        ]

        if model:
            cmd.extend(["--model", model])

        if readonly:
            cmd.extend(["--mode", "plan"])

        delay = _INITIAL_RETRY_DELAY
        result: AgentResult | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                result = self._run_stream_json(cmd, cwd, timeout, on_output, stdin_data=full_prompt)
            except FileNotFoundError:
                return AgentResult(success=False, output=t("driver.cursor_not_found"), exit_code=-1)

            if result.success or attempt >= _MAX_RETRIES:
                return result

            if not self._is_retryable(result):
                return result

            sys.stderr.write(
                f"{_STREAM_PREFIX}{t('driver.retry', attempt=attempt + 1, max=_MAX_RETRIES, delay=delay)}\n"
            )
            sys.stderr.flush()
            time.sleep(delay)
            delay = min(delay * 2, 30)  # exponential backoff capped at 30s

        return result  # type: ignore[return-value]  # unreachable

    # ── retryable error detection ─────────────────────────────────

    @staticmethod
    def _is_retryable(result: AgentResult) -> bool:
        """Return True if the failure is a known transient/not-ready error."""
        output_lower = result.output.lower()
        for pattern in _TRANSIENT_ERROR_PATTERNS:
            if pattern in output_lower:
                return True
        for pattern in _NOT_READY_PATTERNS:
            if pattern in output_lower:
                return True
        if result.exit_code == -1 and "timed out" in output_lower:
            return True
        return False

    # ── core streaming implementation ─────────────────────────────

    def _run_stream_json(
        self,
        cmd: list[str],
        cwd: Path,
        timeout: int,
        on_output: Callable[[str], None] | None = None,
        stdin_data: str | None = None,
    ) -> AgentResult:
        """Parse stream-json with parallel stdout/stderr and wall-clock timeout.

        Key improvements over the naive approach:
        1. stdout and stderr are consumed in separate threads (no pipe deadlock)
        2. A wall-clock deadline aborts the *entire* run, not just proc.wait()
        3. Idle detection: if stdout goes silent for _IDLE_TIMEOUT, treat as hung
        4. Process-group kill ensures clean teardown of child trees
        """
        start = time.monotonic()
        deadline = start + timeout

        final_result = ""
        stream_is_error: bool | None = None  # from stream-json "result" event
        event_log: list[str] = []
        stderr_chunks: list[str] = []

        got_first_visible = threading.Event()  # set on first user-visible output
        got_any_event = threading.Event()       # set on any stdout line (for idle detection)
        heartbeat_stop = threading.Event()
        last_activity = time.monotonic()
        activity_lock = threading.Lock()
        thinking = _ThinkingTracker()

        log.debug("spawn: %s (cwd=%s, timeout=%ds, stdin=%d bytes)",
                  cmd, cwd, timeout, len(stdin_data) if stdin_data else 0)

        proc = proc_mgr.spawn_cursor(cmd, str(cwd), stdin_data=stdin_data)

        def _emit(text: str) -> None:
            if on_output:
                on_output(text + "\n")
            else:
                sys.stderr.write(f"{_STREAM_PREFIX}{text}\n")
                sys.stderr.flush()

        def _touch_activity() -> None:
            nonlocal last_activity
            with activity_lock:
                last_activity = time.monotonic()

        # ── heartbeat thread ──────────────────────────────────────
        def _heartbeat() -> None:
            """Keep printing until a visible event arrives (not just system/init)."""
            while not heartbeat_stop.is_set():
                heartbeat_stop.wait(_HEARTBEAT_INTERVAL)
                if heartbeat_stop.is_set():
                    break
                if not got_first_visible.is_set():
                    elapsed = time.monotonic() - start
                    _emit(t("driver.heartbeat", elapsed=elapsed))

        heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
        heartbeat_thread.start()

        # ── stdout consumer thread ────────────────────────────────
        def _consume_stdout() -> None:
            nonlocal final_result, stream_is_error
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                _touch_activity()
                if not got_any_event.is_set():
                    got_any_event.set()

                try:
                    evt = json.loads(raw_line)
                except json.JSONDecodeError:
                    _emit(raw_line)
                    event_log.append(raw_line)
                    got_first_visible.set()
                    continue

                msg = _format_event(evt, thinking)
                if msg:
                    _emit(msg)
                    event_log.append(msg)
                    got_first_visible.set()

                if evt.get("type") == "result":
                    final_result = evt.get("result", "")
                    stream_is_error = bool(evt.get("is_error"))
                    if stream_is_error:
                        final_result = f"ERROR: {final_result}"

        # ── stderr consumer thread ────────────────────────────────
        def _consume_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_chunks.append(line)
                _touch_activity()

        stdout_thread = threading.Thread(target=_consume_stdout, daemon=True)
        stderr_thread = threading.Thread(target=_consume_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        # ── wait with wall-clock timeout + idle detection ─────────
        timed_out = False
        idle_hung = False
        try:
            while stdout_thread.is_alive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break

                with activity_lock:
                    idle_secs = time.monotonic() - last_activity

                if got_any_event.is_set() and idle_secs > _IDLE_TIMEOUT:
                    idle_hung = True
                    break

                stdout_thread.join(timeout=min(remaining, 2.0))

            if timed_out or idle_hung:
                reason = "wall-clock timeout" if timed_out else f"idle {_IDLE_TIMEOUT}s"
                log.warning("killing cursor process (pid=%s): %s", proc.pid, reason)
                proc_mgr.kill_process_tree(proc)
                proc.wait(timeout=5)
                proc_mgr.unregister(proc)
                return AgentResult(
                    success=False,
                    output=t("driver.cursor_timeout"),
                    exit_code=-1,
                )

            # stdout done — wait for stderr + process exit
            stderr_thread.join(timeout=10)
            proc.wait(timeout=30)
        except Exception:
            proc_mgr.kill_process_tree(proc)
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            raise
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
            proc_mgr.unregister(proc)

        if not on_output:
            elapsed = time.monotonic() - start
            sys.stderr.write(f"{_STREAM_PREFIX}{t('driver.done', elapsed=elapsed)}\n")
            sys.stderr.flush()

        stderr_text = "".join(stderr_chunks)

        # ── determine success ─────────────────────────────────────
        # Combine returncode with stream-json is_error for reliable detection.
        # If they disagree, use the stricter (failure) interpretation.
        rc_ok = proc.returncode == 0
        stream_ok = stream_is_error is not True  # None (no result event) treated as ok

        if rc_ok != stream_ok:
            log.warning(
                "success mismatch: returncode=%s stream_is_error=%s — treating as failure",
                proc.returncode, stream_is_error,
            )

        is_error = not rc_ok or not stream_ok
        full_output = _compose_full_output(event_log, final_result)

        if is_error and stderr_text:
            full_output += f"\n\n== STDERR ==\n{stderr_text.strip()}"

        return AgentResult(
            success=not is_error,
            output=full_output,
            exit_code=proc.returncode or 0,
        )

    # ── prompt composition ────────────────────────────────────────

    def _compose_prompt(self, agent_name: str, prompt: str, *, readonly: bool) -> str:
        developer_instructions = self._load_developer_instructions(agent_name)
        readonly_block = t("driver.readonly_block") if readonly else ""
        if not developer_instructions:
            return prompt + readonly_block

        return t(
            "driver.system_context",
            instructions=developer_instructions.strip(),
            prompt=prompt.strip(),
            readonly_block=readonly_block,
        )

    def _load_developer_instructions(self, agent_name: str) -> str:
        role_file = _ROLE_FILES.get(agent_name)
        if not role_file:
            return ""

        agents_dir = Path(__file__).resolve().parents[3] / "agents" / "cursor"
        lang = get_lang()

        if lang != "en":
            lang_path = agents_dir / lang / role_file
            if lang_path.exists():
                try:
                    return lang_path.read_text(encoding="utf-8").strip()
                except OSError:
                    pass

        path = agents_dir / role_file
        if not path.exists():
            return ""

        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
