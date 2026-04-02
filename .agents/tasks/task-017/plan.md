# Spec

> **[ARCHIVED]** 此计划的 B1–B6 backlog 已全部交付（PR #46–#51）。
> 以下 Analysis 描述的是立项时（2026-04-01）的现状，不是当前仓库状态。

## Analysis

当前 vision 已明确 `harness-flow` 的下一阶段不是重做一个通用 agent runtime，而是把
Cursor-native workflow intelligence 做实。就现状看，仓库里已经有几类互相割裂的状态与产物：

- `.agents/state.json` / `progress.md` 提供会话级摘要
- `.agents/tasks/task-NNN/plan.md`、`build-rN.log`、`evaluation-rN.*`、`ship-metrics.json`
  提供任务级产物
- `.agents/registry.db` 与 `.agents/runs/*/events.jsonl` 提供可查询/可审计的运行记录
- 生成的 `build / eval / ship / brainstorm` 技能已经约定了若干任务目录约束，但还没有统一的
  机器可读任务状态文件把这些产物、阶段转移、阻塞原因和门禁结果串起来

这导致 vision 中 W1 的几个核心信号还未落地：

1. 用户很难通过单一入口或约定产物看到任务当前处于哪一阶段、为什么被阻塞、下一步该做什么
2. `build / eval / ship` 虽然围绕 `task-NNN` 产物工作，但没有一个单一真相源表达
   “当前 active plan 是什么、哪些前置条件已经满足、哪项 gate 还缺失”
3. `status` 仍主要展示会话态，而不是面向 `task-NNN` 的工作流态；它对 build/eval/ship 的最新产物
   只做弱关联，没有显式表达阶段转移、门禁快照与恢复锚点
4. 现有 `SessionState` 与任务目录约定并存，容易让不同入口各写一套语义

因此，第一轮 active plan 最应该做的是建立 **任务级机器可读工作流状态** 及其最小消费面，让
`.agents/tasks/task-NNN/` 真正成为 W1 的单一真相源，再逐步把 handoff artifact、规则激活和
多任务隔离叠加上去。

## Roadmap

### Phase 1 — W1 / Canonical Task State

目标：把单任务主干上的阶段、门禁、阻塞原因和产物引用做成任务目录里的统一机器可读状态。

成功信号：
- `task-NNN` 下存在稳定、机器可读的工作流状态文件，能表达 phase、active plan、gates、blockers、
  artifact refs 与更新时间
- `harness status` 或任务目录中的约定产物能直接回答“现在在哪一阶段、缺什么、下一步是什么”
- 缺少 eval / build / gate 结论时，状态文件和消费方能给出明确阻塞原因
- 在中断或换会话后，只要 canonical state 存在，恢复入口仍能得到一致的阶段与下一步提示

停止 / 转向信号：
- 如果为了维护该状态需要引入第二套常驻协调器或复杂跨进程锁，则说明方案过重，应收窄
- 如果状态文件与现有 `SessionState`/registry/events 无法建立清晰主从关系，则需先回到契约层重构

### Phase 2 — W1 / Structured Handoff + Gate Hardening

目标：在 canonical state 之上，补齐阶段 handoff artifact 与 ship 前置门禁的可验证约束。

成功信号：
- plan/build/eval/ship 在任务目录下产出稳定 handoff artifact 或等价摘要引用
- ship 对缺失/过期的 eval、build、plan 结论有显式 gate，而不是只依赖 prompt 文案提醒
- 状态文件能引用最近一次 handoff 与 gate verdict，支持恢复与审计

停止 / 转向信号：
- 若 handoff 契约开始绑死模型实现细节而非工作流语义，应回退到更小的 schema
- 若 gate 硬化明显破坏现有单轮工作流可用性，需要拆成更小批次推进

### Phase 3 — W2 / Layered Context Compilation

目标：把阶段输入从“大段历史搬运”升级为基础前缀 + 阶段/角色增量 + 结构化前序摘要。

成功信号：
- 生成上下文能按基础规则、阶段目标、角色目标、任务指令、前序摘要分层组装
- 规则与记忆按角色/阶段/任务类型选择性注入，而不是全量灌入
- handoff artifact 成为默认上下文桥接，而不是 transcript 兜底

停止 / 转向信号：
- 若分层装配引入大量模板分叉而无明显收益，应先收敛 shared prefix 设计

