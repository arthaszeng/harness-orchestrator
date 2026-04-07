# Spec

## Analysis

本任务是 **vision 对齐审计**：逐条比对 `.harness-flow/vision.md` 中的全部承诺（4 个 vision 板块 + Roadmap A × 3 phases + Roadmap B × 4 phases）与实际代码/产物/文档的交付状态，找出已交付、部分交付和未交付的缺口，并对缺口给出补齐方案或标记为 deferred。

### 方法

以 vision.md 中的每个 **Success Signal** 和 **Chosen Direction 要点** 为审计单元，判定：

- **DONE** — 代码/文档/测试完备，满足信号描述
- **PARTIAL** — 核心机制已交付但有可衡量遗漏
- **NOT STARTED** — 无对应实现
- **DEFERRED** — 明确属于更远期（90 天里程碑 M3 或更远）

## Vision 对照矩阵

### 1. As-Is Vision Baseline (2026-04-06)


| #   | 承诺                           | 状态       | 证据/缺口                                                                                                   |
| --- | ---------------------------- | -------- | ------------------------------------------------------------------------------------------------------- |
| 1.1 | 清晰入口：brainstorm/vision/plan  | **DONE** | 10 个 SKILL 目录；README 表格区分默认/进阶入口                                                                        |
| 1.2 | 结构化状态与可验证结果（预检、分支、评审门禁、产物落盘） | **DONE** | `git-preflight --json`、`workflow-state.json`、`save-eval`、`gate` CLI 全部落地；task 目录包含 plan/eval/handoff 产物 |
| 1.3 | 问题在评审阶段暴露                    | **DONE** | 5 角色 plan-review + code-eval + Fix-First 自动修复全链路可运行                                                     |


### 2. To-Be Vision（合理想象版）


| #   | 承诺                                                    | 状态          | 证据/缺口                                                                                                                                                    |
| --- | ----------------------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2.1 | Roadmap/Plan Backlog/Active Plan/Feedback Ledger 形成闭环 | **PARTIAL** | Feedback Ledger 已有 `feedback_ledger.py`，但无 UI 命令查看/操作 ledger；Roadmap 目前手动维护在 vision.md，无 CLI 管理。Plan Backlog 仅由 brainstorm SKILL 隐式管理，无持久化 backlog 文件格式。 |
| 2.2 | Gate 升级为"是否值得继续投入"的决策支持                               | **PARTIAL** | `gate` 命令已有 `--force` / 通过门禁；但缺少"建议停止"信号——当前 gate 只是 PASS/FAIL，无 ROI 或投入产出比信号。                                                                           |
| 2.3 | 文档、记忆与交付产物自动同步                                        | **PARTIAL** | `harness-doc-release` SKILL 存在且可用；Memverse 集成已有。但 doc-release 未自动在 ship 后触发（依赖用户手动或 workflow 规则提示）。                                                      |
| 2.4 | 信任来自可观测结果                                             | **PARTIAL** | 审计轨迹完整（task 目录 + eval 产物），但缺乏跨任务的趋势仪表盘（retro 可做但无自动化汇总视图）。                                                                                               |


### 3. 高效易用智能加速（用户共创版）


| #   | 承诺             | 状态          | 证据/缺口                                                                                     |
| --- | -------------- | ----------- | ----------------------------------------------------------------------------------------- |
| 3.1 | e2e 平均执行时间持续下降 | **PARTIAL** | A1 ship fast-path 减少重复预检；A2 context 裁剪减少 token。但无自动度量采集（无 timer/metric 在 workflow 中记录耗时）。 |
| 3.2 | e2e 一次通过率提升    | **PARTIAL** | Fix-First 自动修复 + 结构化恢复文案已落地。但无通过率统计机制。                                                    |
| 3.3 | 人工介入率下降        | **PARTIAL** | Review gate auto-pass/summary-confirm 已实现分级门禁。intervention_audit.py 存在。但无跨任务聚合报告。         |
| 3.4 | 评审分数分布拉开       | **PARTIAL** | `score_calibration.py` 已存在但内容仅为初始 helper。无校准数据或区间定义。                                      |


