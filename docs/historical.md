# Historical Documentation

> This file archives documentation from versions prior to v4.0.0 (when the project was published as `harness-orchestrator`; now `harness-flow`).
> These features have been **removed** — the project now operates exclusively in cursor-native mode.

---

## Orchestrator Mode (removed in v4.0.0)

Prior to v4.0.0, harness-orchestrator supported an "orchestrator mode" that drove external
IDE CLIs (`cursor agent`, `codex exec`) as subprocesses. This was removed because the
cursor-native approach (generating skills/agents/rules that run inside Cursor) provided
a better experience with far less complexity.

**Removed CLI commands:** `harness run`, `harness auto`, `harness stop`, `harness vision`

**Removed modules:** `harness.orchestrator`, `harness.drivers`, `harness.methodology`,
`harness.agents` (packaged agent definitions)

---

## State Machine (removed in v4.0.0)

The orchestrator used an explicit state machine for the task lifecycle with states:
`idle → planning → contracted → building → evaluating → done/blocked`.

Transition enforcement (`ValueError` on invalid transitions) lived in `state.py`.
In cursor-native mode, task state is managed through `.agents/tasks/` plan files
and evaluation artifacts — no programmatic state machine.

---

## Driver Compatibility (removed in v4.0.0)

Harness previously probed Cursor CLI and Codex CLI at startup:

- **Cursor CLI**: Required `cursor agent --print --output-format stream-json`
- **Codex CLI**: Required `codex exec --full-auto --output-last-message`

Version detection ran `--version` and `--help` to verify flag compatibility.
In cursor-native mode, no external CLI is invoked — Cursor IDE executes skills directly.

**Python environment requirements remain unchanged:**

| Dependency | Minimum |
|------------|---------|
| Python | >= 3.9 |
| typer | >= 0.12 |
| pydantic | >= 2.0 |
| jinja2 | >= 3.1 |
| rich | >= 13.0 |

---

## Original Project Vision (pre-v4)

The original vision described a "unified abstraction across agent backends" where Cursor
and Codex could be used interchangeably via drivers. This has been simplified to
Cursor-native only. The current vision is maintained in `.agents/vision.md`.

Key changes from the original vision:
- "Unified abstraction across backends" → IDE-first (Cursor only)
- "Strategist / Reflector roles" → Removed (5-role native review system)
- "Driver layer / methodology layer" → Removed (template-driven generation)
