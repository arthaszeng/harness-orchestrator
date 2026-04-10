# Architecture (v4.0.0 — native-only)

This document explains **why** harness-flow is structured the way it is after the native-only refactor. Execution lives in **Cursor**: the Python package bootstraps configuration, generates IDE artifacts, and maintains local state—not an external orchestration loop.

For module-level behavior, read the code and docstrings. For day-to-day usage, see `README.md`.

## System overview

```
┌─────────────────────────────────────────────────────────────────┐
│  harness CLI (Typer)                                             │
│  init · status · update                                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   .harness-flow/*            core/*              native/skill_gen
   config, vision,      config, state,      Jinja2 → .cursor/
   state, progress      scanner, ui, …      skills, agents, rules
                             │
                             ▼
                    integrations/
                    git_ops, memverse
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Cursor IDE — skills, subagents, rules execute the workflow      │
└─────────────────────────────────────────────────────────────────┘
```

**Principle:** Cursor is the execution engine. Harness generates and refreshes the artifacts Cursor runs; there is no separate process supervisor or IDE driver layer in this package.

---

## CLI layer (`src/harness/cli.py`)

Built with **Typer**. Core commands:


| Command              | Purpose                                                                                  |
| -------------------- | ---------------------------------------------------------------------------------------- |
| `init`               | Project bootstrap wizard; when config already exists, reinit mode regenerates artifacts. |
| `gate`               | Check ship-readiness gates for the current task (hard + soft checks).                    |
| `status`             | Load workflow state and render a Rich dashboard.                                         |
| `git-preflight`      | Structured git preflight checks with deterministic result codes.                         |
| `git-prepare-branch` | Create/resume task branch on top of configured trunk.                                    |
| `git-sync-trunk`     | Sync the current feature branch against configured trunk.                                |
| `git-post-ship`      | Post-ship lifecycle automation: PR merge check, trunk sync, local branch cleanup.        |
| `update`             | Check PyPI, optional pip upgrade, config migration hints; no project artifact writes.    |


---

## Commands (`src/harness/commands/`)

### `init.py`

Two modes:

- **Wizard mode** (no `.harness-flow/config.toml`): interactive setup (language → project info → trunk → CI → Memverse → evaluator model), writes config, generates artifacts.
- **Reinit mode** (`.harness-flow/config.toml` exists): loads existing config, regenerates all `.cursor/` artifacts with `force=True`.

**Writes:** `.harness-flow/config.toml` (from `templates/config.toml.j2`), `.harness-flow/vision.md` when appropriate, then calls `generate_native_artifacts()` so `.cursor/` is populated. Updates `.gitignore` for harness-local files.

### `status.py`

Loads task-level `**workflow-state.json`** under `.harness-flow/tasks/task-NNN/` and
renders canonical phase / gate / blocker information via **Rich** (`core/ui.py` patterns).

### `calibrate_cmd.py`

`harness calibrate` — cross-task review calibration report. Scans all task
directories for `review-outcome.json`, generates aggregated statistics
(Rich terminal or `--json`), and supports single-task view via `--task`.

### `trust_cmd.py`

`harness trust` — display progressive trust profile. Collects review outcomes,
generates `CalibrationReport`, computes `TrustProfile` via `trust_engine.py`.
Supports Rich terminal and `--json` output. Exit 0 always (including no-data case).

### `update.py`

Queries PyPI for newer versions, runs `**pip install --upgrade harness-flow`** when requested, and runs lightweight **config migration** checks with user-visible warnings. It does **not** write project artifacts; users should run `**harness init --force`** in the target repository when regeneration is needed.

---

## Core (`src/harness/core/`)

### `config.py`

**Pydantic** models: `ProjectConfig`, `CIConfig`, `ModelsConfig`, `NativeModeConfig`, `WorkflowConfig`, `HarnessConfig`, plus nested integration config (e.g. Memverse).

- `**HarnessConfig` uses `ConfigDict(extra="ignore")`** so older TOML keys do not break loading.
- `**HarnessConfig.load()**` builds the effective config by deep-merging, then validates:
  - Start from **project** `.harness-flow/config.toml` (if present).
  - Merge `**~/.harness/config.toml`** under it so **project wins** on conflicts.
  - Merge `**HARNESS_*` environment variables** on top (highest precedence).
  - Missing keys fall back to **model defaults**.

`ModelsConfig` carries `default`, `role_overrides`, and `role_configs`; unknown keys under `[models]` are ignored. Native workflows primarily use `native.*` and project/CI/workflow fields.

