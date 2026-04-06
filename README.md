[中文](README.zh-CN.md)

# harness-flow

> **Cursor-native AI engineering framework** — plan, build, review, and ship inside Cursor with structured quality gates.
>
> Install: `pip install harness-flow` · Import: `import harness` · CLI: `harness`

[Python](https://www.python.org/)
[License: MIT](LICENSE)

AI coding tools excel at single-shot tasks. Continuous development needs more: goal tracking, quality gates, adversarial review, and audit trails. Harness organizes these into a contract-driven engineering loop that runs **inside your Cursor IDE** — no separate process, no complex setup.

---

## Quick Start

### 0. 10-minute happy path

If you want one shortest route from zero to a shippable task:

```bash
pip install harness-flow
harness --version
cd /path/to/your/project
harness init --non-interactive
harness git-preflight --json
```

Then open Cursor in the project and run:

```text
/harness-plan add input validation to the user registration endpoint
```

When it finishes, you should have: a task directory, evaluation artifacts, and a branch state ready for ship/PR (subject to your remote/auth setup).

**Prerequisites:** clean git working tree before `harness git-preflight`, Cursor installed, and this repo initialized in the project as above.

### Progress vs next-step hints

- **`HARNESS_NEXT`** — `harness workflow next` prints one machine line for agents/scripts (task id, phase, suggested skill).
- **`HARNESS_PROGRESS`** — Cursor skills may emit a one-line boundary marker; `harness status --progress-line` prints a similar line when `.harness-flow/tasks/.../workflow-state.json` is valid (same `step/total` is a coarse workflow map, not per-skill step counts).
- **`harness status`** — default Rich view for humans (“what to do next” in task language).

### 1. Install

```bash
pip install harness-flow
harness --version
```

Install from source (contributors)

```bash
git clone https://github.com/arthaszeng/harness-flow.git
cd harness-flow
pip install -e ".[dev]"
```



### 2. Initialize your project

```bash
cd /path/to/your/project
harness init
```

The wizard walks you through setup: project info, trunk branch, CI command, Memverse integration, and evaluator model. It generates skills, subagents, and rules directly into `.cursor/`.

### 3. Start building

**Default path (most tasks):** in Cursor, run **`/harness-plan`** with a plain-language requirement (see **Try it now** below). If the ask is a little fuzzy, ask **one** clarification round in the **same** chat, then keep planning—no command switch required for light in-session exploration.

**Advanced entry points** (full capability preserved—use when you intentionally want long-horizon ideation, standing roadmap/backlog loops, or vision-first multi-round framing):

| Skill                 | When to use            | What it does                                                                                 |
| --------------------- | ---------------------- | -------------------------------------------------------------------------------------------- |
| `/harness-brainstorm` | "I have an idea"       | Divergent exploration → structured vision → roadmap/backlog → iterative build/eval/ship loop |
| `/harness-vision`     | "I have a direction"   | Clarify vision → plan → auto build/eval/ship/retro                                           |
| `/harness-plan`       | "I have a requirement" | Refine plan + 5-role review → auto build/eval/ship/retro                                     |

For everyday **single-task** delivery, stay on **`/harness-plan`**. The advanced skills reuse the same building blocks (vision capture, multi-role review, review → ship); they add different **human interaction depth** and loop shape—not a different "tier" of quality.

`/harness-brainstorm` is the **long-horizon loop** with roadmap/backlog; use `/harness-vision` to clarify an incremental direction before planning; **`/harness-plan`** is the **single-round plan** → ship path when the task is already scoped.

**Utility skills:**


| Skill                  | What it does                                                                   |
| ---------------------- | ------------------------------------------------------------------------------ |
| `/harness-investigate` | Systematic bug investigation: reproduce → hypothesize → verify → minimal fix   |
| `/harness-learn`       | Memverse knowledge management: store, retrieve, update project learnings       |
| `/harness-retro`       | Engineering retrospective: commit analytics, hotspot detection, trend tracking |


**Pipeline skills** (for granular control):


| Skill                  | What it does                                                                     |
| ---------------------- | -------------------------------------------------------------------------------- |
| `/harness-build`       | Implement the contract, run CI, triage failures, write a structured build log    |
| `/harness-eval`        | 5-role code review (architect + product-owner + engineer + qa + project-manager) |
| `/harness-ship`        | Full pipeline: test → review → fix → commit → push → PR                          |
| `/harness-doc-release` | Documentation sync: detect stale docs after code changes                         |

**Pipeline order:** **`/harness-build`** implements the contract; **`/harness-ship`** runs tests, **mandatory code eval**, `harness gate`, and PR — it **does not** write feature code. For a one-line hint from `workflow-state.json`, run **`harness workflow next`** in the repo root (same task pick as `harness gate`).


**Try it now:**

```
/harness-plan add input validation to the user registration endpoint
```

---

## How it works

```
You type /harness-ship "add feature X"
  → Rebase onto main, run tests
  → 5-role code evaluation (all dispatched in parallel):
      Architect:       design + security review
      Product Owner:   completeness + behavior
      Engineer:        quality + performance
      QA:              regression + testing (only role running CI)
      Project Manager: scope + delivery
  → Fix-First: auto-fix trivial issues, ask about important ones
  → Bisectable commits + push + PR
```

### 5-role review system

The same 5 specialized roles review both **plans** and **code**, dispatched in parallel:


| Role                | Plan Review                                       | Code Review                                  |
| ------------------- | ------------------------------------------------- | -------------------------------------------- |
| **Architect**       | Feasibility, module impact, dependencies          | Conformance, layering, coupling, security    |
| **Product Owner**   | Vision alignment, user value, acceptance criteria | Requirement coverage, behavioral correctness |
| **Engineer**        | Implementation feasibility, code reuse, tech debt | Code quality, DRY, patterns, performance     |
| **QA**              | Test strategy, boundary values, regression risk   | Test coverage, edge cases, CI health         |
| **Project Manager** | Task decomposition, parallelism, scope            | Scope drift, plan completion, delivery risk  |


Findings from 2+ roles are flagged as **high confidence**. Each role can use a different model via `[native.role_models]` in `.harness-flow/config.toml`. Invalid or locally unavailable model pins are dropped during artifact generation so agents fall back to the IDE default model instead of hard-failing on a bad config.

### Fix-First auto-remediation

Review findings are classified before presenting:

- **AUTO-FIX** — High certainty, small blast radius, reversible. Fixed immediately and committed.
- **ASK** — Security findings, behavior changes, or low confidence. Presented to you for decision.

### Graceful degradation


| Roles responding | Behavior                                                  |
| ---------------- | --------------------------------------------------------- |
| 5/5              | Full synthesis with cross-validation                      |
| 3-4/5            | Proceed with available reviews, note missing perspectives |
| 1-2/5            | Log warning, fall through to single-agent review          |
| 0/5              | Fall back to single generalPurpose subagent               |


---

## Generated artifacts

`harness init` generates everything Cursor needs:


| Category            | Artifacts                                                                           |
| ------------------- | ----------------------------------------------------------------------------------- |
| **Skills** (10)     | brainstorm, vision, plan, build, eval, ship, investigate, learn, doc-release, retro |
| **Agents** (5)      | architect, product-owner, engineer, qa, project-manager                             |
| **Rules** (4)       | trust-boundary, workflow, fix-first, safety-guardrails                              |
| **Parallel Agents** | `.cursor/worktrees.json` — isolated git worktrees for concurrent tasks              |


To regenerate after config changes:

```bash
harness init --force
```

---

## Configuration

Project settings live in `.harness-flow/config.toml`:


| Key                               | Default   | Description                                                                                                                               |
| --------------------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `workflow.max_iterations`         | 3         | Max review iterations per task                                                                                                            |
| `workflow.pass_threshold`         | 7.0       | Evaluator pass threshold (1-10)                                                                                                           |
| `workflow.auto_merge`             | true      | Auto-merge branch after pass                                                                                                              |
| `workflow.branch_prefix`          | "agent"   | Task branch prefix                                                                                                                        |
| `native.evaluator_model`          | "inherit" | Preferred default model for the 5 review roles; invalid or unavailable values fall back to IDE default                                    |
| `native.review_gate`              | "eng"     | Review gate strictness (`eng` = hard gate, `advisory` = log only)                                                                         |
| `native.plan_review_gate`         | "auto"    | Plan review gate (`human` / `ai` / `auto`)                                                                                                |
| `native.gate_full_review_min`     | 5         | Escalation score threshold for full human review                                                                                          |
| `native.gate_summary_confirm_min` | 3         | Escalation score threshold for summary confirmation                                                                                       |
| `native.retro_window_days`        | 14        | Default retro analysis window (days)                                                                                                      |
| `native.role_models.*`            | `{}`      | Per-role model overrides; takes precedence over `native.evaluator_model`, but invalid or unavailable values also fall back to IDE default |


---

## CLI reference

### Core

| Command                                        | Description                                                              |
| ---------------------------------------------- | ------------------------------------------------------------------------ |
| `harness init [--name] [--ci] [-y] [--force]`  | Initialize project (interactive wizard); `--force` regenerates artifacts |
| `harness status`                               | Show current task progress                                               |
| `harness gate [--task]`                        | Check ship-readiness gates for the current task                          |
| `harness update [--check] [--force]`           | Self-update + config migration check                                     |
| `harness --version`                            | Show version                                                             |

### Git lifecycle

| Command                                                                          | Description                                            |
| -------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `harness git-preflight [--json]`                                                 | Structured preflight checks (clean tree, branch, worktree) |
| `harness git-prepare-branch --task-key <key> [--short-desc] [--json]`            | Create or resume task branch on top of trunk            |
| `harness git-sync-trunk [--json]`                                                | Sync current feature branch with configured trunk       |
| `harness git-post-ship [--task-key] [--pr] [--branch] [--wait-merge] [--json]`   | Run post-ship cleanup after PR merge                    |
| `harness git-post-ship-watch [--task-key] [--pr] [--branch] [--json]`            | Start detached post-ship watcher and return immediately  |
| `harness git-post-ship-reconcile [--max-items] [--json]`                         | Reconcile persisted post-ship pending queue              |

### Artifact persistence

| Command                                                                     | Description                                   |
| --------------------------------------------------------------------------- | --------------------------------------------- |
| `harness save-eval --task <id> [--kind] [--verdict] [--score] [--body]`     | Save evaluation results (plan or code)         |
| `harness save-build-log --task <id> [--body]`                               | Save build log to task directory               |
| `harness save-ship-metrics --task <id> [--branch] [--pr-quality-score] ...` | Save ship-metrics.json to task directory        |
| `harness save-feedback-ledger --task <id> [--body]`                         | Save feedback-ledger.jsonl to task directory    |
| `harness save-intervention-audit --task <id> --event-type --command [--summary]` | Append one manual-intervention audit event |


---

## Task artifacts

All task state lives under `.harness-flow/`:

```
.harness-flow/
├── config.toml            # Project configuration
├── vision.md              # Project vision
├── tasks/
│   └── task-001/
│       ├── plan.md        # Plan with spec and contract
│       ├── plan-eval-r1.md
│       ├── code-eval-r2.md
│       ├── intervention-audit.jsonl
│       ├── build-r1.md
│       └── ...
└── archive/               # Archived sessions
```

**Local-first**: all state stays on disk — no cloud dependency.

---

## Repository layout

```
harness-flow/
├── src/harness/
│   ├── cli.py              # CLI entry (Typer)
│   ├── commands/            # init, update, status
│   ├── core/                # Config, state, UI, events
│   ├── native/              # Cursor-native artifact generator
│   ├── templates/           # Jinja2 templates
│   └── integrations/        # Git, Memverse
├── tests/
├── docs/                    # Architecture and historical docs
└── pyproject.toml
```

---

## Internationalization

```bash
harness init --lang zh    # Chinese
harness init --lang en    # English (default)
```

---

## Updating

```bash
harness update          # upgrade + config check; no project artifact writes
harness update --check  # just check for new version
```

---

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
ruff format src/ tests/
```

---

## Historical documentation

Architecture notes from earlier versions (orchestrator mode, state machine, driver compatibility) are preserved in [docs/historical.md](docs/historical.md).

---

## License

[MIT](LICENSE)