# Project Vision — harness-flow

## 项目目标

harness-flow 是一个 Cursor-native 的多智能体开发流水线框架。
通过在 `.cursor/` 中生成 skills、agents、rules 文件，直接在 Cursor IDE 内
驱动 plan → build → eval → ship 的完整开发工作流。

## 关键功能

1. **Native Artifact Generation** — 从模板生成 `.cursor/skills/`, `.cursor/agents/`, `.cursor/rules/`
2. **5-Role Review System** — architect, product-owner, engineer, qa, project-manager 并行审查
3. **Harness Skills Pipeline** — brainstorm → vision → plan → build → eval → ship → retro
4. **CLI 工具** — `harness init` / `harness update` / `harness status`

## 技术约束

- Python 3.9+ 兼容
- 仅依赖 typer, pydantic, jinja2, rich
- 不依赖任何外部 IDE CLI（cursor-agent / codex）
- 所有工作流在 Cursor IDE 内通过 skills 和 subagents 执行

## 非目标

- 不通过 CLI 驱动外部 IDE 进程（原 orchestrator 模式已移除）
- 不支持 Codex CLI 集成
- 不维护独立于 IDE 的自动化工作流引擎

## [2026-04-02] — 移除 Orchestrator 模式，专注 Cursor Native

决定移除原有的"跨客户端 orchestrator"模式（通过 CLI 驱动 Cursor/Codex 进程），
仅保留 cursor-native 模式。原因：实际使用中 native 模式（在 IDE 内通过 skills 驱动）
的体验远优于外部 CLI 编排，后者增加了大量复杂度（drivers、process management、
methodology parsing）却带来有限的价值。此次精简将大幅降低代码复杂度和维护负担。

## [2026-04-02] — 项目重命名 harness-orchestrator → harness-flow

"orchestrator" 已不再描述项目的本质。v4.0.0 移除编排模式后，项目的核心是
brainstorm → vision → plan → build → eval → ship → retro 的开发流水线。
"flow" 更准确地传达了这一价值主张。重命名范围：PyPI 包名、GitHub repo、所有文档
和配置引用。Python 顶级包名 `harness` 保持不变。

## [2026-04-02] — Brainstorm 进化为持续迭代引擎

`/harness-brainstorm` 不再只负责把模糊想法收敛成一次性的 plan，而要升级为长期方向驱动的
迭代入口：先通过提问挖掘真实需求并沉淀为结构化 vision，再生成 roadmap、plan backlog 和
反馈账本，由系统在每轮 eval 后根据方向一致性与交付反馈自动决定下一轮最值得推进的 plan。

这个模式服务于高频开发者的混合场景：既能处理确定性的交付任务，也能处理需要自主探索的发散
需求。核心原则是“方向稳定、计划可重排、反馈可积累、执行可连续”，直到用户明确喊停。

## [2026-04-01] — 参考 Claude Code，强化 Cursor-native Workflow Intelligence

### Problem / User

当前 harness-flow 对高频使用 Cursor 的复杂开发流来说，既缺少清晰、可查询的阶段状态与
交付门禁，也缺少轻量、稳定的阶段交接方式。用户不只会遇到“代码改完了但漏 eval / 漏验证 /
漏 PR”“中断后难以恢复到正确阶段”，还会遇到 planner、implementer、reviewer、fixer 依赖
整段历史对话和长日志传递上下文，导致信息噪声高、阶段职责变形，也让项目定位容易漂向
“再造一个通用 agent runtime”。

### North Star

把 harness-flow 升级为一个 Cursor-native 的 workflow intelligence layer：它不取代 Cursor
做通用编码 agent，而是把结构化任务上下文编译成适合不同阶段执行的输入，再把阶段输出沉淀成
可复用的工作流产物。它提供仓库内机器可读的状态、门禁与恢复能力，也提供分层上下文、阶段
handoff 和规则/记忆注入，让高频开发者把它当成可信赖的 workflow brain。这里若提到“runtime”，
指的是仓库内可查询的流程语义与状态，而不是第二套常驻执行内核。

### Success Signals