### 4. Vision 完整化（执行版）


| #   | 承诺                                | 状态          | 证据/缺口                                                                        |
| --- | --------------------------------- | ----------- | ---------------------------------------------------------------------------- |
| 4.1 | Onboarding：十分钟级首次体验               | **DONE**    | `init --non-interactive` + `scan_project` 自动检测 CI；README 双语 quick start 路径完整 |
| 4.2 | Delivery Reliability：失败集中在可自动修复问题 | **DONE**    | Fix-First heuristic + recovery hints i18n + `workflow next` 恢复文案             |
| 4.3 | Intervention Cost：人工介入收敛到高价值决策点   | **PARTIAL** | gate 分级 + auto-pass 已实现，但无度量数据                                               |
| 4.4 | Decision Quality：评审分数有区分度         | **PARTIAL** | 同 3.4                                                                        |


### 5. 连贯性与效率（工程底盘升级）


| #   | 承诺                     | 状态       | 证据/缺口                                                                                     |
| --- | ---------------------- | -------- | ----------------------------------------------------------------------------------------- |
| 5.1 | plan→ship 同会话衔接不触发重复预检 | **DONE** | ship fast-path 基于 `workflow-state.json` phase 判断跳过预检（task-019/A1）                         |
| 5.2 | 框架强制结构化进度输出            | **DONE** | `_workflow-progress-envelope.md.j2` 模板注入所有 SKILL；`HARNESS_PROGRESS` 格式在模板中强制（task-020/A2） |
| 5.3 | 子 agent 按角色裁剪上下文       | **DONE** | SKILL 模板中 Task 协议/事实分离、Context 最小化表格（task-020/A2）                                         |
| 5.4 | 中断恢复从磁盘产物重建上下文         | **DONE** | `handoff-plan.json` schema v2 + `load_latest_handoff` + `context_footprint`（task-021/A3）  |


### 6. 产品表达层收敛（用户界面升级）


| #   | 承诺           | 状态       | 证据/缺口                                                                                                            |
| --- | ------------ | -------- | ---------------------------------------------------------------------------------------------------------------- |
| 6.1 | 一条默认主线       | **DONE** | `/harness-plan` 定位为默认入口；README 首推 plan，brainstorm/vision 降为进阶（task-022/B1）                                       |
| 6.2 | 用任务语言替代框架语言  | **DONE** | `status` 默认人话输出 + `--verbose` 显示技术细节；`gate` 输出任务语言；i18n workflow.phase 映射（task-023/B2）                           |
| 6.3 | 围绕"下一步"的状态反馈 | **DONE** | `harness status --progress-line`、`harness workflow next`、恢复文案 i18n（task-024 + task-025/B3）                       |
| 6.4 | 10 分钟首次成功    | **DONE** | `init --non-interactive` + `_default_ci_for_non_interactive` + `scan_project`；README 10-minute path（task-025/B4） |


### Roadmap A 总结


| Phase      | 状态       | 核心任务     |
| ---------- | -------- | -------- |
| A1：流程连贯性   | **DONE** | task-019 |
| A2：指令与角色精度 | **DONE** | task-020 |
| A3：上下文复用   | **DONE** | task-021 |


### Roadmap B 总结


| Phase   | 状态       | 核心任务                |
| ------- | -------- | ------------------- |
| B1：默认主线 | **DONE** | task-022            |
| B2：任务语言 | **DONE** | task-023            |
| B3：状态反馈 | **DONE** | task-024 + task-025 |
| B4：首次上手 | **DONE** | task-025            |


### Milestones (Next 90 Days) 对照


