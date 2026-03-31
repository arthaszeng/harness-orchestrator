"""Autonomous loop — multi-task development driven by Strategist."""

from __future__ import annotations

import re
import time

from harness import __version__
from harness.core.config import HarnessConfig
from harness.core.events import EventEmitter, NullEventEmitter
from harness.core.state import StateMachine
from harness.core.ui import get_ui
from harness.drivers.resolver import DriverResolver
from harness.i18n import t
from harness.integrations.memverse import create_memverse
from harness.orchestrator.safety import check_safety
from harness.orchestrator.workflow import WorkflowResult, run_single_task


def run_autonomous(
    config: HarnessConfig,
    sm: StateMachine,
    resolver: DriverResolver,
    *,
    resume: bool = False,
) -> list[WorkflowResult]:
    """Autonomous loop: Strategist proposes tasks → execute → Reflector summarizes."""
    ui = get_ui()
    results: list[WorkflowResult] = []
    consecutive_blocked = 0
    completed_count = len(sm.state.completed)

    memverse = create_memverse(config.integrations.memverse.enabled)

    session_id = sm.state.session_id or "unknown"
    ev: EventEmitter | NullEventEmitter
    try:
        ev = EventEmitter(sm.agents_dir, session_id)
    except OSError:
        ev = NullEventEmitter()

    ui.banner("auto", __version__)
    ui.system_status(resolver.available_drivers)

    while True:
        safety = check_safety(sm, config.autonomous, completed_count, consecutive_blocked)
        if safety.should_stop:
            ui.safety_stop(safety.reason)
            break

        # Strategist: pick the next task
        t0 = time.monotonic()
        with ui.agent_step("[strategist] scanning project state", "codex") as on_out:
            task_requirement = _invoke_strategist(config, sm, resolver, on_output=on_out)
        elapsed = time.monotonic() - t0

        if not task_requirement:
            ui.strategist_done(elapsed)
            break

        ui.strategist_result(task_requirement, elapsed)

        # Run single-task workflow
        result = run_single_task(config, sm, resolver, task_requirement, events=ev)
        results.append(result)

        if result.verdict == "PASS":
            completed_count += 1
            consecutive_blocked = 0
        else:
            consecutive_blocked += 1

        # Reflector: periodic summary
        if completed_count > 0 and completed_count % config.autonomous.progress_report_interval == 0:
            t0 = time.monotonic()
            with ui.agent_step("[reflector] generating summary", "codex") as on_out:
                _invoke_reflector(config, sm, resolver, memverse, on_output=on_out)
            elapsed = time.monotonic() - t0
            ui.step_done("[reflector]", elapsed, True, "synced")

    # Final session summary
    if results:
        passed = [r for r in results if r.verdict == "PASS"]
        avg = sum(r.score for r in passed) / len(passed) if passed else 0.0
        ui.session_end(completed_count, consecutive_blocked, avg)

    return results


def _invoke_strategist(
    config: HarnessConfig,
    sm: StateMachine,
    resolver: DriverResolver,
    *,
    on_output=None,
) -> str | None:
    """Invoke Strategist agent; return the next task description or None."""
    driver = resolver.resolve("strategist")
    agent_name = resolver.agent_name("strategist")

    vision = ""
    vision_path = sm.agents_dir / "vision.md"
    if vision_path.exists():
        vision = vision_path.read_text(encoding="utf-8")[:3000]

    progress = ""
    progress_path = sm.agents_dir / "progress.md"
    if progress_path.exists():
        progress = progress_path.read_text(encoding="utf-8")[:3000]

    prompt = t(
        "prompt.strategist",
        vision=vision,
        progress=progress,
        completed=len(sm.state.completed),
        blocked=[task.requirement for task in sm.state.blocked],
    )

    result = driver.invoke(
        agent_name, prompt, config.project_root,
        readonly=True, on_output=on_output,
    )

    if not result.success:
        return None

    output = result.output.strip()

    if "VISION_COMPLETE" in output:
        return None

    requirement = _extract_requirement(output)
    return requirement


def _extract_requirement(output: str) -> str | None:
    """Extract the requirement line or section from Strategist output."""
    pattern = t("prompt.requirement_regex")
    m = re.search(pattern + r"\n+(.+?)(?=\n##|\Z)", output, re.DOTALL)
    if m:
        return m.group(1).strip().split("\n")[0].strip()

    for line in output.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and len(line) > 5:
            return line[:200]

    return None


def _invoke_reflector(
    config: HarnessConfig,
    sm: StateMachine,
    resolver: DriverResolver,
    memverse: object,
    *,
    on_output=None,
) -> None:
    """Invoke Reflector to summarize progress and detect vision drift."""
    ui = get_ui()
    driver = resolver.resolve("reflector")
    agent_name = resolver.agent_name("reflector")

    vision = ""
    vision_path = sm.agents_dir / "vision.md"
    if vision_path.exists():
        vision = vision_path.read_text(encoding="utf-8")[:3000]

    progress = ""
    progress_path = sm.agents_dir / "progress.md"
    if progress_path.exists():
        progress = progress_path.read_text(encoding="utf-8")[:5000]

    prompt = t(
        "prompt.reflector",
        vision=vision,
        progress=progress,
        completed=sm.state.stats.completed,
        blocked=sm.state.stats.blocked,
        avg_score=sm.state.stats.avg_score,
        total_iterations=sm.state.stats.total_iterations,
    )

    result = driver.invoke(
        agent_name, prompt, config.project_root,
        readonly=True, on_output=on_output,
    )

    if result.success:
        reflection_path = sm.agents_dir / "reflection.md"
        reflection_path.write_text(result.output, encoding="utf-8")

        drift = detect_vision_drift(result.output)
        if drift:
            ui.warn(f"[reflector] {drift}")
            ui.warn("[reflector] consider running `harness vision`")

    # progress.md is now auto-refreshed by StateMachine._checkpoint()


def detect_vision_drift(reflector_output: str) -> str | None:
    """Detect VISION_DRIFT / VISION_STALE markers in Reflector output."""
    for line in reflector_output.split("\n"):
        line = line.strip()
        if line.startswith("VISION_DRIFT:"):
            return line
        if line.startswith("VISION_STALE:"):
            return line
    return None
