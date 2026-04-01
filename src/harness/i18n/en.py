"""English message catalog (default)."""

MESSAGES: dict[str, str] = {
    # ── init command ──────────────────────────────────────────────
    "init.enter_range": "  Please enter a number between 1 and {n}",
    "init.step1_title": "\nStep 2/9  Project Info",
    "init.project_name": "  Project name",
    "init.project_desc": "  Description (optional)",
    "init.step2_title": "\nStep 3/9  IDE Environment",
    "init.cursor_status": "  Cursor CLI: {status}",
    "init.codex_status": "  Codex CLI:  {status}",
    "init.ide_not_detected": "not detected",
    "init.ide_error": "\n  [error] At least one of Cursor or Codex CLI must be installed.",
    "init.install_agents_confirm": "  Install agent definitions to local IDE?",
    "init.step3_title": "\nStep 4/9  Driver Mode",
    "init.both_detected": "  Detected Cursor + Codex, options:",
    "init.opt_auto": "  1. auto -- Builder->Cursor, others->Codex (recommended)",
    "init.opt_cursor": "  2. cursor -- Use Cursor for all roles",
    "init.opt_codex": "  3. codex  -- Use Codex for all roles",
    "init.choose": "  Choose",
    "init.cursor_only": "  Only Cursor detected, using cursor mode",
    "init.codex_only": "  Only Codex detected, using codex mode",
    # ── native mode selection ─────────────────────────────────────
    "init.step_mode_title": "\nStep 5/9  Workflow Mode",
    "init.mode_desc": "  Cursor detected. Choose how harness drives development:",
    "init.mode_desc_no_cursor": "  Choose how harness drives development (cursor-native works without Cursor CLI):",
    "init.no_ide_hint": "  No IDE CLI detected. You can still use cursor-native mode (generates files only).",
    "init.no_ide_orchestrator_warn": "  Error: orchestrator mode requires at least one IDE CLI (cursor or codex).",
    "init.opt_orchestrator": "  1. orchestrator -- External CLI process drives cursor-agent (default)",
    "init.opt_native": "  2. cursor-native -- Skills + subagents inside Cursor IDE (no external process)",
    "init.mode_native_selected": "  → cursor-native mode: will generate skills, subagents, and rules",
    "init.mode_orchestrator_selected": "  → orchestrator mode: standard CLI-driven workflow",
    "init.native_adversarial_model": "  Adversarial review model (cross-model eval)",

    "init.step_trunk_title": "\nStep 6/9  Trunk Branch",
    "init.trunk_prompt": "  Trunk (main) branch name",
    "init.step4_title": "\nStep 7/9  CI Gate",
    "init.scanning": "  Analyzing project structure...",
    "init.found": "    Found {line}",
    "init.no_ci_found": "    No common CI config files found",
    "init.recommended_ci": "\n  Recommended CI commands:",
    "init.recommended_label": " (recommended)",
    "init.ai_analyze": "  {idx}. Let AI analyze the project and recommend",
    "init.custom_input": "  {idx}. Custom input",
    "init.enter_ci": "  Enter CI command",
    "init.no_suggestions": "\n  No automatic suggestions, please choose:",
    "init.opt_ai_analyze": "  1. Let AI analyze the project and recommend",
    "init.opt_custom": "  2. Custom input",
    "init.opt_skip": "  3. Skip (no CI gate)",
    "init.ai_no_ide": "  [warn] No available IDE, skipping AI analysis",
    "init.ai_analyzing": "  [AI] Analyzing...",
    "init.ai_done": "  [AI] Done ({elapsed:.0f}s)",
    "init.ai_recommend": "  AI recommends: {line}",
    "init.use_command": "  Use this command?",
    "init.step5_title": "\nStep 8/9  Memverse Integration",
    "init.memverse_desc": "  Memverse persists key decisions to long-term memory during agent reflection.",
    "init.opt_enable": "  1. Enable",
    "init.opt_disable": "  2. Disable (default)",
    "init.memverse_driver": "\n  Memverse driver follows global setting: {mode}",
    "init.memverse_all_ides": "  All available IDEs can write to Memverse.",
    "init.domain_prefix": "  Domain prefix (to distinguish projects)",
    "init.step6_title": "\nStep 9/9  Vision",

    # ── native mode generation ────────────────────────────────────
    "native.generating": "  Generating Cursor-native mode artifacts...",
    "native.generated_skill": "    [ok] skill: {path}",
    "native.generated_agent": "    [ok] agent: {path}",
    "native.generated_rule": "    [ok] rule:  {path}",
    "native.done": "  ✓ {count} native mode artifacts generated",
    "native.init_hint": "\n  Cursor-native mode ready! Use these skills in Cursor IDE:",
    "native.hint_plan": "    /harness-plan   — Plan and decompose a task",
    "native.hint_build": "    /harness-build  — Implement the plan",
    "native.hint_eval": "    /harness-eval   — Cross-model adversarial review",
    "native.hint_ship": "    /harness-ship   — End-to-end: plan → build → eval → commit → push",
    "init.opt_vision_now": "  1. Generate now with harness vision (recommended)",
    "init.opt_vision_later": "  2. Skip, edit .agents/vision.md later",
    "init.config_exists": ".agents/config.toml already exists, overwrite?",
    "init.cancelled": "Cancelled.",
    "init.wizard_title": "\n  HARNESS -- Project Init Wizard",
    "init.done": "\n  Initialization complete!",
    "init.config_generated": "  .agents/config.toml  generated",
    "init.vision_generated": "  .agents/vision.md    generated",
    "init.gitignore_updated": "  .gitignore           updated",
    "init.next_auto": "\n  Run harness auto to start autonomous development",
    "init.next_status": "  Run harness status to check progress",
    "init.launch_vision": "\n  -> Launching harness vision...\n",
    "init.gitignore_comment": "# harness — do not track runtime state",

    # ── install command ───────────────────────────────────────────
    "install.title": "harness install — Install agent definitions\n",
    "install.env_check": "Environment check:",
    "install.cursor_ok": "  Cursor CLI: ✓",
    "install.cursor_missing": "  Cursor CLI: ✗ not found",
    "install.cursor_not_ready": (
        "  Cursor CLI: ⚠ `cursor-agent` found but not functional\n"
        "    Note: `cursor-agent --version` works ≠ agent is ready.\n"
        "    To fix:\n"
        "    1. Run `curl https://cursor.com/install | bash` to install/update cursor-agent\n"
        "    2. Ensure Cursor Pro subscription is active and you are signed in\n"
        "    3. Run `cursor-agent --help` to verify — it should show help, not 'installing...'"
    ),
    "install.codex_ok": "  Codex CLI:  ✓",
    "install.codex_missing": "  Codex CLI:  ✗ not found",
    "install.codex_not_ready": (
        "  Codex CLI:  ⚠ binary found but `codex exec` not ready\n"
        "    -> Reinstall: npm install -g @openai/codex"
    ),
    "install.cursor_agent_confirm": "  Auto-install Cursor Agent? (curl https://cursor.com/install | bash)",
    "install.codex_cli_confirm": "  Auto-install Codex CLI? (npm install -g @openai/codex)",
    "install.codex_auth_confirm": "  Run Codex authentication? (opens browser for OpenAI login)",
    "install.curl_missing": "  [skip] curl not found, cannot auto-install Cursor Agent",
    "install.npm_missing": "  [skip] npm not found, cannot auto-install Codex CLI",
    "install.cli_running": "  ▸ Installing {label}...",
    "install.cli_ok": "  ✓ {label} installed successfully",
    "install.cli_fail": "  ✗ {label} installation failed",
    "install.cli_timeout": "  ✗ {label} installation timed out",
    "install.cli_error": "  ✗ {label} installation error: {error}",
    "install.path_added": "  ✓ Added {dir} to PATH in ~/{rc}",
    "install.cursor_signin_hint": (
        "  ℹ Cursor Agent installed. Make sure you are signed in to Cursor Pro:\n"
        "    Open Cursor app -> Settings (gear icon) -> Sign In"
    ),
    "install.cursor_signin_skip": "  ℹ Cursor Agent installed. Sign in to Cursor Pro when ready.",
    "install.codex_auth_running": "  ▸ Starting Codex authentication (browser will open)...",
    "install.codex_auth_done": "  ✓ Codex authentication complete",
    "install.codex_auth_skip": "  ℹ Skipped. Run `codex auth` later to authenticate.",
    "install.codex_auth_timeout": "  ⚠ Codex auth timed out. Run `codex auth` manually later.",
    "install.codex_auth_fail": "  ⚠ Codex auth failed. Run `codex auth` manually later.",
    "install.reload_hint": (
        "\n  ┌─────────────────────────────────────────────┐\n"
        "  │  To activate PATH in current terminal, run:  │\n"
        "  │                                               │\n"
        "  │    source ~/{rc:<30s}│\n"
        "  │                                               │\n"
        "  │  Or simply open a new terminal window.        │\n"
        "  └─────────────────────────────────────────────┘"
    ),
    "install.no_ide": "\n[error] Neither Cursor nor Codex CLI detected. At least one is required.",
    "install.no_source": "\n[error] Agent source directory not found: {path}",
    "install.cursor_agents": "Installing Cursor agents:",
    "install.codex_agents": "Installing Codex agents:",
    "install.done": "\nDone: {count} agent definition(s) installed.",
    "install.warn_missing": "  [warn] Source file not found: {src}",
    "install.skip_exists": "  [skip] Already exists: {dst} (use --force to overwrite)",
    "install.force_retry": "  ▸ --force mode: retrying installation without prompts...",
    "install.force_hint": "\n  Tip: run `harness install --force` to overwrite files and retry failed installations.",

    # ── vision command ────────────────────────────────────────────
    "vision.no_config": ".agents/config.toml not found, please run `harness init` first",
    "vision.no_ide": "Neither Cursor nor Codex CLI detected",
    "vision.gathering": "[vision] Gathering project context...",
    "vision.prompt_input": "\nDescribe in one sentence what you want the project to achieve (or the direction to adjust)",
    "vision.advisor_label": "[vision] advisor expanding requirement",
    "vision.gen_failed": "Failed to generate a valid vision",
    "vision.rephrase": "Please describe your requirement differently",
    "vision.gen_ok": "vision generated",
    "vision.questions_intro": "[vision] A few questions to confirm:",
    "vision.answer_prompt": "\nPlease answer the questions above (or press Enter to skip)",
    "vision.supplement": "Supplementary notes: {answers}",
    "vision.expanded_title": "Expanded Vision",
    "vision.confirm_prompt": "Is this vision accurate? [y=confirm / e=amend / r=regenerate]",
    "vision.invalid_choice": "Please enter y, e, or r",
    "vision.written": "[vision] Written to .agents/vision.md ({size} bytes)",
    "vision.amend_prompt": "What would you like to adjust?",
    "vision.user_supplement": "User supplement: {extra}",
    "vision.regenerate_prompt": "Please describe your requirement again",
    "vision.ctx_vision_exists": "  vision.md: exists ({size} bytes)",
    "vision.ctx_vision_missing": "  vision.md: not found",
    "vision.ctx_reflection": "  reflection.md: exists",
    "vision.ctx_progress": "  progress.md: exists",
    "vision.ctx_docs": "  doc/: {count} document(s)",

    # ── run command ───────────────────────────────────────────────
    "run.no_config": ".agents/config.toml not found, please run `harness init` first",
    "run.no_ide": "Neither Cursor nor Codex CLI detected",

    # ── auto command ──────────────────────────────────────────────
    "auto.no_config": ".agents/config.toml not found, please run `harness init` first",
    "auto.no_vision": ".agents/vision.md not found, please edit the project vision first",
    "auto.resume_confirm": "Incomplete session detected ({session_id}), resume?",
    "auto.no_ide": "Neither Cursor nor Codex CLI detected",

    # ── stop command ──────────────────────────────────────────────
    "stop.sent": "Stop signal sent. The current task will stop after completing its current phase.",
    "stop.file": "Signal file: .agents/.stop",

    # ── safety ────────────────────────────────────────────────────
    "safety.stop_signal": "Received harness stop signal",
    "safety.max_tasks": "Reached session task limit ({limit})",
    "safety.consecutive_blocked": "{count} consecutive tasks blocked, circuit breaker triggered",

    # ── state machine ─────────────────────────────────────────────
    "state.no_active_task": "No active task",
    "state.illegal_transition": "Illegal transition: {from_state} → {to_state}",

    # ── drivers ───────────────────────────────────────────────────
    "driver.codex_not_found": "Codex CLI not found",
    "driver.codex_timeout": "Codex agent timed out",
    "driver.codex_not_ready": (
        "Codex binary found but `codex exec` is not functional. "
        "Please reinstall: npm install -g @openai/codex"
    ),
    "driver.cursor_not_found": "Cursor CLI not found",
    "driver.cursor_timeout": "Cursor agent timed out",
    "driver.cursor_not_ready": (
        "`cursor-agent` found but not functional. "
        "Fix: 1) Run `curl https://cursor.com/install | bash` to install/update  "
        "2) Ensure Cursor Pro subscription and signed in  "
        "3) Run `cursor-agent --help` to verify"
    ),
    "driver.heartbeat": "⏳ running {elapsed:.0f}s...",
    "driver.done": "✓ done ({elapsed:.0f}s)",
    "driver.retry": "⟳ transient error, retrying in {delay}s ({attempt}/{max})...",
    "driver.no_ide": "Neither Cursor nor Codex CLI detected",
    "driver.readonly_block": (
        "\n\n## Execution Constraints\n"
        "You are in read-only mode. Do not modify code or perform actions that change the workspace."
    ),
    "driver.system_context": (
        "## System Context\n"
        "The following are developer instructions injected by Harness for the current role."
        " These constraints take priority over the subsequent task description.\n\n"
        "{instructions}\n\n"
        "## Task Input\n"
        "{prompt}{readonly_block}\n"
    ),

    # ── git operations ───────────────────────────────────────────
    "git.rebasing": "[git] rebasing onto {trunk}...",
    "git.rebase_failed": "[git] rebase failed, branch {branch} preserved for manual resolution",
    "git.dirty_worktree": "Working tree has uncommitted changes. Commit or stash them before starting a task.",
    "git.cleanup": "[git] cleaning up: stashing changes and switching to {trunk}",

    # ── evaluation ────────────────────────────────────────────────
    "eval.ci_not_found": "CI command not found: {error}",
    "eval.ci_timeout": "CI command timed out (300s)",
    "eval.ci_fail_stderr": "✗ CI failed ({elapsed:.0f}s)",
    "eval.ci_pass_stderr": "✓ CI passed ({elapsed:.0f}s)",
    "eval.ci_pass": "CI passed",

    # ── workflow prompts ──────────────────────────────────────────
    "prompt.project_root": "Project root: {project_root}",
    "prompt.plan": (
        "Project root: {project_root}\n\n"
        "## Requirement\n{requirement}\n\n"
        "## Project Spec (Summary)\n"
        "{agents_md}\n"
        "{tree_block}\n\n"
        "## Planning Principles\n"
        "- **Search Before Building**: before proposing new patterns or dependencies, "
        "check what the project already uses. Prefer extending existing conventions "
        "over introducing new ones.\n"
        "- **Completeness**: the contract should cover tests, error handling, and type safety "
        "when the cost is small — do not defer obvious work to later iterations.\n\n"
        "Analyze the requirement and output a Spec (technical specification) "
        "and the first-iteration Contract.\n"
        "Strictly follow the format defined in your agent instructions."
    ),
    "prompt.plan_no_agents": "(AGENTS.md not found)",
    "prompt.file_tree_heading": "\n## Project File Tree\n```\n{tree}\n```",
    "prompt.iterate": (
        "Project root: {project_root}\n\n"
        "## Original Requirement\n{requirement}\n\n"
        "## Previous Contract (completed work — preserve what is correct)\n"
        "{previous_contract}\n\n"
        "## Evaluator Feedback (issues to fix)\n{feedback}\n\n"
        "Based on the feedback, produce an updated Spec and Contract for the next iteration.\n"
        "- **Preserve** deliverables from the previous contract that were completed correctly\n"
        "- **Add or revise** deliverables to address the evaluator's feedback\n"
        "- Include a deliverable that explicitly forbids changes outside the contract scope\n"
        "Strictly follow the Spec + Contract format defined in your agent instructions."
    ),
    "prompt.builder": (
        "## Task\n{requirement}\n\n"
        "## Technical Specification (Planner's analysis, for reference)\n"
        "{spec}\n\n"
        "## Contract (your delivery checklist)\n{contract}\n\n"
        "## Project Context (pre-loaded, do not re-read these files)\n"
        "{context}\n\n"
        "## Engineering Principles\n"
        "- **Search Before Building**: before writing new code, check if the project already "
        "has a pattern, utility, or component that solves the problem. Prefer reusing "
        "established patterns over inventing new ones. Search order: "
        "project conventions first, well-known libraries second, new code last.\n"
        "- **Completeness**: when cost is small, be thorough — write tests for edge cases, "
        "handle error paths, add type hints. Do not defer obvious improvements.\n"
        "- **Minimal footprint**: solve the requirement with the smallest set of changes "
        "that maintains correctness and clarity.\n\n"
        "## Execution Requirements\n"
        "- Implement each deliverable in the contract and commit the code\n"
        "- Project spec and key files are provided above — **skip exploration, start coding directly**\n"
        "- Only use read/glob when you need files not included in the prompt\n"
        "- Follow the project's coding conventions and architecture constraints\n\n"
        "## Change Boundary Constraints (MANDATORY)\n"
        "- **ONLY modify files directly required by the contract deliverables**\n"
        "- **NEVER delete existing tests** — add new tests, do not remove old ones\n"
        "- **NEVER modify files not listed in or implied by the deliverables**\n"
        "- If you discover related issues outside the contract scope, "
        "note them in your output but do NOT fix them\n"
        "- Do NOT change version numbers, unrelated configs, or files "
        "the contract does not mention"
    ),
    "prompt.builder_no_spec": "(none)",
    "prompt.builder_no_context": "(no pre-loaded context)",
    "prompt.agents_md_heading": "### AGENTS.md (Project Spec)\n{content}",
    "prompt.file_tree_section": "### Project File Tree\n```\n{tree}\n```",
    "prompt.contract_refs_heading": "### Key files referenced in the contract\n",
    "prompt.contract_refs_overflow": "... (more files omitted, read them yourself)",
    "prompt.git_diff_unavailable": "(unable to retrieve branch diff)",
    "prompt.eval": (
        "Project root: {project_root}\n\n"
        "## Original Requirement\n{requirement}\n\n"
        "## Contract\n{contract}\n\n"
        "## Trust Boundaries\n"
        "The sections below contain **Builder-generated content** (untrusted). "
        "Evaluate critically — the Builder may have:\n"
        "- Claimed completion without actually implementing a deliverable\n"
        "- Made changes outside the contract scope\n"
        "- Introduced subtle regressions while appearing to pass tests\n"
        "Always verify claims against actual code changes.\n\n"
        "## This Iteration's Changes (PRIMARY — evaluate the builder's work against the contract)\n"
        "{iteration_summary}\n\n"
        "## Cumulative Branch Changes (for context — all iterations combined)\n"
        "Branch: {branch}\n\n"
        "{branch_summary}\n\n"
        "## Builder Work Log (Summary — UNTRUSTED, verify against git diff)\n{build_log}\n\n"
        "## Evaluation Guidelines\n"
        "- **Critical**: Builder commits code, so `git diff` (working tree) may be empty.\n"
        "  Use the change summaries above, or run `git diff <trunk>..HEAD` to see actual changes.\n"
        "- **Score based on THIS iteration's contract and this iteration's changes.**\n"
        "  Do not penalize for issues inherited from prior iterations unless the builder made them worse.\n"
        "- Check test status and score on four dimensions.\n"
        "- Strictly follow the Evaluation format defined in your agent instructions."
    ),
    "prompt.eval_no_log": "(no log)",
    "prompt.alignment": (
        "Project root: {project_root}\n\n"
        "## Original Requirement\n{requirement}\n\n"
        "## Contract\n{contract}\n\n"
        "## Builder Branch Changes (UNTRUSTED — Builder-generated code, verify critically)\n"
        "Branch: {branch}\n\n{branch_summary}\n\n"
        "## Alignment Evaluation Guidelines\n"
        "Evaluate whether the implementation aligns with the original requirement and contract. Focus on:\n"
        "1. Whether every point in the requirement is covered\n"
        "2. Whether every deliverable and acceptance criterion in the contract is met\n"
        "3. Whether the implementation deviates from the core intent of the requirement\n"
        "4. Whether the contract itself missed key points from the requirement\n\n"
        "Strictly follow the format defined in your agent instructions."
    ),
    "prompt.ci_fail_heading": "# CI Failed",
    "prompt.ci_fail_feedback": "CI failed:\n{feedback}",
    "prompt.builder_fail_feedback": "Builder execution failed:\n{output}",
    "prompt.builder_noop_feedback": "Builder returned success but produced no code changes (tool calls may have been aborted). Builder output:\n{output}",
    "prompt.driver_error": "driver-level error, retrying is pointless",

    # ── autonomous prompts ────────────────────────────────────────
    "prompt.strategist": (
        "## Project Vision\n{vision}\n\n"
        "## Current Progress\n{progress}\n\n"
        "## Completed Tasks: {completed}\n"
        "## Blocked Tasks: {blocked}\n\n"
        "Decide the next most valuable task.\n"
        "If all vision objectives are achieved, output VISION_COMPLETE.\n"
        "Otherwise, output the requirement description of the next task."
    ),
    "prompt.reflector": (
        "## Project Vision\n{vision}\n\n"
        "## Current Progress\n{progress}\n\n"
        "## Session Stats\n"
        "- Completed: {completed}\n"
        "- Blocked: {blocked}\n"
        "- Avg score: {avg_score:.1f}\n"
        "- Total iterations: {total_iterations}\n\n"
        "Generate a reflection summary following the prescribed format, "
        "including a Vision alignment assessment."
    ),
    "prompt.requirement_regex": r"##\s*(?:Requirement|需求)\s*",

    # ── vision flow prompts ───────────────────────────────────────
    "prompt.advisor_project": "## Project Name\n{name}",
    "prompt.advisor_input": "## User Requirement\n{input}",
    "prompt.advisor_vision": "## Existing Vision\n{vision}",
    "prompt.advisor_progress": "## Completed Work\n{progress}",
    "prompt.advisor_reflection": "## Reflector Reflection\n{reflection}",
    "prompt.advisor_docs": "## Project Documentation Summary\n{docs}",
    "prompt.advisor_tree": "## Project Structure\n```\n{tree}\n```",
    "prompt.advisor_instruction": (
        "Based on the context above, expand the user requirement into a structured project vision."
        " Strictly follow the four-section format defined in your instructions."
    ),
    "prompt.advisor_failed": "Advisor invocation failed, please try again.",

    # ── AI CI suggestion prompt ───────────────────────────────────
    "prompt.ai_ci": (
        "Analyze the following project and recommend a command suitable for automated CI gating.\n"
        "Requirements: the command should cover code quality checks and unit tests, "
        "but should not include slow smoke tests or operations that require network access.\n\n"
        "Project root: {project_root}\n"
        "Project structure findings:\n{report}\n\n"
        "Output only the recommended command (one line), no other explanation. "
        "Example: make check test"
    ),
}