| 里程碑       | 状态          | 说明                                                                                                                                         |
| --------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| M1（可用性基线） | **DONE**    | 主路径文档 + 入口收敛 + 单会话最小闭环                                                                                                                     |
| M2（稳定性基线） | **DONE**    | 高频人工补偿点自动化（fast-path、auto-pass gate、Fix-First、recovery hints）                                                                              |
| M3（智能性基线） | **PARTIAL** | `score_calibration.py` 已有校准工具（repeat penalty、dispersion）但缺分数→决策建议的区间分类；feedback ledger 有存储无 CLI 查阅；retro 可手动运行但无自动趋势。本任务完成 GAP-1 后 M3 部分达成 |


---

## 缺口清单

以下是未完全交付的承诺，按优先级排列：

### GAP-1：评审分数区间语义（Score Band）— M3 核心

- **vision 承诺**：评审分数分布拉开，能区分"可发布""需迭代""需重做"
- **当前状态**：`score_calibration.py` 已有 `normalize_finding_signature`、`apply_repeat_penalty`、`score_dispersion` 等校准工具，但**缺少分数→决策建议的区间分类（ScoreBand）**和 gate 消费链路
- **补齐方案**：在 `score_calibration.py` 增量添加 `ScoreBand` enum + `classify_score`；在 `gates.py` 增加 `parse_eval_aggregate_score` 解析综合分；在 `commands/gate.py` 渲染区间文案
- **区间定义**：`[8.0, 10.0] → SHIP`、`[6.0, 8.0) → ITERATE`、`[0.0, 6.0) → REDO`
- **解析契约**：从最新 code-eval-rN.md 中匹配 `Weighted avg:` 或 `**Average** | **X.X/10`** 行提取浮点分数；解析失败或无分数时静默不展示区间文案（advisory 语义，不构成第二套硬门禁）
- **输入健壮性**：`classify_score` 先 `float() + math.isfinite` 校验，非有限值返回 `None`；有限值 clamp 到 `[0, 10]` 再分档
- **影响范围**：`score_calibration.py`、`gates.py`、`commands/gate.py`、i18n
- **优先级**：HIGH — 直接影响 Decision Quality 信号

### GAP-2：Feedback Ledger CLI — M3 辅助

- **vision 承诺**：反馈回路形成闭环
- **当前状态**：`feedback_ledger.py` 有 save/load 但无 CLI 命令
- **补齐方案**：添加 `harness feedback list [--task TASK]` 和 `harness feedback add` CLI 命令
- **影响范围**：`cli.py`、新 `commands/feedback.py`
- **优先级**：MEDIUM — 增强可观测性但非核心通路

### GAP-3：度量采集基础设施 — To-Be Vision 支撑

- **vision 承诺**：e2e 时间、通过率、介入率可度量
- **当前状态**：无自动 timer/metric 记录
- **补齐方案**：在 workflow-state.json 中添加 `started_at`/`completed_at` 时间戳；`harness retro` 基于时间戳计算 e2e 时间
- **影响范围**：`workflow_state.py`、`retro` SKILL
- **优先级**：MEDIUM — 度量是持续改进的基础但不阻塞当前功能

### GAP-4：doc-release 自动触发 — 自动同步

- **vision 承诺**：文档、记忆与产物自动同步
- **当前状态**：doc-release 需手动调用
- **补齐方案**：在 ship SKILL 的尾部添加 doc-release 自动触发提示或直接集成
- **影响范围**：ship SKILL 模板
- **优先级**：LOW — 已有能力只是缺少自动触发

### GAP-5：Backlog 持久化格式 — To-Be Vision

- **vision 承诺**：Plan Backlog 形成稳定闭环
- **当前状态**：brainstorm SKILL 产出 backlog 但无统一文件格式
- **补齐方案**：定义 `.harness-flow/backlog.md` 或 `.harness-flow/backlog.json` 规范
- **影响范围**：brainstorm/vision SKILL
- **优先级**：LOW — 重度用户需求，非首次体验关键

---

## Approach

本次任务分两阶段：

1. **审计报告**（本 plan.md）— 已完成
2. **核心缺口补齐**（GAP-1 分数区间语义）— 阻塞 M3 里程碑的区间分类部分；feedback CLI 留后续

