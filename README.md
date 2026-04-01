[中文](README.zh-CN.md)

# harness-orchestrator

> Contract-driven multi-agent development framework — run a full plan-build-review-ship pipeline inside Cursor with one command.

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AI coding tools excel at single-shot tasks. Continuous development needs more: goal tracking, quality gates, adversarial review, and audit trails. Harness organizes these into a contract-driven engineering loop that runs **inside your Cursor IDE** — no separate orchestrator process, no complex setup. For CI/CD and headless automation, an optional [orchestrator mode](#advanced-cross-client-orchestrator-mode) drives Cursor and Codex agents via external CLI.

## Quick Start (Cursor-native, 3 minutes)

### 1. Install harness

```bash
pip install harness-orchestrator
harness --version   # verify (also works: python3 -m harness --version)
```

<details>
<summary>Alternative: install from source (for contributors)</summary>

```bash
git clone https://github.com/arthaszeng/harness-orchestrator.git
cd harness-orchestrator
pip install -e ".[dev]"
```

</details>

### 2. Initialize your project

```bash
cd /path/to/your/project
harness init
```

The wizard walks you through setup. When asked for **Workflow Mode**, choose **cursor-native**:

```
Step 5/9  Workflow Mode
  Choose how harness drives development:
  1. orchestrator -- External CLI process drives cursor-agent (default)
  2. cursor-native -- Skills + subagents inside Cursor IDE (no external process)
  Choose [2]: 2
  → cursor-native mode: will generate skills, subagents, and rules
```

This generates skills, subagents, and rules directly into your `.cursor/` directory.

### 3. Use it in Cursor

Open your project in Cursor. You now have **three primary entry points** that cover all task sizes — from vague ideas to specific requirements:

**Start here — three entry points for all task sizes:**

| Skill | When to use | What it does |
|-------|-------------|--------------|
| `/harness-brainstorm` | "I have an idea" | Divergent exploration → vision → plan → review gate → auto build/eval/ship/retro |
| `/harness-vision` | "I have a direction" | Clarify vision → plan → review gate → auto build/eval/ship/retro |
| `/harness-plan` | "I have a requirement" | Refine plan + adversarial review → review gate → auto build/eval/ship/retro |

All three share the same autonomous execution pipeline after plan approval: build → eval → iterate → ship → lightweight auto-retro with Memverse learning.

**Utility skills:**

| Skill | What it does |
|-------|-------------|
| `/harness-investigate` | Systematic bug investigation: reproduce → hypothesize → verify → minimal fix |
| `/harness-learn` | Memverse knowledge management: store, retrieve, update project learnings |
| `/harness-retro` | Engineering retrospective: commit analytics, hotspot detection, trend tracking |

**Advanced skills** (for granular control):

| Skill | What it does |
|-------|-------------|
| `/harness-build` | Implement the contract, run CI, triage failures, write a structured build log |
| `/harness-eval` | Three-pass adversarial code review (evaluator + primary adversarial + cross-model) |
| `/harness-ship` | Full pipeline: test → review → fix → commit → push → PR |
| `/harness-doc-release` | Documentation sync: detect stale docs after code changes |

**Try it now** — open Cursor chat and type:

```
/harness-plan add input validation to the user registration endpoint
```

Harness will plan with adversarial review, apply a review gate, build, run three-pass adversarial code review, auto-fix trivial issues, create bisectable commits, and open a PR — all without leaving your IDE.

### Updating

```bash
harness update          # upgrade to latest, reinstall agents, check config
harness update --check  # just check if a new version is available
```

---

## What happens under the hood

```
You type /harness-ship "add feature X"
  → Rebase onto main, run tests
  → Three-pass adversarial review (all dispatched in parallel):
      Pass 1: harness-evaluator structured review (4 dimensions)
      Pass 2: Primary adversarial subagent (attack surface)
      Pass 3: Cross-model review (independent perspective)
  → Fix-First: auto-fix trivial issues, ask about important ones
  → Bisectable commits + push + PR
```

### Three-pass adversarial review

Every code change goes through three independent subagents, **all dispatched in parallel**:

1. **Structured review** — The `harness-evaluator` subagent scores on completeness, quality, regression, and design
2. **Primary adversarial** — A fresh adversarial subagent hunts for security holes, race conditions, edge cases, and resource leaks
3. **Cross-model** — A reviewer from a different model family (default: `gpt-4.1`, configurable) provides independent perspective

All three passes are dispatched in parallel for maximum speed. Findings from 2+ passes are flagged as **high confidence**. The adversarial model is configurable in `.agents/config.toml`.

### Fix-First auto-remediation

Review findings are classified before presenting:

- **AUTO-FIX** — High certainty, small blast radius, reversible. Fixed immediately and committed.
- **ASK** — Security findings, behavior changes, or low confidence. Presented to you for decision.

Trivial issues never block shipping. Important decisions always get human judgment.

### Graceful degradation

| Pass 1 (Structured) | Pass 2 (Primary) | Pass 3 (Cross-model) | Behavior |
|---------------------|-----------------|---------------|----------|
| OK | OK | OK | Full three-pass synthesis |
| OK | OK | Failed | Two-pass, tagged `[primary-only]` |
| OK | Failed | OK | Two-pass without primary subagent |
| OK | Failed | Failed | Single-reviewer mode |
| Failed | — | — | Fatal — cannot evaluate |

---

## Generated artifacts

When you choose cursor-native mode, `harness init` generates:

| Artifact | Path | Purpose |
|----------|------|---------|
| `/harness-brainstorm` | `.cursor/skills/harness/harness-brainstorm/SKILL.md` | Divergent exploration → vision → plan → auto-execute to PR |
| `/harness-vision` | `.cursor/skills/harness/harness-vision/SKILL.md` | Clarify vision → plan → auto-execute to PR |
| `/harness-plan` | `.cursor/skills/harness/harness-plan/SKILL.md` | Refine plan + adversarial review → auto-execute to PR |
| `/harness-build` | `.cursor/skills/harness/harness-build/SKILL.md` | Build: implement contract, run CI, triage failures |
| `/harness-eval` | `.cursor/skills/harness/harness-eval/SKILL.md` | Three-pass review with Fix-First auto-remediation |
| `/harness-ship` | `.cursor/skills/harness/harness-ship/SKILL.md` | Full pipeline: test → review → fix → commit → PR |
| `/harness-investigate` | `.cursor/skills/harness/harness-investigate/SKILL.md` | Systematic bug investigation and minimal fix |
| `/harness-learn` | `.cursor/skills/harness/harness-learn/SKILL.md` | Memverse knowledge management |
| `/harness-doc-release` | `.cursor/skills/harness/harness-doc-release/SKILL.md` | Documentation sync after code changes |
| `/harness-retro` | `.cursor/skills/harness/harness-retro/SKILL.md` | Engineering retrospective and trend analysis |
| Adversarial reviewer | `.cursor/agents/harness-adversarial-reviewer.md` | Cross-model code reviewer (configurable model) |
| Evaluator | `.cursor/agents/harness-evaluator.md` | Structured evaluator, dispatched by eval/ship for Pass 1 |
| Trust boundary | `.cursor/rules/harness-trust-boundary.mdc` | Always-on: Builder output is untrusted |
| Fix-First | `.cursor/rules/harness-fix-first.mdc` | Always-on: classify findings before presenting |
| Workflow conventions | `.cursor/rules/harness-workflow.mdc` | Commit format, branch naming, task state |
| Safety guardrails | `.cursor/rules/harness-safety-guardrails.mdc` | Always-on: destructive command detection and warning |

To regenerate after config changes:

```bash
harness install --force
```

---

## Configuration

Project settings live in `.agents/config.toml`:

| Key | Default | Description |
|-----|---------|-------------|
| `workflow.mode` | "orchestrator" | `orchestrator` or `cursor-native` |
| `workflow.profile` | "standard" | `lite` / `standard` / `autonomous` |
| `workflow.max_iterations` | 3 | Max iterations per task |
| `workflow.pass_threshold` | 3.5 | Evaluator pass threshold (out of 5) |
| `workflow.auto_merge` | true | Auto-merge branch after pass |
| `workflow.dual_evaluation` | false | Add alignment review after quality review |
| `workflow.branch_prefix` | "agent" | Task branch prefix |
| `native.adversarial_model` | "gpt-4.1" | Cross-model reviewer model |
| `native.adversarial_mechanism` | "auto" | Adversarial dispatch mode. Allowed: `subagent`, `cli`, `auto` |
| `native.review_gate` | "eng" | Review gate strictness. Allowed: `eng` (hard gate), `advisory` (log only) |
| `native.plan_review_gate` | "auto" | Plan review gate mode. Allowed: `human` (always stop), `ai` (auto-approve), `auto` (complexity-adaptive) |
| `native.retro_window_days` | 14 | Default retro analysis window in days (1–365) |
| `autonomous.max_tasks_per_session` | 10 | Max tasks per autonomous session |
| `autonomous.consecutive_block_limit` | 2 | Stop after this many consecutive blocks |

### Models (optional)

Per-role model selection under `[models]`. Harness only passes `--model` when the resolved value is non-empty.

**Resolution order**: `role_overrides.<role>` → `driver_defaults.<driver>` → `models.default` → empty.

```toml
[models]
default = ""

[models.driver_defaults]
# codex = "o3"
# cursor = "claude-4-opus"

[models.role_overrides]
# planner = "o3-pro"
# builder = ""  # explicit: always use IDE default
```

### Workflow profiles

| Profile | Flow | When to use |
|---------|------|-------------|
| **lite** | planner → builder → eval (no spec/contract split; threshold cap 3.0; max 2 rounds) | Small changes, quick fixes |
| **standard** | planner → spec + contract → builder → eval (full review) | Day-to-day development (default) |
| **autonomous** | strategist → standard loop → reflector | Vision-driven autonomous mode |

---

## Task artifacts

All artifacts live under `.agents/` at the project root:

```
.agents/
├── config.toml            # Project config
├── vision.md              # Project vision
├── state.json             # Runtime state
├── .stop                  # Stop signal
├── runs/
│   └── <session-id>/
│       └── events.jsonl   # Structured events
├── tasks/
│   └── task-001/
│       ├── spec-r1.md     # Spec: analysis and technical plan
│       ├── contract-r1.md # Contract (Markdown)
│       ├── contract-r1.json # Contract (JSON sidecar)
│       ├── evaluation-r1.md # Review (Markdown)
│       ├── evaluation-r1.json # Review (JSON sidecar)
│       ├── alignment-r1.md # Alignment review (if dual_evaluation)
│       ├── build-r1.log   # Builder log
│       └── ...
└── archive/               # Archived sessions
```

Every step is traceable. JSON sidecars suit automation and UIs without regex-parsing Markdown.

**Local-first**: All state stays on disk; no cloud dependency. The `.agents/` tree is usually gitignored. To share `config.toml` or `vision.md` with your team, use `git add -f .agents/config.toml`.

---

## Command reference

| Command | Description |
|---------|-------------|
| `harness install [--force] [--lang]` | Install agent definitions to local IDE |
| `harness init [--name] [--ci] [--lang] [-y]` | Initialize project configuration (interactive wizard) |
| `harness vision` | Create or update project vision |
| `harness run <req> [--resume] [--verbose]` | Run a single development task |
| `harness auto [--resume] [--verbose]` | Start the autonomous development loop |
| `harness status` | Show current progress |
| `harness stop` | Gracefully stop the current task |
| `harness --version` | Show version |

---

## Advanced: Cross-Client Orchestrator Mode

Cursor-native mode covers most interactive development workflows. For **CI/CD pipelines**, **headless automation**, or **multi-IDE setups** (Cursor + Codex), use orchestrator mode.

### Prerequisites

| Dependency | Requirement | Notes |
|------------|-------------|-------|
| **Python** | >= 3.9 | Runs the Harness CLI |
| **Cursor CLI and/or Codex CLI** | At least one | Provides agent capability |
| **Git** | Any version | Project must be a Git repo |

IDE CLI setup:

- **Cursor**: Command Palette → `Install 'cursor' command`
- **Codex**: `npm install -g @openai/codex` or from [GitHub](https://github.com/openai/codex)

### Orchestrator vs Cursor-native

|  | Orchestrator | Cursor-native |
|---|---|---|
| **How it runs** | External `harness` CLI spawns agent processes | Skills + subagents inside Cursor IDE |
| **Entry point** | `harness run` / `harness auto` | `/harness-brainstorm`, `/harness-vision`, `/harness-plan` |
| **Cross-model review** | Configurable per role | Adversarial subagent with a different model |
| **When to use** | CI/CD, headless, multi-IDE | Interactive development, Cursor-only |

### Role architecture

| Role | Responsibility | Default backend (`auto` mode) |
|------|----------------|-------------------------------|
| **Planner** | Analyze requirements; produce spec and contract | Codex |
| **Builder** | Implement against the contract; commit changes | Cursor |
| **Evaluator** | Independent review; four-dimensional scoring | Codex |
| **Alignment Evaluator** | Requirement alignment and intent drift detection | Codex |
| **Strategist** | Pick the next task from vision (autonomous mode) | Codex |
| **Reflector** | Distill lessons into long-term memory | Codex/Cursor |

Each role's backend is configurable under `[drivers.roles]`. See [docs/compatibility.md](docs/compatibility.md) for CLI version requirements.

### Orchestrator setup

```bash
# 1. Install agent definitions to IDE directories
harness install

# 2. Initialize (choose "orchestrator" mode)
cd /path/to/your/project
harness init

# 3. Create project vision
harness vision

# 4. Run
harness run "add user authentication"   # single task
harness auto                            # autonomous loop

# 5. Monitor
harness status
harness stop
```

### Single-task flow (`harness run`)

```
Requirement
  → Planner: spec + iterative contract
  → Builder: implement and commit
  → Evaluator: four-dimensional score
      → Pass (≥ 3.5) → done
      → Fail → feedback to Builder, iterate
  → Max iterations (3) → blocked
```

### Autonomous loop (`harness auto`)

```
Vision
  → Strategist: pick next task
  → Single-task flow
  → Reflector: distill lessons
  → Loop until: all done / stop signal / block limit / task limit
```

### Dual Evaluator

With `workflow.dual_evaluation = true`, quality review is followed by alignment review:

- **Quality** — Code quality + regression (four-dimensional scoring)
- **Alignment** — Requirement coverage + contract fit + intent drift

If alignment returns `MISALIGNED`, the task iterates back to Builder. If `CONTRACT_ISSUE`, feedback goes to Planner to revise the contract instead.

```toml
[workflow]
dual_evaluation = true
```

---

## Troubleshooting

### Resuming interrupted work

```bash
harness run "original requirement" --resume
harness auto --resume
```

`--resume` reloads from `state.json` and continues from the interrupted phase.

### Stop behavior

`harness stop` writes `.agents/.stop`. The task finishes its current phase and exits cleanly. For immediate abort, use `Ctrl+C` — Harness saves a checkpoint before exit.

### IDE CLI not found

If you see `Neither Cursor nor Codex CLI detected`:

- **Cursor**: Command Palette → `Install 'cursor' command`
- **Codex**: `npm install -g @openai/codex`

Ensure the binary is on PATH. For cursor-native mode, Cursor CLI is optional — harness generates files that work directly in the IDE.

### Reinstalling

If `harness install` fails or produces a broken setup:

```bash
harness install --force
```

This overwrites existing files, retries CLI installations, and regenerates native artifacts.

---

## Observability

Each session writes structured events to `.agents/runs/<session-id>/events.jsonl`:

```json
{"ts": "2026-03-31T10:00:00.000Z", "event": "agent_end", "role": "planner", "driver": "codex", "exit_code": 0, "elapsed_ms": 12340}
```

Event types: `agent_start`/`agent_end`, `ci_result`, `state_transition`, `task_start`/`task_end`.

---

## Repository layout

```
harness-orchestrator/
├── src/harness/
│   ├── cli.py              # CLI entry (Typer)
│   ├── commands/            # Subcommand implementations
│   ├── orchestrator/        # Workflow core
│   ├── drivers/             # IDE agent invocation abstraction
│   ├── core/                # State, config, UI, events
│   ├── methodology/         # Evaluation, scoring, contracts
│   ├── native/              # Cursor-native mode generator
│   ├── agents/              # Role definitions (Cursor / Codex)
│   ├── templates/           # Prompt templates (orchestrator + native)
│   └── integrations/        # Git, Memverse
├── tests/                   # Test suite
├── docs/                    # State machine, compatibility
└── pyproject.toml
```

---

## When it fits — and when it doesn't

**Good fit:**

- You use Cursor and want quality gates on agent output, not blind trust
- You want traceability across multi-step work
- You want adversarial review to catch what a single pass misses

**Poor fit:**

- Expecting a one-click "build the whole product" autopilot
- Enterprise approval workflows unrelated to coding
- Environments where you cannot install Python or any supported agent CLI (Cursor/Codex)

---

## Internationalization

```bash
harness init --lang zh    # Chinese
harness init --lang en    # English (default)
```

Affects CLI messages, agent prompts, generated files, and installed agent definitions. Stored in `.agents/config.toml` under `[project] lang`.

---

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
ruff format src/ tests/
```

Ruff targets Python 3.9 with line length 100. See [docs/releasing.md](docs/releasing.md) for the release process.

---

## Further reading

| Doc | Description |
|-----|-------------|
| [docs/state-machine.md](docs/state-machine.md) | Task state machine |
| [docs/compatibility.md](docs/compatibility.md) | CLI version requirements |
| [docs/releasing.md](docs/releasing.md) | Release process and PyPI publishing |
| [examples/todo-api-benchmark/](examples/todo-api-benchmark/) | Benchmark: five tasks, three modes |

---

## License

[MIT](LICENSE)
