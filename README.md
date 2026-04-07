[中文](README.zh-CN.md)

# harness-flow

> **Cursor-native AI engineering framework** — one requirement in, one PR out, with a full team of AI reviewers.

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/harness-flow)](https://pypi.org/project/harness-flow/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Your AI Engineering Team

Harness gives you a **complete engineering team** inside Cursor — each role reviews both your plan and your code:

```mermaid
classDiagram
    class HarnessTeam {
        +Requirement
        +Codebase
        +IDE: Cursor
    }
    class Architect {
        +ReviewDesign
        +CheckDependencies
        +EvaluateSecurity
    }
    class ProductOwner {
        +ReviewVision
        +ValidateRequirements
        +CheckUserValue
    }
    class Engineer {
        +ReviewCode
        +CheckPatterns
        +EvaluatePerformance
    }
    class QA {
        +WriteTests
        +RunCI
        +CheckEdgeCases
    }
    class ProjectManager {
        +TrackScope
        +ManageDelivery
        +AssessRisk
    }

    HarnessTeam --> Architect
    HarnessTeam --> ProductOwner
    HarnessTeam --> Engineer
    HarnessTeam --> QA
    HarnessTeam --> ProjectManager
```

> **Not a simulation** — these roles run as parallel AI subagents with distinct system prompts, each scoring independently. Findings from 2+ roles are flagged as high confidence.

---

## How it works

```mermaid
flowchart LR
  You["🧑‍💻 Requirement"]
  Plan["📋 Plan"]
  PR1["5-role\nplan review"]
  Build["🔨 Build\nimplement + CI"]
  Eval["🔍 Eval"]
  PR2["5-role\ncode review"]
  Ship["🚀 Ship\ncommit + PR"]

  You --> Plan --> PR1 --> Build --> Eval --> PR2 --> Ship

  subgraph "5 parallel reviewers"
    direction TB
    A["Architect"]
    PO["Product Owner"]
    E["Engineer"]
    QA["QA"]
    PM["Project Manager"]
  end

  PR1 -.-> A & PO & E & QA & PM
  PR2 -.-> A & PO & E & QA & PM
```

**Fix-First** classifies every review finding before presenting it:
- **AUTO-FIX** — high certainty, small blast radius → fixed immediately
- **ASK** — security, behavior change, low confidence → presented to you

<details>
<summary><strong>5-role review details</strong> (graceful degradation — continues with available perspectives if some fail)</summary>

| Role                | Plan Review                                       | Code Review                                  |
| ------------------- | ------------------------------------------------- | -------------------------------------------- |
| **Architect**       | Feasibility, module impact, dependencies          | Conformance, layering, coupling, security    |
| **Product Owner**   | Vision alignment, user value, acceptance criteria | Requirement coverage, behavioral correctness |
| **Engineer**        | Implementation feasibility, code reuse, tech debt | Code quality, DRY, patterns, performance     |
| **QA**              | Test strategy, boundary values, regression risk   | Test coverage, edge cases, CI health         |
| **Project Manager** | Task decomposition, parallelism, scope            | Scope drift, plan completion, delivery risk  |

Each role can use a different model via `[native.role_models]` in config. Invalid pins fall back to IDE default.

</details>

---

## Quick Start

### 0. 10-minute happy path

```mermaid
flowchart LR
  S1["① Install\npip install harness-flow"]
  S2["② Init\nharness init"]
  S3["③ Update\nharness update"]
  S1 --> S2 --> S3
```

```bash
pip install harness-flow
cd /path/to/your/project
harness init
```

Then open Cursor and type:

```
/harness-plan add input validation to the user registration endpoint
```

That's it — plan, build, 5-role review, and PR in one command.

<!-- TODO: Add a demo recording (GIF or video) showing the full flow from requirement to PR -->

---

## Harness in Action

> 🏗️ **Contract-driven development** — every task starts with a spec + contract. No code without a plan.

> 🔍 **Adversarial multi-role review** — 5 AI reviewers challenge your code from different angles, in parallel. Weak spots get caught before merge.

> 🔧 **Fix-First auto-remediation** — trivial findings are fixed instantly. You only see what matters.

> 📋 **Full audit trail** — plans, reviews, build logs, gate results. Every decision is traceable in `.harness-flow/tasks/`.

---

## All skills — default: `/harness-plan`

<details>
<summary><strong>Advanced entry points</strong></summary>

`/harness-brainstorm` is the long-horizon loop with roadmap/backlog; `/harness-vision` clarifies an incremental direction before planning; **`/harness-plan`** is the single-round plan → ship path.

| Skill                 | When to use            | What it does                                                                                 |
| --------------------- | ---------------------- | -------------------------------------------------------------------------------------------- |
| `/harness-brainstorm` | "I have an idea"       | Divergent exploration → structured vision → roadmap/backlog → iterative build/eval/ship loop |
| `/harness-vision`     | "I have a direction"   | Clarify vision → plan → auto build/eval/ship/retro                                           |
| `/harness-plan`       | "I have a requirement" | Refine plan + 5-role review → auto build/eval/ship/retro                                     |

</details>

<details>
<summary><strong>Utility & pipeline skills</strong></summary>

| Skill                  | What it does                                                                   |
| ---------------------- | ------------------------------------------------------------------------------ |
| `/harness-investigate` | Systematic bug investigation: reproduce → hypothesize → verify → minimal fix   |
| `/harness-learn`       | Memverse knowledge management: store, retrieve, update project learnings       |
| `/harness-retro`       | Engineering retrospective: commit analytics, hotspot detection, trend tracking |
| `/harness-build`       | Implement the contract, run CI, triage failures, write a structured build log  |
| `/harness-eval`        | 5-role code review (architect + product-owner + engineer + qa + project-manager) |
| `/harness-ship`        | Full pipeline: test → review → fix → commit → push → PR                        |
| `/harness-doc-release` | Documentation sync: detect stale docs after code changes                       |

</details>

<details>
<summary><strong>Progress & next-step hints</strong></summary>

- **`harness workflow next`** — one machine-readable line for agents/scripts (task id, phase, suggested skill).
- **`harness status`** — Rich panel for humans ("what to do next" in task language).
- **`HARNESS_PROGRESS`** — one-line boundary marker emitted by Cursor skills.

</details>

---

<details>
<summary><strong>Configuration</strong></summary>

Project settings live in `.harness-flow/config.toml`:

| Key                               | Default   | Description                                                       |
| --------------------------------- | --------- | ----------------------------------------------------------------- |
| `workflow.max_iterations`         | 3         | Max review iterations per task                                    |
| `workflow.pass_threshold`         | 7.0       | Evaluator pass threshold (1-10)                                   |
| `workflow.auto_merge`             | true      | Auto-merge branch after pass                                      |
| `native.evaluator_model`          | "inherit" | Default model for review roles; falls back to IDE default         |
| `native.review_gate`              | "eng"     | Review gate strictness (`eng` = hard gate, `advisory` = log only) |
| `native.plan_review_gate`         | "auto"    | Plan review gate (`human` / `ai` / `auto`)                       |
| `native.role_models.*`            | `{}`      | Per-role model overrides; falls back to IDE default               |
| `workflow.branch_prefix`          | "agent"   | Task branch prefix                                                |

</details>

<details>
<summary><strong>CLI reference</strong></summary>

| Command                                                    | Description                                          |
| ---------------------------------------------------------- | ---------------------------------------------------- |
| `harness init [--name] [--ci] [-y] [--force]`              | Initialize project (interactive wizard)              |
| `harness status`                                           | Show current task progress                           |
| `harness gate [--task]`                                    | Check ship-readiness gates                           |
| `harness update [--check] [--force]`                       | Self-update + config migration                       |
| `harness git-preflight [--json]`                           | Preflight checks (clean tree, branch, worktree)      |
| `harness save-eval --task <id> [--kind] [--verdict] ...`   | Save evaluation results                              |
| `harness save-build-log --task <id> [--body]`              | Save build log                                       |
| `harness git-prepare-branch --task-key <key>`              | Create or resume task branch                         |
| `harness git-sync-trunk [--json]`                          | Sync feature branch with trunk                       |

</details>

---

## Development

`harness init` generates **10 skills**, **5 subagents**, **4 rules** into `.cursor/`. All task state lives under `.harness-flow/` (local-first). See [MIT License](LICENSE).

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```
