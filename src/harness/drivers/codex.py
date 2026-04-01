"""Codex CLI subprocess driver."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
import time

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from harness.drivers.base import AgentResult
from harness.i18n import get_lang, t

_ROLE_FILES = {
    "harness-planner": "planner.toml",
    "harness-evaluator": "evaluator.toml",
    "harness-alignment-evaluator": "alignment_evaluator.toml",
    "harness-strategist": "strategist.toml",
    "harness-reflector": "reflector.toml",
    "harness-advisor": "advisor.toml",
}

_STREAM_PREFIX = "    │ "
_HEARTBEAT_INTERVAL = 15
_PROBE_TIMEOUT = 8


@dataclass
class DriverProbe:
    available: bool
    version: str = ""
    warnings: list[str] = field(default_factory=list)


class CodexDriver:
    """Invoke agents via Codex CLI.

    Codex CLI no longer exposes `codex exec --agent`, so this driver parses
    role definitions and concatenates developer instructions into the prompt.
    """

    def __init__(self) -> None:
        self._probe_result: DriverProbe | None = None

    @property
    def name(self) -> str:
        return "codex"

    def is_available(self) -> bool:
        return shutil.which("codex") is not None

    def probe(self) -> DriverProbe:
        """Detect CLI version and validate that ``codex exec`` is functional."""
        if self._probe_result is not None:
            return self._probe_result

        if not self.is_available():
            self._probe_result = DriverProbe(available=False)
            return self._probe_result

        warnings: list[str] = []
        version = ""
        try:
            result = subprocess.run(
                ["codex", "--version"],
                capture_output=True, text=True, timeout=_PROBE_TIMEOUT,
            )
            version = result.stdout.strip() or result.stderr.strip()
        except Exception:
            warnings.append("could not detect codex version")

        functional = True
        try:
            help_result = subprocess.run(
                ["codex", "exec", "--help"],
                capture_output=True, text=True, timeout=_PROBE_TIMEOUT,
            )
            help_text = help_result.stdout + help_result.stderr
            if help_result.returncode != 0:
                functional = False
                warnings.append(t("driver.codex_not_ready"))
            else:
                for flag in ("--full-auto", "--output-last-message"):
                    if flag not in help_text:
                        warnings.append(f"codex exec may not support {flag}")
        except subprocess.TimeoutExpired:
            functional = False
            warnings.append(t("driver.codex_not_ready"))
        except Exception:
            functional = False
            warnings.append(t("driver.codex_not_ready"))

        self._probe_result = DriverProbe(
            available=functional, version=version, warnings=warnings,
        )
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
        model: str = "",
    ) -> AgentResult:
        full_prompt = self._compose_prompt(agent_name, prompt, readonly=readonly)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            output_file = f.name

        cmd = [
            "codex",
            "exec",
            "--full-auto",
            "--color",
            "never",
            "--output-last-message",
            output_file,
            "-C",
            str(cwd),
        ]

        if model:
            cmd.extend(["--model", model])

        cmd.append("-")

        try:
            return self._run_streaming(cmd, full_prompt, output_file, cwd, timeout, on_output)
        except FileNotFoundError:
            return AgentResult(success=False, output=t("driver.codex_not_found"), exit_code=-1)
        finally:
            Path(output_file).unlink(missing_ok=True)

    def _run_streaming(
        self,
        cmd: list[str],
        input_text: str,
        output_file: str,
        cwd: Path,
        timeout: int,
        on_output: Callable[[str], None] | None = None,
    ) -> AgentResult:
        """Run subprocess with streaming; forward lines via on_output or stderr."""
        start = time.monotonic()
        lines: list[str] = []

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(cwd),
        )

        if proc.stdin:
            proc.stdin.write(input_text)
            proc.stdin.close()

        last_output_time = time.monotonic()
        heartbeat_stop = threading.Event()

        # No heartbeat when on_output is set (UI already shows progress)
        if not on_output:
            def _heartbeat() -> None:
                while not heartbeat_stop.is_set():
                    heartbeat_stop.wait(_HEARTBEAT_INTERVAL)
                    if heartbeat_stop.is_set():
                        break
                    elapsed = time.monotonic() - start
                    idle = time.monotonic() - last_output_time
                    if idle >= _HEARTBEAT_INTERVAL:
                        sys.stderr.write(
                            f"{_STREAM_PREFIX}{t('driver.heartbeat', elapsed=elapsed)}\n"
                        )
                        sys.stderr.flush()

            heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
            heartbeat_thread.start()

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                last_output_time = time.monotonic()
                lines.append(line)
                if on_output:
                    on_output(line)
                else:
                    sys.stderr.write(f"{_STREAM_PREFIX}{line}")
                    sys.stderr.flush()

            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return AgentResult(success=False, output=t("driver.codex_timeout"), exit_code=-1)
        finally:
            heartbeat_stop.set()
            if not on_output:
                heartbeat_thread.join(timeout=2)

        if not on_output:
            elapsed = time.monotonic() - start
            sys.stderr.write(f"{_STREAM_PREFIX}{t('driver.done', elapsed=elapsed)}\n")
            sys.stderr.flush()

        final_output = ""
        try:
            final_output = Path(output_file).read_text(encoding="utf-8").strip()
        except OSError:
            pass

        combined_output = final_output or "".join(lines)
        return AgentResult(
            success=proc.returncode == 0,
            output=combined_output,
            exit_code=proc.returncode or 0,
        )

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

        agents_dir = Path(__file__).resolve().parent.parent / "agents" / "codex"
        lang = get_lang()

        if lang != "en":
            lang_path = agents_dir / lang / role_file
            if lang_path.exists():
                try:
                    data = tomllib.loads(lang_path.read_text(encoding="utf-8"))
                    instructions = data.get("developer_instructions", "")
                    if instructions and isinstance(instructions, str):
                        return instructions.strip()
                except (tomllib.TOMLDecodeError, OSError):
                    pass

        path = agents_dir / role_file
        if not path.exists():
            return ""

        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            return ""

        instructions = data.get("developer_instructions", "")
        return instructions.strip() if isinstance(instructions, str) else ""