- [W1: 单任务主干] ✅ 用户可以通过统一状态入口或约定产物看到 `plan -> build -> eval -> ship`
的最小状态、阻塞原因与阶段转移，而不再主要依赖 transcript 猜进度 — *B1 PR #46*
- [W1: 单任务主干] ✅ 阶段之间默认通过结构化 handoff artifact 传递任务目标、前一阶段摘要、
变更范围与验证/发现摘要，而不是继续搬运整段对话与长日志 — *B2 PR #48*
- [W1: 单任务主干] ✅ `ship` 前的关键前置条件可被系统显式检查；缺少 eval、验证或必要产物时会被
硬门禁拦下，并给出明确阻塞原因 — *B3 PR #47*
- [W1: 单任务主干] ✅ 在同分支、同任务上下文下，中断恢复能回到正确阶段与任务记录 — *B1 PR #46*
- [W2: 上下文与隔离] ✅ 工作流上下文按基础规则、角色目标、阶段目标、任务指令与前序摘要分层
组装，并按角色、阶段、任务类型选择性激活规则与记忆，而不是全量灌入 — *B4 PR #49, B5 PR #50*
- [W2: 上下文与隔离] ✅ 并行任务下，任务目录、工作区与状态查询边界清晰，切换任务时不会轻易
串线或相互污染 — *B6 PR #51*
- [持续治理，不阻塞 W1/W2] vision / plan / approval 的边界通过明确的阶段转移、批准点和
可查询状态表达，并持续支撑 roadmap / backlog / feedback 的治理闭环

### Non-Goals / Constraints

- 不复制 Claude Code 的完整产品面，不重建其完整权限平台、远程协议或 UI
- 不追求通用 AI IDE，而是服务 harness-flow 自身的 Cursor-native 工作流
- 不重新引入独立于 IDE 的自动化工作流引擎、常驻守护进程或第二套编排内核
- 不重做底层工具执行 runtime、通用 shell 层或通用 agent CLI 去替代 Cursor
- 借鉴的是上层方法：分层上下文、上下文压缩、模式化阶段控制、规则/记忆外置、结构化 handoff
artifact，而不是底层工具运行时
- handoff artifact 与规则/记忆注入默认视为半可信输入；消费侧应受 schema、allowlist 与门禁
约束，而不是只依赖模型自律
- 状态与门禁应保持单一真相源，并由单一的阶段转移权威维护，避免不同入口各自维护一套规则
- 不绑定 Claude Code 的具体 API、目录结构或内部子系统
- 优先落地高杠杆能力：状态、门禁、结构化 handoff、恢复；规则激活、workflow memory、
多任务隔离按波次推进
- 保持现有 skill / agent / rule / `.agents/tasks/` 体系兼容，避免一次性重写

## [2026-04-02] — W1 + W2 Vision Backlog Complete

B1–B6 全部交付，W1（单任务主干）和 W2（上下文与隔离）的核心 success signals 已通过：

| Backlog | 名称 | PR | 波次 |
|---------|------|-----|------|
| B1 | Canonical Workflow State Artifact | #46 | W1 |
| B2 | Structured Stage Handoff Contract | #48 | W1→W2 |
| B3 | Ship Gate Hardening | #47 | W1 |
| B4 | Layered Context Assembler + Selective Rule Activation | #49 | W2 |
| B5 | Workflow Memory Pack (Memverse integration) | #50 | W2 |
| B6 | Parallel Task Isolation + Worktree-Aware Status | #51 | W2 |

后续方向：持续治理闭环、B5 memory pack 深化、gate 自动拦截增强。

### Chosen Direction

继续让 Cursor 负责“执行”，而 harness-flow 负责“如何把任务上下文组织得更对”。第一波聚焦
单任务主干上的状态、门禁、恢复和 stage handoff artifact；第二波再增强分层上下文装配、
选择性规则/记忆注入与任务隔离；持续治理项则服务于 vision / roadmap / backlog / feedback
的长期闭环，但不阻塞前两波主干交付。我们吸收 Claude Code 在 context engineering 上的
方法论，但不把 harness-flow 演化成 Claude Code 的替代品或底层 runtime 克隆。