### Phase 4 — W2 / Isolation, Memory, Driver Flexibility

目标：增强并行任务边界、workflow memory 与未来 driver abstraction 的兼容性。

成功信号：
- 并行 task/worktree 的状态查询与恢复不会轻易串线
- 仓库级 workflow memory 可复用常见命令、失败模式、review rubric
- 上下文/状态 contract 不把系统锁死在单一 driver 上

停止 / 转向信号：
- 若多任务隔离或 driver abstraction 开始主导全部实现复杂度，应延后到 W1 收敛后再做

## Plan Backlog

### B1 — Canonical Workflow State Artifact

- 用户问题：用户无法通过单一入口看清任务当前 phase、缺失产物、阻塞原因和下一步动作
- 为什么现在做：这是 W1 的最小基础；没有它，后续 handoff、gate、恢复和 status 都只能继续拼接弱信号
- 预计推进的 success signals：W1 状态可查询、W1 阻塞原因清晰、W1 中断恢复锚点
- 依赖：现有 `.agents/tasks/task-NNN/*` 约定；`SessionState` / `status` / templates 现状
- 风险：与 `SessionState` 双写；schema 过早复杂化
- 状态：`DONE` — PR #46

### B2 — Structured Stage Handoff Contract

- 用户问题：阶段之间仍容易依赖 transcript 和长日志搬运上下文
- 为什么现在值得做：是 W1 到 W2 的桥梁，也是 phase 2 gate hardening 的数据基础
- 预计推进的 success signals：W1 handoff artifact、W2 layered context
- 依赖：B1 提供 canonical refs
- 风险：把 handoff 写成提示词碎片而非稳定 contract
- 状态：`DONE` — PR #48

### B3 — Ship Gate Hardening Against Missing/Stale Artifacts

- 用户问题：`ship` 虽有检查，但对“当前 diff 是否有新鲜 eval/build 结论”的表达仍偏分散
- 为什么现在值得做：能直接降低“漏 eval / 漏验证 / 带旧结论继续 ship”的风险
- 预计推进的 success signals：W1 ship gate、W1 blocker visibility
- 依赖：B1；B2 最好有但不是强依赖
- 风险：对现有 ship 流程过于激进，造成误阻塞
- 状态：`DONE` — PR #47

### B4 — Layered Context Assembler + Selective Rule Activation

- 用户问题：上下文容易过长、重复、信噪比差
- 为什么现在值得做：是 Claude Code 报告中最值得借鉴的上层方法，但不属于当前最小闭环
- 预计推进的 success signals：W2 layered context / selective activation
- 依赖：B2 的 handoff contract
- 风险：模板和生成上下文同时大改，blast radius 较大
- 状态：`DONE` — PR #49

### B5 — Workflow Memory Pack

- 用户问题：仓库常见命令、常见失败模式和评审习惯没有稳定复用载体
- 为什么现在值得做：可提升后续阶段输入质量，但没有 B1/B2/B3 紧急
- 预计推进的 success signals：W2 rule/memory injection
- 依赖：B4 更完整，但也可局部先做
- 风险：与通用聊天记忆混淆，边界不清
- 状态：`DONE` — PR #50

### B6 — Parallel Task Isolation + Worktree-Aware Status

- 用户问题：多任务/并行 worktree 下状态、任务目录、恢复点仍可能串线
- 为什么现在值得做：vision 已明确这是 W2 重点，但目前单任务 W1 价值更高
- 预计推进的 success signals：W2 isolation
- 依赖：B1 的 canonical state contract
- 风险：在 W1 未稳定前并发建模过重
- 状态：`DONE` — PR #51

## Active Plan

### Selected Backlog Item

`B1 — Canonical Workflow State Artifact`

### Why This Plan Now

它是 vision 里 W1 的最小可验证切口，也是后续 B2/B3/B4 的共同基础。相比直接先做 handoff 或
规则激活，先建立任务级单一真相源能更快回答用户最痛的几个问题：当前在哪里、为什么卡住、缺什么、
接下来该做什么。

### Targeted Success Signals

- [W1] 用户可通过统一状态入口或约定产物看到最小状态、阻塞原因与阶段转移
- [W1] `ship` 前置条件的缺口可以被显式表达为 blocker（本轮只做可见性与快照，不做执行层硬拦）
- [W1] 单任务上下文下的恢复锚点更清晰

### Plan Scope