### `roles.py`

Minimal constants only:

- `**ALL_ROLES`** — empty `frozenset` (no routed roles in native-only mode).
- `**NATIVE_REVIEW_ROLES**` — the five native review roles: `architect`, `product_owner`, `engineer`, `qa`, `project_manager`.
- `**SCORING_DIMENSIONS**` — evaluation dimension labels (used by tests for validation).
- `**DEFAULT_RUNTIME**` — default runtime label (`"cursor"`) for registry/events/tracker.

### `state.py`

`**TaskState**` enumeration for workflow phases (idle, planning, contracted, building, evaluating, shipping, done, blocked).

### `workflow_state.py`

Task-level canonical workflow state stored at
`.harness-flow/tasks/task-NNN/workflow-state.json`. It tracks phase, active plan,
artifact refs, gate snapshots, blocker reason, and deterministic task discovery.
`resolve_task_dir` resolves the active task with priority:
`explicit_task_id` → `HARNESS_TASK_ID` env → `session_task_id` → latest numeric.
Registry/events remain audit-only metadata, not gate authorities.

### `task_identity.py`

Task key resolution for workflow and branch lifecycle. Supports configurable
strategies (`numeric`, `jira`, `custom`, `hybrid`) so task identifiers are not
hard-wired to `task-NNN`. Provides validation and branch extraction helpers,
with backward compatibility for `task-NNN`. Also provides convenience functions
`extract_task_key_from_branch(branch, cwd)` and `extract_task_id_from_branch(branch)`
for extracting task keys from `agent/<task-key>-*` branch names.

### `branch_lifecycle.py`

Structured git lifecycle orchestration used by workflow entry points:
preflight checks, trunk sync, task-branch prepare/resume, and feature rebase.
Returns structured result codes/messages for deterministic agent handling.

### `post_ship.py`

Post-ship lifecycle orchestration. Handles PR state lookup via `gh`,
merged-only safety checks, trunk update, and local task-branch cleanup with guardrails
(never delete trunk/current branch).

### `handoff.py`

Structured stage handoff contract. Each pipeline stage (plan → build → eval → ship)
writes a compact JSON summary at its exit point via `save_handoff()`. The next stage
reads that handoff via `load_handoff()` or `load_latest_handoff()` instead of
re-processing full upstream artifacts. Handoff files live at
`.harness-flow/tasks/task-NNN/handoff-<phase>.json` with `PHASE_ORDER = (plan, build, eval, ship)`.
Schema uses Pydantic with `extra="ignore"` and versioning for forward compatibility.

### `gates.py`

Ship-readiness gate validation. `check_ship_readiness(task_dir)` runs hard checks
(plan exists, eval exists, eval verdict parseable, eval ship-eligible) and soft
checks (build exists, eval freshness, workflow-state gate populated). Returns a
structured `GateVerdict` with per-item results. `write_gate_snapshot` persists the
verdict to `workflow-state.json` via load-merge-save. Used by `harness gate` CLI.

**Adaptive Ship Gate (template-level):** The ship skill template includes
`_ship-review-gate.md.j2` which computes an escalation score from code-change
signals (diff size, file count, risk directories, commit types) and selects one
of three review intensities:


| Level | Trigger                                                     | Behavior                                         |
| ----- | ----------------------------------------------------------- | ------------------------------------------------ |
| FULL  | score ≥ `gate_full_review_min` (default 5)                  | 5-role parallel code review                      |
| LITE  | score in `[gate_summary_confirm_min, gate_full_review_min)` | Engineer + QA only                               |
| FAST  | score < `gate_summary_confirm_min` (default 3)              | Skip multi-role review; CI + `harness gate` only |


This is a **soft gate** (computed by the agent per template instructions). The
Python-level `gates.py` machine gate remains unchanged and always runs.

### `failure_patterns.py`

Structured failure pattern library for cross-task failure tracking. Each task
records its own failure patterns in `failure-patterns.jsonl` (JSONL append mode,
same as `intervention_audit.py`). `save_failure_pattern()` appends one pattern
with auto-generated signature via `normalize_finding_signature()` and syncs
`workflow-state.json` artifact refs. `load_failure_patterns()` loads patterns
from a single task directory (skipping corrupt lines). `search_failure_patterns()`
aggregates across all task and archive directories via `iter_task_dirs` /
`iter_archive_dirs`, supporting normalized substring query and category filtering.