GAP-2~5 标记为 deferred，可作为后续独立任务。

对 GAP-1 的实现方案（分层：core 解析 → core 分类 → commands 渲染）：

1. `**score_calibration.py`（增量）**：
  - 新增 `ScoreBand` enum（SHIP/ITERATE/REDO）
  - 新增 `classify_score(score: float) -> ScoreBand | None`：先 `float() + math.isfinite` 校验，非有限值返回 `None`；有限值 clamp 到 `[0, 10]`，再按闭开区间分档：`[8.0, 10.0] → SHIP`、`[6.0, 8.0) → ITERATE`、`[0.0, 6.0) → REDO`
  - 阈值使用模块级常量 `SHIP_THRESHOLD = 8.0`、`ITERATE_THRESHOLD = 6.0`，注释标注未来可配置
2. `**gates.py`（增量）**：
  - 新增 `parse_eval_aggregate_score(content: str) -> float | None`：匹配 `Weighted avg:` 或 `**Average** | **X.X/10`** 或 `Weighted Average:` 行，提取浮点数；无匹配或解析失败返回 `None`
  - `GateVerdict` 增加可选字段 `score_band: ScoreBand | None = None` 和 `aggregate_score: float | None = None`
  - `check_ship_readiness` 中，当读取 eval 内容后调用 `parse_eval_aggregate_score` 和 `classify_score`，结果挂到 verdict
3. `**commands/gate.py`（渲染层）**：
  - 当 `verdict.score_band` 非 `None` 时，追加一行区间文案：`t('score_band.{band.value}')` 格式化分数
  - ScoreBand 是 **advisory 语义**——不构成第二套硬门禁，与 `EvalVerdict` PASS/ITERATE 独立
4. **i18n**：en.py + zh.py 新增 `score_band.ship`、`score_band.iterate`、`score_band.redo` 描述性文案
5. **测试**：
  - `test_score_calibration.py`：参数化单测覆盖 `classify_score` 边界（8.0→SHIP、7.9→ITERATE、6.0→ITERATE、5.9→REDO、0.0→REDO、10.0→SHIP）和 `None`/`NaN`/`inf`/负数
  - `test_score_calibration.py`：`parse_eval_aggregate_score` 多种 markdown 格式
  - `test_gates.py` 或 `test_cli.py`：至少 1 条 CLI 窄集成测试验证 gate 输出包含区间文案

## Impact

- 修改文件：`core/score_calibration.py`、`core/gates.py`、`commands/gate.py`、`i18n/en.py`、`i18n/zh.py`
- 新增文件：`tests/test_score_calibration.py`
- 预计 ~7 个文件，影响范围小

## Risks

- 区间阈值选择是品味决策，需基于实际评分分布调整
  - 缓解：首版使用硬编码常量（SHIP_THRESHOLD=8.0、ITERATE_THRESHOLD=6.0），注释标注扩展点，config 可覆盖留后续
- eval 产物中综合分格式可能随模板演进漂移
  - 缓解：`parse_eval_aggregate_score` 支持多种 markdown 格式且解析失败静默降级（不输出区间文案）

---

# Contract

## Deliverables

- D1：Vision 对照审计矩阵（本文档上半部分）— AC：每个 vision 板块的每条承诺有明确 DONE/PARTIAL/NOT STARTED 状态
- D2：Score Band 核心实现 — AC：`classify_score` 函数按闭开区间 `[8,10]/[6,8)/[0,6)` 返回 SHIP/ITERATE/REDO/None；`parse_eval_aggregate_score` 从 eval markdown 提取综合分
- D3：Gate 集成 — AC：`GateVerdict` 包含 `score_band` 和 `aggregate_score`；`commands/gate.py` 当分数可用时输出 advisory 区间文案
- D4：i18n score_band 键 — AC：en.py 和 zh.py 均包含 `score_band.ship`、`score_band.iterate`、`score_band.redo` 及描述
- D5：测试覆盖 — AC：参数化单测覆盖 `classify_score` 边界 + 极端值 + `parse_eval_aggregate_score` 多格式 + 至少 1 条 CLI 窄集成测试

