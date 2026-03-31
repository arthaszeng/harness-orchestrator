[中文](README.zh-CN.md)

# harness-orchestrator

> Contract-driven multi-agent autonomous development orchestration framework for Cursor and Codex — with a Cursor-native mode that runs entirely inside your IDE.

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Today's AI coding tools excel at single-shot tasks, but continuous development often suffers from goal drift, broken context, missing quality gates, and opaque processes. harness-orchestrator organizes multiple agent capabilities into a contract-driven, auditable, recoverable engineering loop:

- **Requirements move with a method** — Planner analyzes requirements to produce a spec and negotiate iterative contracts, instead of jumping straight to code
- **Implementation and review are separate** — Builder implements against the contract; Evaluator reviews independently with four-dimensional scoring as a quality gate
- **Three-pass adversarial review** — In Cursor-native mode, Claude structured review + Claude adversarial subagent + cross-model GPT reviewer, with high-confidence synthesis across passes
- **Fix-First auto-remediation** — Review findings are classified as AUTO-FIX (applied immediately) or ASK (presented for human judgment), keeping the feedback loop tight
- **Autonomous but bounded** — Strategist picks tasks from vision, constrained by iteration limits, pass thresholds, and stop signals
- **Full traceability** — Each iteration's spec, contract, and evaluation are saved in Markdown + JSON for audit, automation, and resume after interruption
- **Two modes** — **Orchestrator** (external CLI drives agents) or **Cursor-native** (skills + subagents inside the IDE, no external process)

> **Design idea**: The core architecture is inspired by the GAN adversarial principle — separation and iterative interplay between Builder (generator) and Evaluator (discriminator) drives code quality to converge; Planner establishes a shared baseline for both sides through the contract protocol.

## Quick start

### Prerequisites

| Dependency | Requirement | Notes |
|------------|-------------|-------|
| **Python** | >= 3.9 | Runs the Harness CLI |
| **Cursor CLI and/or Codex CLI** | At least one | Provides actual agent capability |
| **Git** | Any version | Project must be a Git repo; Harness relies on Git for branches and change tracking |

IDE CLI setup:

