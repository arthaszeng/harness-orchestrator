# Changelog

## Unreleased

### Breaking Changes

- **Removed CLI commands**: `git-post-ship-watch`, `git-post-ship-reconcile`, `worktree-init`
- **Removed `SessionState` persistence**: `state.json` is no longer created or read. All state is now exclusively managed through `workflow-state.json` per task directory.
- **Removed `--wait-merge` / `--timeout-sec` / `--poll-interval-sec` options** from `git-post-ship`
- **Removed worktree subsystem**: `harness.core.worktree` module and `harness.commands.worktree_init` deleted. Worktree symlink setup is now handled by Cursor's native `.cursor/worktrees.json` post-create hook. If not using Cursor, create symlinks manually: `ln -sfn <main-tree>/.harness-flow .harness-flow` and similarly for `.cursor/skills/harness`, `.cursor/agents`, `.cursor/rules`.
- **Removed `context.worktree` field** from `harness git-preflight --json` output. Scripts consuming this field should remove the check.
- **Removed `WORKTREE_SKIP`** return from `prepare_task_branch()` in linked worktrees. Branch preparation now executes normally regardless of worktree status.
- **Removed `DirtyWorktreeError` compatibility alias** in `harness.integrations.git_ops`. Use `DirtyWorkingTreeError` directly. Migration: `from harness.integrations.git_ops import DirtyWorkingTreeError`.
- **Renamed error code `DIRTY_WORKTREE`** → `DIRTY_WORKING_TREE` in `GitOperationResult` and i18n keys (`git_preflight.recovery.DIRTY_WORKING_TREE`). Scripts matching the old code string should update accordingly.
- **Moved `extract_task_key_from_branch` / `extract_task_id_from_branch`** from `harness.core.worktree` to `harness.core.task_identity`.

### Changed

- `**status` and `progress**` fully rewritten to use `WorkflowState` as the sole data source. SessionState-based dashboards removed.
- **Preflight templates** (en/zh) simplified: worktree detection step removed, steps renumbered 1–4.
- **Ship templates** (en/zh) removed Step 8.25 (post-ship watcher auto-trigger).
- `**harness init`** no longer blocks execution inside a linked worktree.

### Removed

- `SessionState`, `TaskRecord`, `CompletedTask`, `SessionStats`, `StopContext`, `TaskArtifacts` models from `state.py`
- `post_ship_pending.py` and `post_ship_watcher.py` modules
- `update_progress()` function (progress.md generation)
- Status dashboard stats panel and recent-result panel (data source removed)

## 4.1.50

### Added

- `**harness workflow next`** — prints one machine-readable `HARNESS_NEXT task=… phase=… skill=… hint="…"` line from the latest task’s `workflow-state.json`, using the **same task resolution as `harness gate`** (explicit `--task`, then `HARNESS_TASK_ID`, then latest numeric `task-NNN`).

### Changed

- **Native skill templates (SSOT):** clarify the default pipeline `**/harness-build` → `/harness-ship`**; `**/harness-ship` does not implement feature code** (tests, mandatory 5-role eval, `harness save-eval`, `harness gate`, PR). Added a short **continuity + eval gate** block to plan/build/ship skills to reduce skipped eval and “plan/build then stop” behavior on weaker models. Vision/plan execution text aligned.
- **Merged `/harness-brainstorm` into `/harness-vision`** — Vision now auto-detects whether to explore (Socratic questioning + approach options) or clarify (quick 1–2 questions). The loop controller (Roadmap/Backlog/ActivePlan/FeedbackLedger/StopConditions) is now part of Vision. Brainstorm entry point removed.

## 4.1.0

### Breaking Changes

- **Project renamed** from `harness-orchestrator` to `harness-flow`. Install with `pip install harness-flow`. The Python package name (`harness`) and CLI command (`harness`) are unchanged.
- **Migration:** If upgrading from `harness-orchestrator`, run `pip uninstall harness-orchestrator && pip install harness-flow`.

## 4.0.0 (2026-04-02)

### Breaking Changes

- **Removed orchestrator mode** — The external CLI-driven orchestrator (`harness run`, `harness auto`, `harness stop`, `harness vision`) has been removed. Harness now operates exclusively in cursor-native mode.
- **Removed CLI commands**: `run`, `auto`, `stop`, `vision`
- **Removed modules**: `harness.orchestrator`, `harness.drivers`, `harness.methodology`, `harness.agents` (packaged agent definitions)
- **Removed config fields**: `workflow.mode`, `workflow.profile`, `workflow.dual_evaluation`, `[drivers]` section, `integrations.memverse.driver`
- **Removed role registry**: Orchestrator roles (planner, builder, evaluator, alignment_evaluator, strategist, reflector) removed from `harness.core.roles`

### Migration

- **Old configs are safe**: `HarnessConfig` now uses `extra="ignore"`, so `.agents/config.toml` files with `[drivers]` or removed `[workflow]` fields will load without errors.
- **Use Cursor skills instead of CLI**: `/harness-plan`, `/harness-vision` replace the removed CLI commands.
- **Run `harness install --force`** after upgrading to regenerate native artifacts.

### What's kept

- Full cursor-native mode: skill generation, 5-role review system, Fix-First auto-remediation
- CLI commands: `init`, `install`, `status`, `update`
- Core infrastructure: config, state, UI, events, registry, git ops, scanner
- All native templates and generated artifacts

### Simplified

- `harness init` wizard: 6 steps (was 9) — no IDE probing, no mode selection
- `harness install`: only generates native artifacts (no IDE agent copying)
- `config.py`: cleaner model without driver configs
- `roles.py`: minimal exports (NATIVE_REVIEW_ROLES, SCORING_DIMENSIONS)
- `state.py`: data models only (StateMachine removed)
- i18n catalogs: ~72 keys each (was ~270+)