### `review_calibration.py`

Review calibration: prediction-vs-outcome tracking and cross-task aggregation.

**Layer 1 — Data model:** `ReviewOutcome` persists per-task prediction snapshots
(eval aggregate, dimension scores, verdict, finding count) alongside actual
outcomes (CI pass/fail, revert detection) in `review-outcome.json`.

**Layer 2 — Aggregation:** `generate_calibration_report()` collects outcomes
from all task/archive directories and computes prediction accuracy
(verdict vs CI result alignment), dimension biases (per-dimension delta from
aggregate), and score-outcome correlation (point-biserial). Requires ≥5
paired samples for full statistics; degrades gracefully with fewer.

**Integration points:**

- `artifacts.save_evaluation(kind="code")` writes prediction sidecar
automatically (both structured and `raw_body` paths)
- `post_ship.PostShipManager.record_outcome()` collects actual outcomes
(best-effort, failure-isolated from core cleanup path)
- `harness calibrate` CLI exposes Rich and JSON reports

The calibration pipeline reads only `review-outcome.json` files and does
**not** consume `events.jsonl` to avoid dual truth-source conflicts with
the session-level event stream.

### `trust_engine.py`

Progressive trust engine — computes trust level from historical calibration data.

**Pure-function module:** no I/O, no side effects. Inputs (`CalibrationReport`,
`list[ReviewOutcome]`, `TrustConfig`) provided by caller (CLI or gate command).

**Trust levels** (discrete, ordered most-to-least trusted):

- `HIGH` — prediction accuracy ≥ 85%, ≥ 10 paired samples, no recent reverts → escalation -2
- `MEDIUM` — accuracy ≥ 70%, ≥ 5 paired samples, no recent reverts → escalation -1
- `LOW` — insufficient data or accuracy below threshold → escalation +0
- `PROBATION` — revert detected in recent N tasks → escalation +3

**Priority rule:** PROBATION > HIGH > MEDIUM > LOW (revert always overrides
positive accuracy signals).

**Advisory only:** trust level is displayed in `harness gate` and `harness trust`
output but never changes hard gate pass/block semantics. `GateVerdict.trust_level`
is not persisted to `workflow-state.json`.

**Configuration:** `[workflow.trust]` in `config.toml` exposes `accuracy_high`,
`accuracy_medium`, `min_samples_high`, `min_samples_medium`,
`probation_revert_window` — all with sensible defaults.

### `progress.py`

`**suggest_next_action`** and `**update_progress**` helpers for markdown progress narratives (e.g. `.harness-flow/progress.md`) aligned with native workflows.

### `scanner.py`

Scans the repository layout to **suggest CI commands** during `init`.

### `ui.py`

**Rich** helpers for terminal output (tables, panels, styling) used by status and other commands.

### `events.py`

Structured **JSONL** event logging for observability of harness-adjacent activity.

### `registry.py`

**SQLite**-backed registry for agent run metadata (local audit trail).

### `context.py`

**Task execution context** shared by code paths that still need a unified “where is the task root / config” view.

---

## Native mode generator (`src/harness/native/`)

### `skill_gen.py`

- Loads **Jinja2** templates from `src/harness/templates/native/`.
- Builds a **layered template context** via `_build_layered_context()` from `HarnessConfig`.
Context is organized into three layers:
  - **Layer 0 (Base)** — project-wide scalars (CI command, trunk branch, project lang, memverse config, etc.)
  - **Layer 1 (Role)** — principles (planner/builder), per-role model hints, evaluator model
  - **Layer 2 (Stage)** — pipeline gates, hooks, thresholds
  Each artifact receives only the layers it needs; e.g. agents get Layer 0+1 (no stage hooks),
  most rules get Layer 0+2 (no role principles), while `harness-trust-boundary` gets all three
  layers because it references evaluator model info. Mapping is defined in `_ARTIFACT_LAYERS`.
- **Selective rule activation**: `NativeModeConfig.rule_activation` controls per-rule generation:
`"always"` (default), `"phase_match"` (adds marker comment), `"disabled"` (skips file).
- `**generate_native_artifacts()`** writes:
  - **9 skills** under `.cursor/skills/harness/<skill-name>/SKILL.md`
  - **5 agents** under `.cursor/agents/*.md` (with `<!-- context: layers ... -->` metadata)
  - **Up to 4 rules** under `.cursor/rules/*.mdc` (count depends on `rule_activation`)
  - **Eval resources** (checklist and specialist docs) under `.cursor/skills/harness/harness-eval/`

