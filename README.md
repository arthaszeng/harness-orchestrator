[中文](README.zh-CN.md)

# harness-flow

### Agent writes code. Harness Flow ships products.

**L5 autonomous delivery for the vibe coding era — you're the copilot now.**

[Python](https://www.python.org/)
[PyPI](https://pypi.org/project/harness-flow/)
[License: MIT](LICENSE)

## The Problem

AI agents can write code — but they **can't ship products**. They lack navigation (goal management), traffic rules (quality gates), and a dashcam (audit trail). The bottleneck has shifted from *"can AI write code?"* to *"can AI autonomously deliver?"*

## Where Harness Flow Fits

<p align="center">
  <img src="docs/assets/evolution-l5-en.png" alt="The Evolution of Software Development: from manual coding (L0) to AI assistant (L1) to agent mode (L3) to Harness Flow autonomous delivery (L5)" width="800" />
</p>

### The Three Pillars of L5


|     | Navigation               | Traffic Rules                 | Dashcam                         |
| --- | ------------------------ | ----------------------------- | ------------------------------- |
|     | vision → plan → roadmap  | adaptive multi-role review + gates + trust | audit trail + learnings + retro |
|     | AI knows **where** to go | AI obeys the **rules**        | every decision **recorded**     |


---

## How It Works

```mermaid
flowchart LR
  Req["Requirement"] --> Plan["Plan"]
  Plan --> PlanReview["Adaptive\nplan review"]
  PlanReview --> Build["Build + CI"]
  Build --> CodeReview["Adaptive\ncode review"]
  CodeReview --> Ship["Ship → PR"]

  PlanReview -.-|"Architect · PO · Engineer · QA · PM"| CodeReview

  style Req fill:#fff,stroke:#222,stroke-width:2px,color:#000
  style Plan fill:#fff,stroke:#222,stroke-width:2px,color:#000
  style PlanReview fill:#222,stroke:#222,stroke-width:2px,color:#fff
  style Build fill:#fff,stroke:#222,stroke-width:2px,color:#000
  style CodeReview fill:#222,stroke:#222,stroke-width:2px,color:#fff
  style Ship fill:#fff,stroke:#222,stroke-width:2px,color:#000
```



One requirement in → one PR out. Both plan and code are reviewed by 5 parallel AI reviewers. Findings from 2+ roles on the same issue are flagged `[HIGH CONFIDENCE]`.

**Fix-First** classifies every review finding:

- **AUTO-FIX** — high certainty + small blast radius + reversible → fixed immediately
- **ASK** — security, behavior change, architecture → batched for your decision

---

## Quick Start

### 0. 10-minute happy path

**Step 1** — Install:

```bash
pip install harness-flow
```

**Step 2** — Initialize in your project:

```bash
cd <YOUR_PROJECT_PATH>
harness init
```

**Step 3** — Open Cursor, type a requirement:

```
/harness-plan add input validation to the user registration endpoint
```

That's it — plan, build, adaptive multi-role review, and PR. One command.

**What you'll see:** the agent generates a spec + contract, 5 reviewers challenge the plan in parallel, then the agent implements, runs CI, gets code reviewed by the same 5 roles, and opens a PR — all autonomously.

---

## Deep Dive

**Your AI Engineering Team — 5 parallel reviewers**

Harness gives you a **complete engineering team** inside Cursor — each role reviews both your plan and your code:


| Role                | Plan Review                                       | Code Review                                  |
| ------------------- | ------------------------------------------------- | -------------------------------------------- |
| **Architect**       | Feasibility, module impact, dependencies          | Conformance, layering, coupling, security    |
| **Product Owner**   | Vision alignment, user value, acceptance criteria | Requirement coverage, behavioral correctness |
| **Engineer**        | Implementation feasibility, code reuse, tech debt | Code quality, DRY, patterns, performance     |
| **QA**              | Test strategy, boundary values, regression risk   | Test coverage, edge cases, CI health         |
| **Project Manager** | Task decomposition, parallelism, scope            | Scope drift, plan completion, delivery risk  |


> **Not a simulation** — these roles run as parallel AI subagents with distinct system prompts, each scoring independently. Findings from 2+ roles are flagged as high confidence.

Each role can use a different model via `[native.role_models]` in config. If some reviewers fail, the pipeline continues with available perspectives (graceful degradation).

**Contract-Driven Development**

Every task starts with a **spec + contract** — deliverables, acceptance criteria, and risk analysis — reviewed by 5 roles before any code is written.

The contract lives in `.harness-flow/tasks/task-NNN/plan.md` and serves as the single source of truth. Runtime state is tracked in `workflow-state.json` alongside it.

**Fix-First Auto-Remediation**

Every review finding is classified before presenting it to you:

- **AUTO-FIX** (high certainty + small blast radius + reversible) → fixed immediately, tests re-run
- **ASK** (security, behavior change, architecture, low confidence) → batched and presented for your decision

Typical auto-fixes: unused imports, stale comments, missing null checks, naming inconsistencies, obvious N+1 queries.

**Full Audit Trail**

Plans, reviews, build logs, gate results — all persisted per task. Every decision is traceable.

```
.harness-flow/
├── config.toml              # project settings (CI command, trunk branch, language)
├── vision.md                # product direction (optional)
└── tasks/task-NNN/
    ├── plan.md              # spec + contract (scope SSOT)
    ├── handoff-*.json       # structured context per phase (plan, build, eval, ship)
    ├── build-rN.md          # build log per round
    ├── plan-eval-rN.md      # plan review per round
    ├── code-eval-rN.md      # code review per round
    ├── ship-metrics.json    # delivery metrics (scores, test count, coverage)
    ├── workflow-state.json  # canonical task phase / gate / blocker tracking
    └── ...                  # feedback ledger, intervention audit, etc. (optional)
```

---

## Installation & Upgrade


| Command                    | What it does                                                         |
| -------------------------- | -------------------------------------------------------------------- |
| `pip install harness-flow` | Install the CLI                                                      |
| `harness init`             | Interactive wizard → generates skills, agents, rules into `.cursor/` |
| `harness init --force`     | Regenerate all artifacts (after config changes or version upgrade)   |
| `harness update`           | Self-update the package + run config migration                       |
| `harness update --check`   | Check for new version without installing                             |


---

## All Skills — default: `/harness-plan`

`/harness-plan` is the default for most tasks — single-round plan → ship path.

`/harness-vision` covers everything from vague ideas to clear directions — it auto-detects whether to explore or clarify.

**Entry points**


| Skill             | When to use                       | What it does                                                                              |
| ----------------- | --------------------------------- | ----------------------------------------------------------------------------------------- |
| `/harness-plan`   | "I have a requirement"            | Refine plan + adaptive review → auto build/eval/ship/retro                                |
| `/harness-vision` | "I have an idea" or "a direction" | Explore or clarify → structured vision → roadmap/backlog → iterative build/eval/ship loop |


**Utility & pipeline skills**


| Skill                  | What it does                                                                     |
| ---------------------- | -------------------------------------------------------------------------------- |
| `/harness-investigate` | Systematic bug investigation: reproduce → hypothesize → verify → minimal fix     |
| `/harness-learn`       | Memverse knowledge management: store, retrieve, update project learnings         |
| `/harness-retro`       | Engineering retrospective: commit analytics, hotspot detection, trend tracking   |
| `/harness-build`       | Implement the contract, run CI, triage failures, write a structured build log    |
| `/harness-eval`        | Adaptive multi-role code review (FAST/LITE/FULL based on escalation score)       |
| `/harness-ship`        | Full pipeline: test → review → fix → commit → push → PR                          |
| `/harness-doc-release` | Documentation sync: detect stale docs after code changes                         |


**Progress & next-step hints**

- `**harness workflow next`** — one machine-readable line for agents/scripts (task id, phase, suggested skill).
- `**harness status`** — Rich panel for humans ("what to do next" in task language).
- `**HARNESS_PROGRESS**` — one-line boundary marker emitted by Cursor skills.

---

**Configuration**

Project settings live in `.harness-flow/config.toml`:


| Key                       | Default   | Description                                                       |
| ------------------------- | --------- | ----------------------------------------------------------------- |
| `workflow.max_iterations` | 3         | Max review iterations per task                                    |
| `workflow.pass_threshold` | 7.0       | Evaluator pass threshold (1-10)                                   |
| `workflow.auto_merge`     | true      | Auto-merge branch after pass                                      |
| `native.evaluator_model`  | "inherit" | Default model for review roles; falls back to IDE default         |
| `native.review_gate`      | "eng"     | Review gate strictness (`eng` = hard gate, `advisory` = log only) |
| `native.plan_review_gate` | "auto"    | Plan review gate (`human` / `ai` / `auto`)                        |
| `native.role_models.`*    | `{}`      | Per-role model overrides; falls back to IDE default               |
| `workflow.branch_prefix`  | "agent"   | Task branch prefix                                                |


**CLI reference**


| Command | Description |
| --- | --- |
| **Project setup** | |
| `harness init [--name] [--ci] [-y] [--force]` | Initialize project (interactive wizard) |
| `harness update [--check] [--force]` | Self-update + config migration |
| `harness status` | Show current task progress |
| `harness version` | Show version and runtime info |
| **Git operations** | |
| `harness git-preflight [--json]` | Preflight checks (clean tree, branch) |
| `harness git-prepare-branch --task-key <key>` | Create or resume task branch |
| `harness git-sync-trunk [--json]` | Sync feature branch with trunk |
| `harness git-post-ship [--json]` | Post-ship cleanup after PR merge |
| **Quality gates** | |
| `harness gate [--task]` | Check ship-readiness gates |
| `harness plan-lint --task <id> [--json]` | Validate plan.md structure |
| `harness validate-artifacts --task <id> [--json]` | Report artifact dependency status |
| `harness preflight-bundle --task <id> [--json]` | Run 4-in-1 preflight checks |
| **Artifact persistence** | |
| `harness save-eval --task <id> [--kind] [--verdict] ...` | Save evaluation results |
| `harness save-build-log --task <id> [--body]` | Save build log |
| `harness save-ship-metrics --task <id> [--body]` | Save ship metrics JSON |
| `harness save-feedback-ledger --task <id> [--body]` | Save feedback ledger entry |
| `harness save-intervention-audit --task <id> ...` | Save intervention audit event |
| `harness save-failure --task <id> [--pattern] ...` | Record failure pattern |
| **Review & calibration** | |
| `harness escalation-score compute [--phase] ...` | Compute escalation score |
| `harness review-score compute [--kind] [--json]` | Calibrate review score and verdict |
| `harness calibrate [--task] [--json]` | Review calibration report |
| `harness trust [--json]` | Progressive trust profile |
| `harness record-outcome --task <id> ...` | Record actual CI/revert outcome |
| **Workflow helpers** | |
| `harness workflow next [--task] [--json]` | Workflow hints from task state |
| `harness task next-id [--json]` | Next available task ID |
| `harness search-failures --query <q> [--limit]` | Search failure patterns across tasks |
| `harness context-budget --task <id> [--json]` | Estimate token usage vs budget |
| `harness plan-completion-audit --task <id> [--json]` | Audit deliverable completion vs diff |
| `harness diff-stat [--json]` | Branch diff statistics |
| `harness ship-prepare --task <id> [--json]` | Pre-compute ship metadata |
| **Cross-stage coordination** | |
| `harness handoff read\|write [--task] ...` | Structured cross-stage handoff |
| `harness session read\|write [--task] ...` | Intra-phase session context |
| `harness barrier register\|complete\|check\|list ...` | Barrier management for async tasks |
| **Infrastructure** | |
| `harness worktree-setup` | Create symlinks in linked worktree |
| `harness pr-status [--json]` | Query CI and merge status of a PR |
| `harness ci-logs [--json]` | Retrieve logs from failed CI jobs |


---

## Development

`harness init` generates **9 skills**, **5 subagents**, **4 rules** into `.cursor/`. All task state lives under `.harness-flow/` (local-first). See [MIT License](LICENSE).

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