只做 **canonical task state + 最小消费面**，不在本轮同时实现完整 handoff artifact、完整 gate
硬化、多任务隔离或 workflow memory。特别地，本轮只把 `ship` 缺口表达为 blocker / gate snapshot，
不把缺口升级成真正的执行层硬阻断；完整 hardening 归属 B3。

---

## Approach

采用“**任务目录为真相源，SessionState 为兼容/摘要层**”的路径，分四个交付物推进：

1. **建立 canonical task state schema 与 Python 读写层**
   在 `.agents/tasks/task-NNN/` 下新增稳定机器可读文件（暂定 `workflow-state.json`），字段覆盖：
   - `schema_version`
   - `task_id`, `branch`, `phase`, `iteration`
   - `active_plan` 摘要（id/title）
   - `artifacts` 引用（plan/build/eval/feedback/ship）
   - `gates` 快照（plan review / eval / ship readiness）
   - `blocker`（kind/reason）
   - `updated_at`
   Python 侧新增统一的 load/save/locate helpers，并明确它是任务级权威；`.agents/state.json`
   保留为会话摘要与兼容层，不再作为唯一 workflow SSOT。`.agents/registry.db` 与
   `.agents/runs/*/events.jsonl` 仅用于运行元数据与审计，不参与 workflow phase/gate 的权威判定；
   若需要可追溯性，canonical state 只允许引用它们的 id/path，而不复制 gate 逻辑。

2. **让 `harness status` 与 `progress` 优先消费任务级状态**
   更新 `status.py` / `progress.py`，优先读取最近任务目录中的 canonical state，并展示：
   - 当前阶段
   - 当前 active plan
   - 缺失 gate / blocker reason
   - 最近关键 artifact 引用
   - 推荐下一步动作
   若 state 文件不存在，则回退到现有 `SessionState` 路径，保证向后兼容。任务发现规则在本轮中
   明确为：`显式 task id > SessionState.current_task.id（若目录存在） > 数值最大的 task-NNN`；
   生成的技能协议与 Python helper 必须使用同一确定性规则。

3. **把 plan / build / eval / ship 的关键阶段转移接入 canonical state**
   更新相关技能模板，使其在写 `plan.md`、`build-rN.log`、`evaluation-rN.*`、`ship-metrics.json`
   等现有产物时，也同步更新或要求更新 canonical state 的 phase、artifacts 与 gate 快照。
   本轮只覆盖主干四条技能链与对应 zh 镜像，不扩展到完整 brainstorm loop 文案重构。
   重点不是把所有逻辑搬进 Python，而是让生成的 workflow 协议围绕同一份任务级状态文件协作。

4. **补齐测试与兼容性保护**
   新增/更新测试覆盖：
   - canonical state schema 的 round-trip 与默认值
   - 非法 JSON、缺字段、未知 `schema_version`、异常值等 fail-closed 解析与降级
   - 最近 task 目录 / 最新 state 的发现逻辑，以及 `SessionState` 与 task 目录并存时的优先级
   - `harness status` 在有/无 canonical state 时的输出，并至少通过一次 CLI 入口集成断言
   - 生成后的 skill 文案在 en/zh 下都明确引用 canonical state 作为任务级真相源
   - 旧项目在没有新文件时仍能 fallback 到现有 `SessionState`

### Rejected Alternatives

- 继续把 `.agents/state.json` 当唯一状态源：它偏会话态，不适合表达任务目录中的 gate/artifact 事实
- 完全不改 Python、只改 prompt：无法给 `harness status` 提供真实的统一查询面
- 一次把 handoff / gate / isolation / memory 全做掉：范围过大，难以形成第一波可验证反馈
- 直接做多任务/并发隔离：价值高但不如先把单任务 W1 真相源稳定下来

## Impact

预计影响文件：

- `src/harness/core/state.py`
- `src/harness/core/progress.py`
- `src/harness/commands/status.py`
- `src/harness/core/` 下新增 workflow-state 相关模块
- `src/harness/templates/native/skill-plan.md.j2`
- `src/harness/templates/native/skill-build.md.j2`
- `src/harness/templates/native/skill-eval.md.j2`
- `src/harness/templates/native/skill-ship.md.j2`
- `src/harness/templates/native/zh/skill-plan.md.j2`
- `src/harness/templates/native/zh/skill-build.md.j2`
- `src/harness/templates/native/zh/skill-eval.md.j2`
- `src/harness/templates/native/zh/skill-ship.md.j2`
- `src/harness/templates/native/sections/_plan-core.md.j2`
- `src/harness/templates/native/sections/_review-gate.md.j2`（若需引用 canonical gate snapshot）
- `tests/` 中状态/生成/CLI 覆盖文件
- `ARCHITECTURE.md`