- **Cursor**: In Cursor → Command Palette → `Install 'cursor' command`, ensure `cursor` is on your PATH
- **Codex**: Install via npm or from [GitHub](https://github.com/openai/codex), ensure `codex` is on your PATH

> Default routing in `auto` mode is a **replaceable empirical default** (Builder→Cursor, other roles→Codex). That is not Harness's core value — the core assets are the contract protocol, evaluation rubric, state machine, artifact chain, and interrupt recovery. You can configure a driver per role in `.agents/config.toml`. With only one CLI installed, all roles run through that driver.

### Install

```bash
git clone https://github.com/arthaszeng/harness-orchestrator.git
cd harness-orchestrator
./install.sh
```

The install script runs `pip install -e .` and automatically configures PATH if needed. You can also use `python3 -m harness` as a drop-in alternative to the `harness` command.

Verify:

```bash
harness --version
# harness-orchestrator 1.8.2
```

### Five steps to get going

```bash
# 1. Install agent definitions into your local IDE
harness install

# 2. Initialize configuration in your project
cd /path/to/your/project
harness init

# 3. Create project vision
harness vision

# 4. Run work (pick one)
harness run "add user authentication"   # single-task mode
harness auto                            # autonomous mode

# 5. Check progress / stop
harness status
harness stop
```

The sections below expand on each step.

> **Cursor-native mode**: During `harness init`, choose **cursor-native** to skip external CLI orchestration entirely. Harness generates skills, subagents, and rules into `.cursor/`, and you drive the workflow from inside your IDE with `/harness-plan`, `/harness-build`, `/harness-eval`, and `/harness-ship`. See [Cursor-Native Mode](#cursor-native-mode) for details.

---

## Initialization and configuration

### harness install

Installs role definition files into local IDE directories (`~/.cursor/agents/` and/or `~/.codex/agents/`). Harness detects installed IDEs and only installs the matching agent files. Use `--force` to overwrite existing definitions.

### harness init

Starts an interactive wizard in the current project with seven steps:

1. **Project info** — Name and description
2. **IDE environment** — Detect Cursor/Codex and optionally install agent definitions
3. **Driver mode** — Choose auto (recommended: Builder→Cursor, others→Codex), cursor, or codex
4. **Workflow mode** — Choose **orchestrator** (external CLI drives agents) or **cursor-native** (skills + subagents inside Cursor IDE). Only shown when Cursor is detected
5. **CI gate** — Configure commands for quality checks, with optional AI-suggested recommendations
6. **Memverse integration** — Optionally enable long-term memory to persist key decisions during reflection
7. **Vision** — Generate now or edit later

After initialization, `.agents/` is created at the project root with:

| Generated file | Purpose |
|----------------|---------|
| `.agents/config.toml` | Project config: driver mode, CI commands, workflow parameters, etc. |
| `.agents/vision.md` | Project vision (if you chose to generate it in the wizard) |
| `.agents/state.json` | Runtime state (created on first task run; consider adding to `.gitignore`) |

Use `--non-interactive` to skip the wizard and use defaults:

```bash
harness init --name my-project --ci "make test" -y
```

### harness vision

Interactive Q&A with the Advisor agent expands a short description into a structured vision document written to `.agents/vision.md`. Vision is the main input Strategist uses to pick tasks in autonomous mode. You can also edit the file directly.

---

## Core workflow

### Role architecture

| Role | Responsibility | Default backend in `auto` |
|------|----------------|----------------------------|
| **Planner** | Analyze requirements; produce spec and iterative contract | Codex |
| **Builder** | Implement against the contract; commit changes | Cursor |
| **Evaluator** | Independent review; four-dimensional scoring (completeness / quality / regression / design); pass or iterate | Codex |
| **Alignment Evaluator** | Requirement alignment: contract fit, requirement coverage, intent drift detection (requires `dual_evaluation`) | Codex |
| **Strategist** | In autonomous mode, pick the next task from vision and progress | Codex |
| **Reflector** | After a task, distill lessons into long-term memory | Codex/Cursor |

The **Advisor** role supports `harness vision` and AI-assisted analysis during `harness init`.

> Each role's backend can be set independently under `[drivers.roles]`. The table reflects `auto` mode preferences, not hard binding. See [docs/compatibility.md](docs/compatibility.md) for CLI version requirements.

### Single-task flow (`harness run`)

```
User provides requirement
  → Planner: produce spec (analysis, technical approach, impact, risks)
  → Planner: negotiate iterative contract (deliverables, acceptance criteria, complexity)
  → Builder: implement per contract and commit
  → Evaluator: independent review, four-dimensional score
      → Score ≥ threshold (default 3.5) → PASS, task done
      → Score < threshold → feedback to Builder, next iteration
  → Max iterations (default 3) reached without pass → task blocked
```

### Autonomous loop (`harness auto`)

```
Read .agents/vision.md
  → Strategist: pick next task from vision and current progress
  → Run single-task flow (as above)
  → Reflector: distill this round's lessons
  → Loop until:
      - All tasks complete
      - Stop signal (harness stop)
      - Consecutive block limit (default 2)
      - Per-session task limit (default 10)
```

### Choosing `run` vs `auto`

|  | `harness run` | `harness auto` |
|---|---|---|
| **When to use** | Clear requirement; finish one slice | Have vision but want Strategist to plan breakdown |
| **Task source** | From the command line | Strategist from vision and progress |
| **Scope** | One task's plan→build→eval loop | Continuous loop across multiple tasks |
| **Prerequisites** | `init` done | `init` + `vision` done |
| **How it stops** | Task completes or max iterations | Manual `harness stop`, all tasks done, or safety valve |

Both modes support `--resume` (continue from last interruption) and `--verbose` (full agent output).

---

## Cursor-Native Mode

Cursor-native mode runs the entire harness workflow **inside the Cursor IDE** using skills, subagents, and rules — no external CLI process needed. During `harness init`, select **cursor-native** when prompted for workflow mode.

### Orchestrator vs Cursor-native

|  | Orchestrator | Cursor-native |
|---|---|---|
| **How it runs** | External `harness` CLI spawns `cursor-agent` processes | Skills + subagents inside Cursor IDE |
| **Entry point** | `harness run` / `harness auto` | `/harness-plan`, `/harness-build`, `/harness-eval`, `/harness-ship` |
| **Cross-model review** | Configurable per role in `[drivers.roles]` | Adversarial subagent with a different model (e.g. GPT reviews Claude's work) |
| **When to use** | CI/CD pipelines, headless automation, multi-IDE setups | Interactive development, Cursor-only workflows, unlimited Cursor quota |

### Generated artifacts

When you select cursor-native mode, `harness init` generates:

| Artifact | Path | Purpose |
|----------|------|---------|
| `/harness-plan` | `.cursor/skills/harness/harness-plan/SKILL.md` | Plan and decompose a task with adversarial spec review loop |
| `/harness-build` | `.cursor/skills/harness/harness-build/SKILL.md` | Autonomous build: implement contract, run CI, triage test failures, write structured build log |
| `/harness-eval` | `.cursor/skills/harness/harness-eval/SKILL.md` | Three-pass review (Claude + Claude adversarial + cross-model) with Fix-First auto-remediation |
| `/harness-ship` | `.cursor/skills/harness/harness-ship/SKILL.md` | Fully automated pipeline: merge base → test → review → adversarial eval → fix loop → bisectable commits → push → PR |
| Adversarial reviewer | `.cursor/agents/harness-adversarial-reviewer.md` | Cross-model adversarial code reviewer with structured JSON output (`model:` configurable, default `gpt-4.1`; `readonly: true`) |
| Evaluator | `.cursor/agents/harness-evaluator.md` | Structured code evaluator with JSON verdict output (`model: inherit`, `readonly: true`) |
| Trust boundary | `.cursor/rules/harness-trust-boundary.mdc` | Always-on rule: Builder output is untrusted |
| Fix-First | `.cursor/rules/harness-fix-first.mdc` | Always-on rule: classify findings as AUTO-FIX or ASK before presenting |
| Workflow conventions | `.cursor/rules/harness-workflow.mdc` | Commit format, branch naming, task state management |

### Three-pass adversarial review

The `/harness-eval` and `/harness-ship` skills run a three-pass review pipeline with cross-model synthesis:

1. **Pass 1 — Structured review** — Main agent (Claude) scores on four dimensions (completeness, quality, regression, design) and collects findings with structured JSON output
2. **Pass 2 — Claude adversarial subagent** — An independent Claude subagent with fresh context hunts for security holes, race conditions, edge cases, resource leaks, and logic errors
3. **Pass 3 — Cross-model adversarial** — A GPT-based subagent (default: `gpt-4.1`) provides independent perspective from a different model family

**Synthesis**: Findings are deduplicated by fingerprint (`path:line:category`). Issues found by 2+ passes are flagged as **high confidence** with boosted confidence scores.

The adversarial model is configurable in `.agents/config.toml` under `[native] adversarial_model`. Passes 2 and 3 are dispatched in parallel for speed. If any subagent fails, evaluation gracefully degrades — see the degradation matrix below.

### Fix-First auto-remediation

After review, all findings are classified before being presented:

- **AUTO-FIX** — High certainty, small blast radius, reversible. Applied immediately with a verification test run and committed automatically.
- **ASK** — Security findings, behavior changes, architecture changes, or low confidence on critical issues. Presented to the user in a single batch for decision.

This keeps the review → fix feedback loop tight: trivial issues never block shipping, while important decisions always get human judgment.

### Graceful degradation

| Pass 1 (Structured) | Pass 2 (Claude subagent) | Pass 3 (GPT) | Action |
|---------------------|-------------------------|---------------|--------|
| OK | OK | OK | Full three-pass synthesis |
| OK | OK | Failed | Synthesis without cross-model, tagged `[claude-only]` |
| OK | Failed | OK | Synthesis without Claude subagent |
| OK | Failed | Failed | Single-reviewer mode, noted in evaluation |
| Failed | — | — | Fatal — cannot evaluate |

### Regenerating artifacts

To regenerate all native mode artifacts (e.g. after updating config):

```bash
harness install --force
```

---

## Command reference

| Command | Description |
|---------|-------------|
| `harness install [--force / -f] [--lang / -l]` | Install agent definitions to local IDE (Cursor / Codex) |
| `harness init [--name / -n NAME] [--ci CMD] [--lang / -l] [--non-interactive / -y]` | Initialize harness configuration in the current project (interactive wizard) |
| `harness vision` | Interactively create or update project vision (.agents/vision.md) |
| `harness run <requirement> [--resume / -r] [--verbose / -V]` | Run a single development task |
| `harness auto [--resume / -r] [--verbose / -V]` | Start the autonomous development loop |
| `harness status` | Show current progress and status |
| `harness stop` | Gracefully stop the currently running task |
| `harness --version / -v` | Show version and exit |

### Key options

- **`--resume / -r`** — Restore the last session from `state.json` and continue from the interrupted phase instead of restarting. Use after unexpected exits or closed terminals.
- **`--verbose / -V`** — Print full agent input/output for debugging. Off by default for concise output.
- **`--force / -f`** (install) — Overwrite installed agent definition files (e.g. after an upgrade).
- **`--lang / -l`** (init, install) — Language for prompts and agent definitions: `en` (default) or `zh`. Install also falls back to project config or UI language when omitted.
- **`--non-interactive / -y`** (init) — Skip the wizard and use defaults. Combine with `--name` and `--ci` for project name and CI command.

---

## Configuration

Project settings live in `.agents/config.toml`. Important keys:

| Key | Default | Description |
|-----|---------|-------------|
| `workflow.mode` | "orchestrator" | Workflow mode: `orchestrator` (CLI-driven) or `cursor-native` (IDE-internal skills) |
| `workflow.profile` | "standard" | Workflow profile: `lite` / `standard` / `autonomous` (see below) |
| `workflow.max_iterations` | 3 | Max iterations per task |
| `workflow.pass_threshold` | 3.5 | Evaluator pass threshold (out of 5) |
| `workflow.auto_merge` | true | Auto-merge branch after pass |
| `workflow.branch_prefix` | "agent" | Task branch prefix |
| `workflow.dual_evaluation` | false | Dual evaluators: after quality review, run alignment review |
| `native.adversarial_model` | "gpt-4.1" | Cross-model adversarial reviewer model (cursor-native only) |
| `native.adversarial_mechanism` | "auto" | How to dispatch adversarial review: `subagent` / `cli` / `auto` |
| `native.review_gate` | "eng" | Which review layers are hard gates |
| `autonomous.max_tasks_per_session` | 10 | Max tasks per autonomous session |
| `autonomous.consecutive_block_limit` | 2 | Stop after this many consecutive blocks |

### Models (optional, silent by default)

Per-role model selection uses `.agents/config.toml` under `[models]`. Harness only passes `--model` to the IDE CLI when the resolved value is non-empty, so leaving everything unset preserves IDE default model behavior.

**Resolution order** (first match wins): `role_overrides.<role>` → `driver_defaults.<resolved_driver>` → `models.default` → empty.

The resolved driver for the role (from `[drivers]` / `[drivers.roles]`) is determined *before* looking up `driver_defaults`, so defaults always apply to the actual backend (Codex vs Cursor) in use.

Supported role names: `planner`, `builder`, `evaluator`, `alignment_evaluator`, `strategist`, `reflector`, `advisor`.

Example (commented keys are optional; empty `default` is the recommended baseline):

```toml
[models]
default = ""  # empty: never force --model unless a more specific rule sets one

[models.driver_defaults]
# codex = "o3"
# cursor = "claude-4-opus"

[models.role_overrides]
# planner = "o3-pro"
# alignment_evaluator = "o3"
# builder = ""  # explicit: this role always uses IDE default, even if global/driver default is set
```

### Workflow profiles

| Profile | Flow | When to use |
|---------|------|-------------|
| **lite** | planner → builder → eval (no spec/contract split; threshold cap 3.0; max 2 rounds) | Small changes, quick fixes, spikes |
| **standard** | planner → spec + contract → builder → eval (full four-dimensional review) | Day-to-day development (default) |
| **autonomous** | strategist → standard loop → reflector | Autonomous development with vision |

Set in `.agents/config.toml`:

```toml
[workflow]
profile = "lite"  # or "standard" / "autonomous"
```

---

## Task artifacts

Harness keeps all artifacts under `.agents/` at the project root:

```
.agents/
├── config.toml            # Project config (harness init)
├── vision.md              # Vision (harness vision)
├── state.json             # Runtime state
├── .stop                  # Stop signal (harness stop; cleared when the task ends)
├── runs/
│   └── <session-id>/
│       └── events.jsonl   # Structured events (agent calls, CI, state transitions)
├── tasks/
│   └── task-001/
│       ├── spec-r1.md     # Round 1 spec: analysis and technical plan
│       ├── contract-r1.md # Round 1 contract (Markdown)
│       ├── contract-r1.json # Round 1 contract (JSON sidecar, machine-friendly)
│       ├── evaluation-r1.md # Round 1 review (Markdown)
│       ├── evaluation-r1.json # Round 1 review (JSON sidecar: scores, verdict, feedback)
│       ├── alignment-r1.md # Alignment review (only if dual_evaluation)
│       ├── build-r1.log   # Builder log
│       ├── spec-r2.md     # Round 2 (if iterating)
│       └── ...
└── archive/               # Archived completed sessions
```

| Artifact | Produced by | Description |
|----------|-------------|-------------|
| **spec** | Planner | Analysis, technical approach, impact, risks |
| **contract** (.md + .json) | Planner | Iterative contract: deliverables, acceptance criteria, complexity |
| **evaluation** (.md + .json) | Evaluator | Four-dimensional scores (completeness / quality / regression / design) and feedback |
| **alignment** | Alignment Evaluator | Alignment review (only when `dual_evaluation` is on) |
| **events.jsonl** | System | Structured events per agent call, CI run, state change |
| **state.json** | System | Session state; supports `--resume` |

Every task step is traceable — you can answer who did what, why it passed or blocked. JSON sidecars suit automation and UIs without regex-parsing Markdown.

---

## Repository layout

```
harness-orchestrator/
├── src/harness/
│   ├── cli.py              # CLI entry (Typer)
│   ├── __init__.py          # Package metadata
│   ├── commands/            # Commands: subcommand implementations
│   ├── orchestrator/        # Orchestration: workflow core
│   ├── drivers/             # Drivers: IDE agent invocation abstraction
│   ├── core/                # Core: state, config, UI, events
│   ├── methodology/         # Methodology: evaluation, scoring, contracts
│   ├── native/              # Cursor-native mode: skill/agent/rule generator
│   ├── templates/           # Role prompt templates (orchestrator + native)
│   │   └── native/          # Jinja2 templates for cursor-native artifacts
│   └── integrations/        # Integrations: Git, Memverse
├── agents/                  # Role definition templates (Cursor / Codex)
├── tests/                   # Test suite (includes fixtures/)
├── docs/                    # Docs (state machine, compatibility matrix)
├── examples/                # Benchmarks and examples
├── pyproject.toml           # Metadata, dependencies, build
└── README.md
```

<details>
<summary>Module responsibilities</summary>

- **`cli.py`** — Single user entry; registers subcommands with Typer and delegates to `commands/`
- **`commands/`** — Argument parsing and flow startup; calls workflow logic in `orchestrator/`
- **`orchestrator/`** — Core engine: `workflow.py` for single-task loop, `autonomous.py` for autonomous loop, `vision_flow.py` for vision, `safety.py` for the safety valve
- **`drivers/`** — Wraps Cursor and Codex CLI details; upper layers use the `AgentDriver` protocol; `resolver.py` routes roles by mode (auto/cursor/codex); capability probe at startup checks versions and flags
- **`core/`** — Runtime state (`state.py`), project config (`config.py`), terminal UI (`ui.py`), structured events (`events.py`), scanning, archive, index
- **`methodology/`** — Parse evaluation output, compute four-dimensional scores, contract templates, JSON sidecars
- **`native/`** — Cursor-native mode generator: reads SSOT roles + config, renders Jinja2 templates into `.cursor/skills/`, `.cursor/agents/`, `.cursor/rules/`
- **`integrations/`** — Git branching and Memverse long-term memory

</details>

---

## Resume, stop, and troubleshooting

### Resuming interrupted work

If a run stops unexpectedly, Harness checkpoints in `state.json`:

```bash
harness run "original requirement" --resume
harness auto --resume
```

`--resume` reloads the last session and continues from the interrupted phase.

### Stop behavior

`harness stop` does not kill the process; it writes `.agents/.stop`. The running task finishes the current phase (plan/build/eval), sees the signal, and exits cleanly. For immediate abort, use `Ctrl+C`; Harness saves a checkpoint before exit.

### IDE CLI not found

Harness orchestrates; agents run via Cursor or Codex CLI. On startup Harness runs a capability probe (version and critical flags). Incompatible setups may log warnings but execution continues.

If you see `Neither Cursor nor Codex CLI detected` (or similar):

- **Cursor**: Command Palette → `Install 'cursor' command`
- **Codex**: npm or [GitHub](https://github.com/openai/codex)

Ensure the binary is on PATH; you need at least one. Version details: [docs/compatibility.md](docs/compatibility.md).

### Codex integration

For Codex roles, Harness concatenates each role's `developer_instructions` into the `codex exec` input; it does not rely on legacy `codex exec --agent`.

### Local-first

All state and artifacts stay on disk; no cloud dependency. The whole `.agents/` tree is usually gitignored — local runtime including `state.json`, task artifacts, and archives. To version `config.toml` or `vision.md` for the team, use `git add -f .agents/config.toml` (and similar) as needed.

---

## Observability

Each session writes structured events to `.agents/runs/<session-id>/events.jsonl`, one JSON object per line:

```json
{"ts": "2026-03-31T10:00:00.000Z", "event": "agent_end", "role": "planner", "driver": "codex", "exit_code": 0, "elapsed_ms": 12340, "output_len": 2048, "iteration": 1}
```

Event types include:

| Event | Contents |
|-------|----------|
| `agent_start` / `agent_end` | Role, driver, duration, exit code, output length |
| `ci_result` | CI command, exit code, verdict, duration |
| `state_transition` | From state → to state |
| `task_start` / `task_end` | Task ID, requirement, branch, final verdict and score |

Inspect logs:

```bash
cat .agents/runs/*/events.jsonl | python -m json.tool
```

---

## Dual Evaluator

With `workflow.dual_evaluation = true`, tasks that pass quality review also go through alignment review:

- **Quality Evaluator** (default) — Code quality + regression; four-dimensional scoring
- **Alignment Evaluator** — Requirement coverage + contract fit + intent drift

If alignment returns `MISALIGNED`, the task returns to Builder; if `CONTRACT_ISSUE`, feedback goes to Planner instead of Builder.

```toml
[workflow]
dual_evaluation = true
```

---

## Further reading

| Doc | Description |
|-----|-------------|
| [docs/state-machine.md](docs/state-machine.md) | Task state machine: valid transitions, resume, stop signal, BLOCKED |
| [docs/compatibility.md](docs/compatibility.md) | Runtime matrix: Cursor/Codex CLI versions, known limits |
| [examples/todo-api-benchmark/](examples/todo-api-benchmark/) | Benchmark: five incremental tasks, three modes (Codex / Cursor / Harness) |

---

## When it fits — and when it doesn't

**Good fit:**

- You already use Cursor or Codex and want agents to advance work under a clear methodology
- You want quality gates on agent output, not blind trust in one shot
- You want continuity and traceability across multi-step work

**Poor fit:**

- Expecting a one-click “build the whole product” autopilot
- Needing enterprise approval, release trains, or data orchestration unrelated to core coding
- Environments where you cannot install local CLIs (Cursor/Codex)

---

## Internationalization

Harness supports English (default) and Chinese. Set the language during initialization:

```bash
harness init --lang zh    # Chinese prompts and generated files
harness init --lang en    # English (default)
```

The language setting affects:

- CLI prompts and messages
- Agent prompts sent to the LLM
- Generated template files (vision.md, config.toml comments)
- Agent definition instructions installed to IDE

Language preference is stored in `.agents/config.toml` under `[project] lang`.

---

## Development

```bash
# Dev install (pytest + ruff)
pip install -e ".[dev]"

# Tests
pytest

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
```

Ruff targets Python 3.9 with line length 100.

---

## License

[MIT](LICENSE)
