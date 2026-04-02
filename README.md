[中文](README.zh-CN.md)

# harness-flow

> **Cursor-native AI engineering framework** — plan, build, review, and ship inside Cursor with structured quality gates.
>
> Install: `pip install harness-flow` · Import: `import harness` · CLI: `harness`

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AI coding tools excel at single-shot tasks. Continuous development needs more: goal tracking, quality gates, adversarial review, and audit trails. Harness organizes these into a contract-driven engineering loop that runs **inside your Cursor IDE** — no separate process, no complex setup.

---

## Quick Start

### 1. Install

```bash
pip install harness-flow
harness --version
```

<details>
<summary>Install from source (contributors)</summary>

```bash
git clone https://github.com/arthaszeng/harness-flow.git
cd harness-flow
pip install -e ".[dev]"
```

</details>

### 2. Initialize your project

```bash
cd /path/to/your/project
harness init
```

The wizard walks you through setup: project info, trunk branch, CI command, Memverse integration, and evaluator model. It generates skills, subagents, and rules directly into `.cursor/`.

### 3. Start building

Open your project in Cursor. Three primary entry points cover all task sizes:

| Skill | When to use | What it does |
|-------|-------------|--------------|
| `/harness-brainstorm` | "I have an idea" | Divergent exploration → structured vision → roadmap/backlog → iterative build/eval/ship loop |
| `/harness-vision` | "I have a direction" | Clarify vision → plan → auto build/eval/ship/retro |
| `/harness-plan` | "I have a requirement" | Refine plan + 5-role review → auto build/eval/ship/retro |

Use `/harness-brainstorm` when you want a long-horizon loop that can keep picking the next active plan from a roadmap/backlog.
Use `/harness-vision` when the direction is already clear and you want one clarified increment before planning and shipping.
Use `/harness-plan` when you already have one defined task and want a single-round plan → ship flow.
The entry points still share core building blocks such as vision capture, multi-role review, and the review → ship pipeline.

**Utility skills:**

| Skill | What it does |
|-------|-------------|
| `/harness-investigate` | Systematic bug investigation: reproduce → hypothesize → verify → minimal fix |
| `/harness-learn` | Memverse knowledge management: store, retrieve, update project learnings |
| `/harness-retro` | Engineering retrospective: commit analytics, hotspot detection, trend tracking |

**Pipeline skills** (for granular control):

| Skill | What it does |
|-------|-------------|
| `/harness-build` | Implement the contract, run CI, triage failures, write a structured build log |
| `/harness-eval` | 5-role code review (architect + product-owner + engineer + qa + project-manager) |
| `/harness-ship` | Full pipeline: test → review → fix → commit → push → PR |
| `/harness-doc-release` | Documentation sync: detect stale docs after code changes |

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

| Role | Plan Review | Code Review |
|------|------------|-------------|
| **Architect** | Feasibility, module impact, dependencies | Conformance, layering, coupling, security |
| **Product Owner** | Vision alignment, user value, acceptance criteria | Requirement coverage, behavioral correctness |
| **Engineer** | Implementation feasibility, code reuse, tech debt | Code quality, DRY, patterns, performance |
| **QA** | Test strategy, boundary values, regression risk | Test coverage, edge cases, CI health |
| **Project Manager** | Task decomposition, parallelism, scope | Scope drift, plan completion, delivery risk |

Findings from 2+ roles are flagged as **high confidence**. Each role can use a different model via `[native.role_models]` in `.harness-flow/config.toml`. Invalid or locally unavailable model pins are dropped during artifact generation so agents fall back to the IDE default model instead of hard-failing on a bad config.

### Fix-First auto-remediation

Review findings are classified before presenting:

- **AUTO-FIX** — High certainty, small blast radius, reversible. Fixed immediately and committed.
- **ASK** — Security findings, behavior changes, or low confidence. Presented to you for decision.

### Graceful degradation

| Roles responding | Behavior |
|-----------------|----------|
| 5/5 | Full synthesis with cross-validation |
| 3-4/5 | Proceed with available reviews, note missing perspectives |
| 1-2/5 | Log warning, fall through to single-agent review |
| 0/5 | Fall back to single generalPurpose subagent |

---

## Generated artifacts

`harness init` generates everything Cursor needs:

| Category | Artifacts |
|----------|-----------|
| **Skills** (10) | brainstorm, vision, plan, build, eval, ship, investigate, learn, doc-release, retro |
| **Agents** (5) | architect, product-owner, engineer, qa, project-manager |
| **Rules** (4) | trust-boundary, workflow, fix-first, safety-guardrails |
| **Parallel Agents** | `.cursor/worktrees.json` — isolated git worktrees for concurrent tasks |

To regenerate after config changes:

```bash
harness init --force
```

---

## Configuration

Project settings live in `.harness-flow/config.toml`:

| Key | Default | Description |
|-----|---------|-------------|
| `workflow.max_iterations` | 3 | Max review iterations per task |
| `workflow.pass_threshold` | 7.0 | Evaluator pass threshold (1-10) |
| `workflow.auto_merge` | true | Auto-merge branch after pass |
| `workflow.branch_prefix` | "agent" | Task branch prefix |
| `native.evaluator_model` | "inherit" | Preferred default model for the 5 review roles; invalid or unavailable values fall back to IDE default |
| `native.review_gate` | "eng" | Review gate strictness (`eng` = hard gate, `advisory` = log only) |
| `native.plan_review_gate` | "auto" | Plan review gate (`human` / `ai` / `auto`) |
| `native.gate_full_review_min` | 5 | Escalation score threshold for full human review |
| `native.gate_summary_confirm_min` | 3 | Escalation score threshold for summary confirmation |
| `native.retro_window_days` | 14 | Default retro analysis window (days) |
| `native.role_models.*` | `{}` | Per-role model overrides; takes precedence over `native.evaluator_model`, but invalid or unavailable values also fall back to IDE default |

---

## CLI reference

| Command | Description |
|---------|-------------|
| `harness init [--name] [--ci] [-y] [--force]` | Initialize project (interactive wizard); `--force` regenerates artifacts |
| `harness status` | Show current task progress |
| `harness update [--check] [--force]` | Self-update + config migration check (no project artifact writes) |
| `harness --version` | Show version |

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

Architecture notes from earlier versions (orchestrator mode, state machine, driver compatibility) are preserved in [`docs/historical.md`](docs/historical.md).

---

## License

[MIT](LICENSE)