Skills/agents/rules are regenerated according to `init --force` behavior.

`**harness worktree-setup`** — CLI command that creates symlinks in linked git worktrees, pointing `.harness-flow`, `.cursor/skills/harness`, `.cursor/agents`, and `.cursor/rules` back to the main working tree. Preflight templates guide agents to run this command automatically when `.harness-flow` is missing.

---

## Templates (`src/harness/templates/`)

- `**config.toml.j2**` — project config emitted by `init`.
- `**native/**` — Jinja2 sources for skills, agents, rules, and shared **sections** (e.g. plan/review gates, trust boundary, CI verification).
- `**vision.md.j2` / `vision.zh.md.j2`** — initial vision stubs.

All user-visible harness **behavior** in the IDE is intended to flow from these templates plus `HarnessConfig`, so upgrades can refresh prompts without forking business logic across Python files.

---

## Integrations (`src/harness/integrations/`)

- `**git_ops.py`** — git helpers (rebase, merge, cleanup) plus structured command results (`GitOperationResult`) for deterministic error handling.
- `**memverse.py**` — Memverse integration anchor. Actual search/add runs via Cursor MCP tools in the IDE; Python only provides the `integrations.memverse` config which is projected into templates as `memverse_enabled` and `memverse_domain` (Layer 0).

---

## Design principles

1. **Cursor IDE is the execution engine** — Harness generates **skills, agents, and rules** that Cursor’s agent runtime executes. No in-package external CLI orchestration of other IDEs.
2. **Five-role adversarial review** — The five native roles review **plans and code** in parallel; templates encode how dispatch and aggregation behave.
3. **Fix-First auto-remediation** — Review output is classified into **AUTO-FIX** vs **ASK** before presentation (encoded in generated rules/skills, not in a Python state machine).
4. **Config cascade** — **Project** and **global** TOML merge with **project overriding global**; `**HARNESS_*` env vars** override both; Pydantic validates the result.
5. **Backward compatibility** — `**extra="ignore"`** on `HarnessConfig` allows stale keys from older installs to load safely.
6. **Template-driven generation** — Native artifacts are rendered from **Jinja2**; Python supplies context and file placement only.
7. **Local-first** — State, config, registry, and logs are **on disk**; PyPI is only needed for **package updates**, not for routine development.

---

## Artifact layout (high level)

**Project (`.harness-flow/`)**

- `config.toml` — harness configuration.
- `vision.md` — product/engineering vision for skills.
- `tasks/`, `archive/` — task artifacts and history (convention from harness workflow docs).
- `tasks/task-NNN/workflow-state.json` — canonical task-level phase/gate/blocker/artifact state.
- `tasks/task-NNN/review-outcome.json` — prediction-vs-outcome calibration data (auto-populated by `save_evaluation` and `post_ship`).

**Generated IDE (`.cursor/`)**

- `skills/harness/`** — generated skills and eval resources.
- `agents/*.md` — five review agents plus any future template outputs.
- `rules/*.mdc` — always-on rules (workflow, trust boundary, Fix-First, safety).
- ~~`worktrees.json`~~ — Removed. Worktree symlink setup is now handled by `harness worktree-setup` CLI command.

---

## Internationalization

Module-level catalogs (`i18n/en.py`, `i18n/zh.py`) expose `t(key, **kwargs)`. Missing keys fall back to English. CLI and generator user-facing strings go through this layer when applicable.

---

## Testing orientation

Tests are organized around **fast, local behavior**: configuration loading (including env overrides), state/progress, scanner suggestions, skill generation output, init/update flows, git helpers, registry, and UI pieces—without requiring a live Cursor session. Template and config drift is caught by tests that assert on generated files or loaded models.

---

## Design decisions (native era)

### Why generate `.cursor/` instead of shipping static files?

Project-specific **CI command**, **trunk branch**, **review gates**, and **hooks** must flow into prompts. Templating from `HarnessConfig` keeps one SSOT and allows `harness init --force` to refresh IDE assets after config edits.

### Why keep `ALL_ROLES` empty?

Older configs and code paths referenced a unified role set for model validation. An empty `ALL_ROLES` preserves **compatibility** while native mode keys off `**NATIVE_REVIEW_ROLES`** only.

### Why SQLite for the registry?

A **local, queryable** history of runs supports debugging and audit without a hosted service—consistent with the local-first stance.