## Acceptance Criteria

- 所有测试通过（`python -m pytest tests/ -v`）
- `harness gate` 在有分数时输出区间文案
- 审计矩阵准确反映当前代码状态

## Out of Scope

- GAP-2~5（feedback CLI、度量采集、doc-release 自动触发、backlog 格式）— 标记为 deferred
- 分数阈值的 config 可覆盖（留作后续增强）

## Decision Audit Trail


| #   | Phase    | Decision                                        | Classification   | Principle      | Rationale                             | Rejected Alternative               |
| --- | -------- | ----------------------------------------------- | ---------------- | -------------- | ------------------------------------- | ---------------------------------- |
| 1   | Approach | 只补 GAP-1（区间分类），M3 里程碑标记为"部分达成"                  | Mechanical       | #4 DRY / #3 务实 | GAP-1 是 M3 的核心信号缺口；feedback CLI 独立且不急 | 一次性补全所有缺口 — 范围膨胀                   |
| 2   | Approach | 区间阈值 `[8,10] SHIP / [6,8) ITERATE / [0,6) REDO` | [TASTE DECISION] | #1 完整性         | 基于 5 角色评审实际分布，8 分以上多为可直接发布            | 更细粒度（5 档）— 增加复杂度无明显收益              |
| 3   | Approach | 分层 core 解析 → core 分类 → commands 渲染              | Mechanical       | #5 显式 > 巧妙     | 与 task-023 确立的 CLI→commands→core 分层一致 | 全部逻辑放 commands/gate.py — 违背分层约定    |
| 4   | Approach | ScoreBand 为 advisory 语义，不构成第二套硬门禁               | Mechanical       | #6 偏向行动        | 避免 ScoreBand 与 EvalVerdict 语义冲突       | 用 ScoreBand 替换 EvalVerdict — 破坏性变更 |
| 5   | Review   | 首版硬编码阈值常量，config 留后续                            | Mechanical       | #3 务实          | Risks 与 OoS 统一表述                      | 首版就做 config — 范围膨胀                 |


---

## Plan Review Summary

### Round 1

5 角色并行评审（Architect 7/10、Product Owner 7.5/10、Engineer 7/10、QA 7/10、PM 8.5/10）。
Weighted avg: 7.4/10。裁定：PLAN_NEEDS_REVISION（C1 CRITICAL）。

核心发现与处置：


| #   | 簇                            | 严重程度                       | 处置                                                         |
| --- | ---------------------------- | -------------------------- | ---------------------------------------------------------- |
| C1  | score_calibration.py 现状描述不准确 | [HIGH CONFIDENCE] CRITICAL | **已修正**：改为"增量添加 ScoreBand/classify_score"                  |
| C2  | 分数解析契约未定义                    | [HIGH CONFIDENCE] WARN     | **已修正**：Approach 中新增 `parse_eval_aggregate_score` 规格和支持的格式 |
| C3  | 边界区间未显式定义                    | [HIGH CONFIDENCE] WARN     | **已修正**：写明闭开区间 `[8,10]/[6,8)/[0,6)` + 输入健壮性                |
| C4  | ScoreBand 与 EvalVerdict 并存   | WARN                       | **已修正**：Decision #4 明确 advisory 语义                         |
| C5  | M3 应标"部分达成"                  | WARN                       | **已修正**：里程碑对照和 Decision #1 更新                              |
| C6  | 测试需 CLI 集成测试                 | WARN                       | **已修正**：D5 AC 含 CLI 窄集成测试                                  |
| C7  | Risks/OoS 矛盾                 | WARN                       | **已修正**：Decision #5 统一为首版硬编码                               |
| C8  | deferred GAP 跟踪锚点            | INFO                       | **已记录**：ship 后在 vision.md M3 段补充                           |


修订后裁定：**PLAN_APPROVED**（所有 CRITICAL/WARN 已处置）