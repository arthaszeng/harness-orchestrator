"""Chinese message catalog (中文消息目录)."""

MESSAGES: dict[str, str] = {
    # ── init command ──────────────────────────────────────────────
    "init.enter_range": "  请输入 1-{n} 之间的数字",
    "init.step1_title": "\nStep 2/8  项目信息",
    "init.project_name": "  项目名称",
    "init.project_desc": "  项目描述（可选）",
    "init.step2_title": "\nStep 3/8  IDE 环境",
    "init.cursor_status": "  Cursor CLI: {status}",
    "init.codex_status": "  Codex CLI:  {status}",
    "init.ide_not_detected": "未检测到",
    "init.ide_error": "\n  [error] 至少需要安装 Cursor 或 Codex CLI。",
    "init.install_agents_confirm": "  安装 agent 定义到本地 IDE?",
    "init.step3_title": "\nStep 4/8  驱动模式",
    "init.both_detected": "  检测到 Cursor + Codex，可选：",
    "init.opt_auto": "  1. auto -- Builder->Cursor, 其余->Codex（推荐）",
    "init.opt_cursor": "  2. cursor -- 全部使用 Cursor",
    "init.opt_codex": "  3. codex  -- 全部使用 Codex",
    "init.choose": "  选择",
    "init.cursor_only": "  仅检测到 Cursor，将使用 cursor 模式",
    "init.codex_only": "  仅检测到 Codex，将使用 codex 模式",
    "init.step_trunk_title": "\nStep 5/8  主干分支",
    "init.trunk_prompt": "  主干分支名称",
    "init.step4_title": "\nStep 6/8  CI 门禁",
    "init.scanning": "  分析项目结构...",
    "init.found": "    发现 {line}",
    "init.no_ci_found": "    未发现常见 CI 配置文件",
    "init.recommended_ci": "\n  推荐的 CI 命令:",
    "init.recommended_label": "（推荐）",
    "init.ai_analyze": "  {idx}. 让 AI 深度分析项目后推荐",
    "init.custom_input": "  {idx}. 自定义输入",
    "init.enter_ci": "  请输入 CI 命令",
    "init.no_suggestions": "\n  未找到自动建议，请选择：",
    "init.opt_ai_analyze": "  1. 让 AI 深度分析项目后推荐",
    "init.opt_custom": "  2. 自定义输入",
    "init.opt_skip": "  3. 跳过（不配置 CI 门禁）",
    "init.ai_no_ide": "  [warn] 无可用 IDE，跳过 AI 分析",
    "init.ai_analyzing": "  [AI] 分析中...",
    "init.ai_done": "  [AI] 完成 ({elapsed:.0f}s)",
    "init.ai_recommend": "  AI 推荐: {line}",
    "init.use_command": "  使用这个命令?",
    "init.step5_title": "\nStep 7/8  Memverse 记忆集成",
    "init.memverse_desc": "  Memverse 可在 agent 反思时将关键决策持久化到长期记忆系统。",
    "init.opt_enable": "  1. 开启",
    "init.opt_disable": "  2. 关闭（默认）",
    "init.memverse_driver": "\n  Memverse driver 将跟随全局设置: {mode}",
    "init.memverse_all_ides": "  所有可用 IDE 均可写入 Memverse。",
    "init.domain_prefix": "  Domain prefix（用于区分项目）",
    "init.step6_title": "\nStep 8/8  Vision",
    "init.opt_vision_now": "  1. 现在用 harness vision 交互式生成（推荐）",
    "init.opt_vision_later": "  2. 跳过，稍后手动编辑 .agents/vision.md",
    "init.config_exists": ".agents/config.toml 已存在，是否覆盖?",
    "init.cancelled": "已取消。",
    "init.wizard_title": "\n  HARNESS -- 项目初始化向导",
    "init.done": "\n  初始化完成！",
    "init.config_generated": "  .agents/config.toml  已生成",
    "init.vision_generated": "  .agents/vision.md    已生成",
    "init.gitignore_updated": "  .gitignore           已更新",
    "init.next_auto": "\n  运行 harness auto 开始自治开发",
    "init.next_status": "  运行 harness status 查看状态",
    "init.launch_vision": "\n  -> 启动 harness vision...\n",
    "init.gitignore_comment": "# harness — 不跟踪运行时状态",

    # ── install command ───────────────────────────────────────────
    "install.title": "harness install — 安装 agent 定义\n",
    "install.env_check": "环境检测:",
    "install.cursor_ok": "  Cursor CLI: ✓",
    "install.cursor_missing": "  Cursor CLI: ✗ 未找到",
    "install.cursor_not_ready": (
        "  Cursor CLI: ⚠ 检测到 `cursor-agent` 但未就绪\n"
        "    注意: `cursor-agent --version` 能用 ≠ agent 可用。\n"
        "    修复步骤:\n"
        "    1. 运行 `curl https://cursor.com/install | bash` 安装/更新 cursor-agent\n"
        "    2. 确保 Cursor Pro 订阅有效且已登录\n"
        "    3. 运行 `cursor-agent --help` 验证 — 应显示帮助信息而非 'installing...'"
    ),
    "install.codex_ok": "  Codex CLI:  ✓",
    "install.codex_missing": "  Codex CLI:  ✗ 未找到",
    "install.codex_not_ready": (
        "  Codex CLI:  ⚠ 检测到二进制但 `codex exec` 未就绪\n"
        "    -> 重新安装: npm install -g @openai/codex"
    ),
    "install.cursor_agent_confirm": "  是否自动安装 Cursor Agent? (curl https://cursor.com/install | bash)",
    "install.codex_cli_confirm": "  是否自动安装 Codex CLI? (npm install -g @openai/codex)",
    "install.codex_auth_confirm": "  是否进行 Codex 认证? (会打开浏览器登录 OpenAI)",
    "install.curl_missing": "  [skip] 未找到 curl，无法自动安装 Cursor Agent",
    "install.npm_missing": "  [skip] 未找到 npm，无法自动安装 Codex CLI",
    "install.cli_running": "  ▸ 正在安装 {label}...",
    "install.cli_ok": "  ✓ {label} 安装成功",
    "install.cli_fail": "  ✗ {label} 安装失败",
    "install.cli_timeout": "  ✗ {label} 安装超时",
    "install.cli_error": "  ✗ {label} 安装出错: {error}",
    "install.path_added": "  ✓ 已将 {dir} 添加到 ~/{rc} 的 PATH 中",
    "install.cursor_signin_hint": (
        "  ℹ Cursor Agent 已安装。请确保已登录 Cursor Pro:\n"
        "    打开 Cursor 应用 -> 设置 (齿轮图标) -> 登录"
    ),
    "install.cursor_signin_skip": "  ℹ Cursor Agent 已安装，请在准备好后登录 Cursor Pro。",
    "install.codex_auth_running": "  ▸ 正在启动 Codex 认证 (浏览器将打开)...",
    "install.codex_auth_done": "  ✓ Codex 认证完成",
    "install.codex_auth_skip": "  ℹ 已跳过。稍后运行 `codex auth` 完成认证。",
    "install.codex_auth_timeout": "  ⚠ Codex 认证超时，请稍后手动运行 `codex auth`。",
    "install.codex_auth_fail": "  ⚠ Codex 认证失败，请稍后手动运行 `codex auth`。",
    "install.reload_hint": (
        "\n  ┌─────────────────────────────────────────────┐\n"
        "  │  在当前终端激活 PATH，请运行:                │\n"
        "  │                                               │\n"
        "  │    source ~/{rc:<30s}│\n"
        "  │                                               │\n"
        "  │  或者直接打开一个新的终端窗口。               │\n"
        "  └─────────────────────────────────────────────┘"
    ),
    "install.no_ide": "\n[error] 未检测到 Cursor 或 Codex CLI，至少需要安装一个。",
    "install.no_source": "\n[error] agent 源文件目录不存在: {path}",
    "install.cursor_agents": "安装 Cursor agents:",
    "install.codex_agents": "安装 Codex agents:",
    "install.done": "\n完成: {count} 个 agent 定义已安装。",
    "install.warn_missing": "  [warn] 源文件不存在: {src}",
    "install.skip_exists": "  [skip] 已存在: {dst} (用 --force 覆盖)",

    # ── vision command ────────────────────────────────────────────
    "vision.no_config": "未找到 .agents/config.toml，请先运行 `harness init`",
    "vision.no_ide": "未检测到 Cursor 或 Codex CLI",
    "vision.gathering": "[vision] 收集项目上下文...",
    "vision.prompt_input": "\n请用一句话描述你想让项目实现什么（或你想调整的方向）",
    "vision.advisor_label": "[vision] advisor 展开需求",
    "vision.gen_failed": "未能生成有效 vision",
    "vision.rephrase": "请换一种方式描述你的需求",
    "vision.gen_ok": "vision 已生成",
    "vision.questions_intro": "[vision] 有几个问题想确认：",
    "vision.answer_prompt": "\n请回答以上问题（或直接回车跳过）",
    "vision.supplement": "补充说明：{answers}",
    "vision.expanded_title": "展开后的 Vision",
    "vision.confirm_prompt": "这个 vision 准确吗？ [y=确认写入 / e=补充修改 / r=重新生成]",
    "vision.invalid_choice": "请输入 y、e 或 r",
    "vision.written": "[vision] 已写入 .agents/vision.md ({size} bytes)",
    "vision.amend_prompt": "请补充你想调整的内容",
    "vision.user_supplement": "用户补充：{extra}",
    "vision.regenerate_prompt": "请重新描述你的需求",
    "vision.ctx_vision_exists": "  vision.md: 存在 ({size} bytes)",
    "vision.ctx_vision_missing": "  vision.md: 不存在",
    "vision.ctx_reflection": "  reflection.md: 存在",
    "vision.ctx_progress": "  progress.md: 存在",
    "vision.ctx_docs": "  doc/: {count} 个文档",

    # ── run command ───────────────────────────────────────────────
    "run.no_config": "未找到 .agents/config.toml，请先运行 `harness init`",
    "run.no_ide": "未检测到 Cursor 或 Codex CLI",

    # ── auto command ──────────────────────────────────────────────
    "auto.no_config": "未找到 .agents/config.toml，请先运行 `harness init`",
    "auto.no_vision": "未找到 .agents/vision.md，请先编辑项目愿景",
    "auto.resume_confirm": "检测到未完成的会话 ({session_id})，是否恢复?",
    "auto.no_ide": "未检测到 Cursor 或 Codex CLI",

    # ── stop command ──────────────────────────────────────────────
    "stop.sent": "已发送停止信号。当前任务将在完成当前阶段后停止。",
    "stop.file": "信号文件: .agents/.stop",

    # ── safety ────────────────────────────────────────────────────
    "safety.stop_signal": "收到 harness stop 信号",
    "safety.max_tasks": "达到会话任务上限 ({limit})",
    "safety.consecutive_blocked": "连续 {count} 个任务阻塞，触发熔断",

    # ── state machine ─────────────────────────────────────────────
    "state.no_active_task": "没有活跃的任务",
    "state.illegal_transition": "非法转换: {from_state} → {to_state}",

    # ── drivers ───────────────────────────────────────────────────
    "driver.codex_not_found": "Codex CLI 未找到",
    "driver.codex_timeout": "Codex agent 超时",
    "driver.codex_not_ready": (
        "检测到 Codex 二进制但 `codex exec` 不可用，请重新安装: npm install -g @openai/codex"
    ),
    "driver.cursor_not_found": "Cursor CLI 未找到",
    "driver.cursor_timeout": "Cursor agent 超时",
    "driver.cursor_not_ready": (
        "检测到 `cursor-agent` 但未就绪。"
        "修复: 1) 运行 `curl https://cursor.com/install | bash` 安装/更新  "
        "2) 确保 Cursor Pro 订阅有效且已登录  "
        "3) 运行 `cursor-agent --help` 验证"
    ),
    "driver.heartbeat": "⏳ 运行中 {elapsed:.0f}s...",
    "driver.done": "✓ 完成 ({elapsed:.0f}s)",
    "driver.retry": "⟳ 瞬时错误，{delay}s 后重试 ({attempt}/{max})...",
    "driver.no_ide": "未检测到 Cursor 或 Codex CLI",
    "driver.readonly_block": (
        "\n\n## 执行约束\n"
        "你当前是只读角色，不要修改代码或执行会改变工作区的操作。"
    ),
    "driver.system_context": (
        "## System Context\n"
        "以下内容是 Harness 为当前角色注入的 developer instructions。"
        " 这些约束优先于后续任务描述。\n\n"
        "{instructions}\n\n"
        "## Task Input\n"
        "{prompt}{readonly_block}\n"
    ),

    # ── git operations ───────────────────────────────────────────
    "git.rebasing": "[git] 正在 rebase 到 {trunk}...",
    "git.rebase_failed": "[git] rebase 失败，分支 {branch} 已保留以供手动处理",
    "git.dirty_worktree": "工作树存在未提交的更改。请先 commit 或 stash 后再启动任务。",
    "git.cleanup": "[git] 正在清理：暂存更改并切回 {trunk}",

    # ── evaluation ────────────────────────────────────────────────
    "eval.ci_not_found": "CI 命令未找到: {error}",
    "eval.ci_timeout": "CI 命令超时 (300s)",
    "eval.ci_fail_stderr": "✗ CI 失败 ({elapsed:.0f}s)",
    "eval.ci_pass_stderr": "✓ CI 通过 ({elapsed:.0f}s)",
    "eval.ci_pass": "CI 通过",

    # ── workflow prompts ──────────────────────────────────────────
    "prompt.project_root": "项目根目录: {project_root}",
    "prompt.plan": (
        "项目根目录: {project_root}\n\n"
        "## 需求\n{requirement}\n\n"
        "## 项目规范（摘要）\n"
        "{agents_md}\n"
        "{tree_block}\n\n"
        "请分析需求，输出 Spec（技术规格）和首次迭代的 Contract（合同）。\n"
        "严格按照你的 agent 指令中定义的格式输出。"
    ),
    "prompt.plan_no_agents": "（未找到 AGENTS.md）",
    "prompt.file_tree_heading": "\n## 项目文件树\n```\n{tree}\n```",
    "prompt.iterate": (
        "项目根目录: {project_root}\n\n"
        "## 原始需求\n{requirement}\n\n"
        "## 上轮合同（已有成果 — 保持正确的部分）\n"
        "{previous_contract}\n\n"
        "## Evaluator 反馈（需修复的问题）\n{feedback}\n\n"
        "请根据反馈，输出更新后的 Spec 和 Contract。\n"
        "- **保持**上轮合同中已正确完成的交付物\n"
        "- **新增或修改**交付物以解决 Evaluator 指出的问题\n"
        "- 包含一条交付物，明确禁止合同范围外的改动\n"
        "严格按照你的 agent 指令中定义的 Spec + Contract 格式输出。"
    ),
    "prompt.builder": (
        "## 任务\n{requirement}\n\n"
        "## 技术规格（Planner 的分析结果，供参考）\n"
        "{spec}\n\n"
        "## 合同（你的交付清单）\n{contract}\n\n"
        "## 项目上下文（已预读，不要重复读取这些文件）\n"
        "{context}\n\n"
        "## 执行要求\n"
        "- 按合同交付物逐项实现，完成后提交代码\n"
        "- 上方已提供项目规范和关键文件内容，**跳过探索阶段，直接开始编码**\n"
        "- 只在需要查看 prompt 未包含的文件时才调用 read/glob\n"
        "- 遵守项目的编码规范和架构约束\n\n"
        "## 变更边界约束（强制执行）\n"
        "- **只修改合同交付物直接涉及的文件**\n"
        "- **禁止删除现有测试** — 可以新增测试，但不得移除已有测试\n"
        "- **禁止修改交付物列表未涉及的文件**\n"
        "- 如果发现合同范围外的相关问题，在输出中记录但不要修改代码\n"
        "- 不要改动版本号、无关配置或合同未提及的文件"
    ),
    "prompt.builder_no_spec": "（无）",
    "prompt.builder_no_context": "（无预读上下文）",
    "prompt.agents_md_heading": "### AGENTS.md（项目规范）\n{content}",
    "prompt.file_tree_section": "### 项目文件树\n```\n{tree}\n```",
    "prompt.contract_refs_heading": "### 合同引用的关键文件\n",
    "prompt.contract_refs_overflow": "... (更多文件已省略，请自行读取)",
    "prompt.git_diff_unavailable": "(无法获取分支差异)",
    "prompt.eval": (
        "项目根目录: {project_root}\n\n"
        "## 原始需求\n{requirement}\n\n"
        "## 合同\n{contract}\n\n"
        "## 本轮变更（核心 — 根据合同评估 Builder 的工作）\n"
        "{iteration_summary}\n\n"
        "## 累积分支变更（上下文 — 所有迭代的合并变更）\n"
        "分支: {branch}\n\n"
        "{branch_summary}\n\n"
        "## Builder 工作日志（摘要）\n{build_log}\n\n"
        "## 评估指引\n"
        "- **关键**：Builder 会 commit 代码，因此 `git diff`（working tree）可能为空。\n"
        "  请使用上方的变更摘要，或执行 `git diff <trunk>..HEAD` 来查看实际变更。\n"
        "- **请基于本轮合同和本轮变更打分。**\n"
        "  不要因为前轮遗留的问题扣分，除非 Builder 使之恶化。\n"
        "- 检查测试状态，按四维标准打分。\n"
        "- 严格按照你的 agent 指令中定义的 Evaluation 格式输出。"
    ),
    "prompt.eval_no_log": "（无日志）",
    "prompt.alignment": (
        "项目根目录: {project_root}\n\n"
        "## 原始需求\n{requirement}\n\n"
        "## 合同\n{contract}\n\n"
        "## Builder 分支变更\n分支: {branch}\n\n{branch_summary}\n\n"
        "## 对齐评估指引\n"
        "请评估实现是否与原始需求和合同对齐。关注：\n"
        "1. 需求中的每个要点是否被覆盖\n"
        "2. 合同的每个交付物和验收标准是否被满足\n"
        "3. 实现是否偏离需求的核心意图\n"
        "4. 合同本身是否遗漏了需求中的关键点\n\n"
        "严格按照你的 agent 指令中定义的格式输出。"
    ),
    "prompt.ci_fail_heading": "# CI 失败",
    "prompt.ci_fail_feedback": "CI 失败:\n{feedback}",
    "prompt.builder_fail_feedback": "Builder 执行失败:\n{output}",
    "prompt.builder_noop_feedback": "Builder 返回成功但未产生任何代码变更（可能工具调用全部被中断）。Builder 输出:\n{output}",
    "prompt.driver_error": "驱动级错误，重试无意义",

    # ── autonomous prompts ────────────────────────────────────────
    "prompt.strategist": (
        "## 项目愿景\n{vision}\n\n"
        "## 当前进展\n{progress}\n\n"
        "## 已完成任务数: {completed}\n"
        "## 已阻塞任务: {blocked}\n\n"
        "请决定下一个最有价值的任务。\n"
        "如果所有愿景目标已达成，输出 VISION_COMPLETE。\n"
        "否则，按格式输出下一个任务的需求描述。"
    ),
    "prompt.reflector": (
        "## 项目愿景\n{vision}\n\n"
        "## 当前进展\n{progress}\n\n"
        "## 会话统计\n"
        "- 已完成: {completed}\n"
        "- 已阻塞: {blocked}\n"
        "- 平均得分: {avg_score:.1f}\n"
        "- 总迭代: {total_iterations}\n\n"
        "请按格式生成反思总结，包括 Vision 对齐度评估。"
    ),
    "prompt.requirement_regex": r"##\s*(?:需求|Requirement)\s*",

    # ── vision flow prompts ───────────────────────────────────────
    "prompt.advisor_project": "## 项目名称\n{name}",
    "prompt.advisor_input": "## 用户需求\n{input}",
    "prompt.advisor_vision": "## 现有 Vision\n{vision}",
    "prompt.advisor_progress": "## 已完成的工作\n{progress}",
    "prompt.advisor_reflection": "## Reflector 反思\n{reflection}",
    "prompt.advisor_docs": "## 项目文档摘要\n{docs}",
    "prompt.advisor_tree": "## 项目结构\n```\n{tree}\n```",
    "prompt.advisor_instruction": (
        "请根据以上上下文，将用户需求展开为结构化的项目愿景。"
        "严格按照你的指令中定义的四段式格式输出。"
    ),
    "prompt.advisor_failed": "Advisor 调用失败，请重试。",

    # ── AI CI suggestion prompt ───────────────────────────────────
    "prompt.ai_ci": (
        "分析以下项目，推荐一个适合作为自动化 CI 门禁的命令。\n"
        "要求：命令应覆盖代码质量检查和单元测试，但不应包含慢速的冒烟测试或需要网络的操作。\n\n"
        "项目根目录: {project_root}\n"
        "项目结构发现:\n{report}\n\n"
        "请直接输出推荐的命令（一行），不要其他解释。例如：make check test"
    ),
}