允许新增一个与任务级 workflow state 相关的核心模块，但不应引入外部服务、数据库迁移或长期后台进程。

## Risks

1. **双写风险**
   若 `SessionState` 与 `workflow-state.json` 都被当作权威，会出现语义漂移。
   缓解：在 contract 中明确任务级 state 为 canonical，SessionState 为摘要/兼容层。

2. **schema 过早复杂化**
   若第一版 state 文件试图覆盖所有未来 W2 需求，会让实现和迁移都过重。
   缓解：仅纳入 W1 需要的 phase/gate/blocker/artifact refs；将 handoff 细节延后到 B2。

3. **模板与 Python 更新不同步**
   若 status 依赖新文件，但 workflow 模板未稳定写入，会造成“Python 期待有，技能实际不写”。
   缓解：测试中覆盖生成后的模板引用与 fallback 行为。

4. **过度硬化 gate**
   若本轮直接把 ship gate 做成严格阻断，可能破坏现有 flow。
   缓解：本轮只提供 blocker 表达与最小 gate snapshot，完整 hardening 放在 B3。

5. **旧任务兼容性**
   旧 `task-NNN` 目录没有 canonical state 文件。
   缓解：CLI/status 必须 fallback；生成物需允许在文件缺失时给出指导而不是崩溃。

---

# Contract

## Deliverables

- [x] D1：定义 canonical task workflow state schema 与读写 helpers
  验收标准：任务目录下存在稳定机器可读状态文件；schema 至少覆盖 task id、phase、iteration、
  active plan、artifact refs、gate snapshot、blocker、updated_at；Python 侧具备 load/save/find-latest
  能力，并能在文件缺失时安全 fallback。解析必须 fail-closed：对非法 JSON、缺字段、未知
  `schema_version` 或异常值降级处理，不把未校验内容当作 gate/合并依据。

- [x] D2：`harness status` / `progress` 优先展示任务级 workflow state
  验收标准：在存在 canonical state 时，`status` 能显示 phase、blocker、active plan、关键产物引用；
  在不存在时回退到现有 `SessionState` 路径且无回归。中断或换会话后，只要 canonical state 仍在，
  `status` 或约定产物给出的恢复/续作提示必须与该 state 一致。

- [x] D3：plan / build / eval / ship 生成物围绕 canonical state 协作
  验收标准：相关技能模板明确把任务级 state 作为单一真相源或明确更新目标；至少覆盖
  plan/build/eval/ship 的关键阶段转移与 gate/blocker 快照，不要求本轮实现完整 handoff artifact。
  渲染后的 en/zh 技能正文必须能被自动化断言检测到对 `workflow-state.json`（或最终命名）的引用
  及其更新义务。

- [x] D4：补齐自动化测试与兼容性断言
  验收标准：新增/更新测试至少覆盖 schema round-trip、损坏 state 降级、task discovery 数值排序规则、
  canonical 与 `SessionState` 不一致时的权威优先级、旧任务目录 fallback、CLI 入口下的 `harness status`
  集成断言、`progress` 共享渲染核心或等价烟雾断言、en/zh 模板生成引用；`python -m pytest tests/ -v` 通过。

## Acceptance Criteria

- 单任务 W1 路径上存在一个稳定、任务级、机器可读的 workflow state 文件
- `harness status` 或任务目录中的约定产物可以回答“当前阶段 / blocker / active plan / 下一步”，而不是只展示会话摘要
- 生成的 `plan / build / eval / ship` 协议围绕同一任务级状态协作
- 旧任务目录在缺少新文件时不会导致 CLI 或生成逻辑崩溃
- 没有引入独立守护进程、第二套 runtime、数据库迁移或外部服务依赖
- 现有 `.agents/tasks/task-NNN/` 产物体系继续有效，并与新状态文件协同
- `workflow-state.json` 是 phase/gate/blocker/artifact refs 的唯一权威来源；`SessionState`、
  registry、events 只能作为摘要、兼容或审计来源，不得平行判定 workflow gate
- 本轮只兑现 blocker / gate snapshot 的可见性，不把 ship 缺口升级成执行层硬阻断

## Out of Scope

- 完整的 stage handoff artifact contract（B2）
- 完整 ship gate hardening 与 freshness enforcement（B3）
- 规则/记忆的分层激活系统（B4/B5）
- 多任务/多 worktree 隔离与 driver abstraction（B6）
- 重写 `harness-ship`/`harness-eval` 的全部执行协议
- 引入外部数据库、守护进程或后台自动调度

## Stop Conditions

- 发现 canonical state 无法与现有 task artifact / SessionState 建立明确主从关系
- 为了维护状态一致性必须引入跨进程协调器或复杂锁服务
- `status`/templates 的兼容成本高到需要同时重写多个工作流入口
- 5 角色评审指出该 active plan 实际已经越过 W1 边界并侵入 W2/B2/B3
- D3 的模板面超出主干四条技能链，或开始要求重写 brainstorm / handoff 语义

## Implementation Order

1. 先定义 task-level state contract 与 Python helper
2. 再接 `status` / `progress` 读取路径与 fallback
3. 再更新 plan/build/eval/ship 模板的状态引用和阶段转移
4. 最后补测试并用 review gate 检查范围是否仍停留在 W1/B1
5. 若 D3 在时间盒内仍明显过宽，优先保住 D1+D2+D4，并把额外模板扩展降级到 follow-up backlog

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected Alternative |
|---|-------|----------|---------------|-----------|-----------|---------------------|
| 1 | Backlog | 先做 B1 canonical state，而不是直接做 handoff/gate/isolation | Mechanical | #3 务实 | 先建立 W1 最小闭环与单一真相源 | 直接推进 B2/B3/B6 |
| 2 | Architecture | 任务目录状态为 canonical，SessionState 为摘要/兼容层 | Taste | #5 显式优于巧妙 | 让任务级事实落在 `.agents/tasks/`，与现有 artifact 同层 | 继续以 `.agents/state.json` 作为唯一来源 |
| 3 | Scope | 本轮只纳入 phase/gate/blocker/artifact refs，不纳入完整 handoff payload | Mechanical | #4 DRY | 控制 schema 复杂度，给 B2 留清晰边界 | 一次把未来 handoff 细节全塞进 state |
| 4 | Delivery | Python 查询面与模板协议同步推进 | Mechanical | #1 选择完整性 | 只改一边会留下半拉子系统 | 仅改 Python 或仅改 prompt |
| 5 | Risk | 对旧任务目录保持 fallback，而不是强制迁移 | Mechanical | #3 务实 | 降低回归面，先让新旧共存 | 强制一次性迁移所有历史任务 |

## Plan Review Summary

### Round 1

- Architecture: 8/10
- Product: 8/10
- Engineering: 7/10
- Testing: 8/10
- Delivery: 8.5/10
- Weighted avg: 7.9/10
- Verdict: `PLAN_NEEDS_REVISION`

主要修订项：
- 明确 `workflow-state.json` 是 phase/gate/blocker/artifact refs 的唯一权威来源
- 明确 `registry/events` 仅用于审计与元数据，不参与 workflow gate 判定
- 写死 task discovery 规则，并要求技能协议与 Python helper 一致
- 把 D3 收窄到 `plan/build/eval/ship` 主干四条技能链
- 把恢复锚点、坏 state 降级、CLI 集成与 en/zh 模板引用检测写入验收与测试要求

### Round 2

- Architecture: 9/10
- Product: 9/10
- Engineering: 9/10
- Testing: 9/10
- Delivery: 9/10
- Weighted avg: 9.0/10
- Verdict: `PLAN_APPROVED`

收敛说明：
- Canonical state 与 `SessionState` / registry / events 的主从边界已明确
- B1 与 B3 的预期差异已在 scope、risks、acceptance 与 feedback ledger 中对齐
- D3 已收窄到主干四条技能链，并补上时间盒降级路径
- task discovery 与 fail-closed 解析要求已写死，测试覆盖更接近真实风险

Review Gate:
- Interaction depth: `high`
- Deliverables: `4`
- Estimated file impact: `12`
- Risk flags: `none`
- Aggregate review score: `9.0/10`
- Gate score: `1`
- Result: `Plan auto-approved (gate score 1, aggregate review score 9.0/10)`
