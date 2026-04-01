[English](README.md)

# harness-orchestrator

> 契约驱动的多智能体开发框架 — 在 Cursor 内一条命令完成 计划-构建-评审-发布 全流程。

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AI 编程工具擅长单次任务，但持续开发需要更多：目标跟踪、质量门禁、对抗评审、审计轨迹。Harness 将这些组织成契约驱动的工程闭环，**直接运行在 Cursor IDE 内** — 无需独立编排进程，无需复杂配置。对于 CI/CD 和无头自动化场景，可选的[编排器模式](#进阶跨客户端编排器模式)通过外部 CLI 驱动 Cursor 和 Codex agent。

## 快速开始（Cursor 原生模式，3 分钟上手）

### 1. 安装 harness

```bash
pip install harness-orchestrator
harness --version   # 验证（也可用: python3 -m harness --version）
```

<details>
<summary>备选：从源码安装（面向贡献者）</summary>

```bash
git clone https://github.com/arthaszeng/harness-orchestrator.git
cd harness-orchestrator
pip install -e ".[dev]"
```

</details>

### 2. 初始化你的项目

```bash
cd /path/to/your/project
harness init
```

向导会引导你完成配置。当询问 **工作流模式** 时，选择 **cursor-native**：

```
Step 5/9  工作流模式
  请选择工作流模式（cursor-native 模式无需 Cursor CLI）：
  1. orchestrator -- 外部 CLI 进程驱动 cursor-agent（默认）
  2. cursor-native -- 在 Cursor IDE 内通过 skills + subagents 驱动（无需外部进程）
  选择 [2]: 2
  → cursor-native 模式：将生成 skills、subagents 和 rules
```

这会将 skills、subagents 和 rules 直接生成到你的 `.cursor/` 目录。

### 3. 在 Cursor 中使用

在 Cursor 中打开项目。你现在拥有 **三个主要入口**，覆盖从模糊想法到具体需求的所有任务体量：

**从这里开始 — 三个入口覆盖所有任务体量：**

| 技能 | 何时用 | 功能 |
|-------|-------------|------|
| `/harness-brainstorm` | "我有个想法" | 发散探索 → vision → 计划 → 审阅门控 → 自动构建/评审/发布/回顾 |
| `/harness-vision` | "我有个方向" | 澄清 vision → 计划 → 审阅门控 → 自动构建/评审/发布/回顾 |
| `/harness-plan` | "我有个需求" | 细化计划 + 5 角色审查 → 审阅门控 → 自动构建/评审/发布/回顾 |

三个入口采用递归组合（brainstorm ⊃ vision ⊃ plan），共享同一计划审查 → ship 管线。计划批准后，`/harness-ship` 处理构建 → 评审 → 迭代 → 发布 → PR。

**工具类技能：**

| 技能 | 功能 |
|-------|-------------|
| `/harness-investigate` | 系统化 bug 调查：复现 → 假设 → 验证 → 最小修复 |
| `/harness-learn` | Memverse 知识管理：存储、检索、更新项目经验 |
| `/harness-retro` | 工程回顾：提交分析、热点检测、趋势追踪 |

**高级技能**（细粒度控制）：

| 技能 | 功能 |
|-------|-------------|
| `/harness-build` | 按契约实现，运行 CI，分流失败，输出结构化构建日志 |
| `/harness-eval` | 5 角色代码评审（架构师 + 产品负责人 + 工程师 + QA + 项目经理） |
| `/harness-ship` | 全自动流水线：测试 → 评审 → 修复 → 提交 → push → PR |
| `/harness-doc-release` | 文档同步：检测代码变更导致的文档过时 |

**现在就试试** — 打开 Cursor 聊天窗口，输入：

```
/harness-plan 给用户注册接口添加输入校验
```

Harness 会生成计划并 5 角色审查、应用审阅门控、构建、5 角色代码评审、自动修复琐碎问题、创建可二分提交并开 PR — 全程不离开 IDE。

### 更新

```bash
harness update          # 升级到最新版，重装 agent，检查配置
harness update --check  # 仅检查是否有新版本
```

---

## 背后发生了什么

```
你输入 /harness-ship "添加功能 X"
  → Rebase 到 main，运行测试
  → 5 角色代码评审（全部并行调度）：
      架构师：      设计 + 安全评审
      产品负责人：  完整性 + 行为正确性
      工程师：      质量 + 性能
      QA：          回归 + 测试（唯一运行 CI 的角色）
      项目经理：    scope + 交付
  → Fix-First：自动修复琐碎问题，重要问题询问你
  → 可二分提交 + push + PR
```

### 统一 5 角色评审系统

同一组 5 个专业角色同时审查**计划**和**代码**，全部并行调度：

| 角色 | 计划审查关注点 | 代码评审关注点 |
|------|---------------|---------------|
| **架构师** | 可行性、模块影响、依赖变更 | 架构合规性、分层、耦合、安全 |
| **产品负责人** | vision 对齐、用户价值、验收标准 | 需求覆盖、行为正确性 |
| **工程师** | 实现可行性、代码复用、技术债 | 代码质量、DRY、模式一致、性能 |
| **QA** | 测试策略、边界值、回归风险 | 测试覆盖、边界场景、CI 健康度 |
| **项目经理** | 任务分解、并行度、scope | scope 漂移、计划完成度、交付风险 |

被 2+ 角色发现的问题标注为**高置信度**。每个角色可通过 `.agents/config.toml` 中的 `[native.role_models]` 使用不同模型。

### Fix-First 自动修复

评审发现在呈现前先分类：

- **AUTO-FIX** — 高确定性、影响面小、可逆。立即修复并提交。
- **ASK** — 安全发现、行为变更或低置信度。交由你决策。

琐碎问题不阻断发布，重要决策始终由人类判断。

### 优雅降级

| 响应角色数 | 行为 |
|-----------|------|
| 5/5 | 完整综合 + 交叉验证 |
| 3-4/5 | 使用可用评审继续，标注缺失视角 |
| 1-2/5 | 记录警告，降级到单 agent 评审 |
| 0/5 | 回退到单个 generalPurpose 子代理 |

---

## 生成的工件

选择 cursor-native 模式后，`harness init` 会生成：

| 工件 | 路径 | 用途 |
|----------|------|---------|
| `/harness-brainstorm` | `.cursor/skills/harness/harness-brainstorm/SKILL.md` | 发散探索 → vision → 计划 → 自动执行到 PR |
| `/harness-vision` | `.cursor/skills/harness/harness-vision/SKILL.md` | 澄清 vision → 计划 → 自动执行到 PR |
| `/harness-plan` | `.cursor/skills/harness/harness-plan/SKILL.md` | 细化计划 + 5 角色审查 → 自动执行到 PR |
| `/harness-build` | `.cursor/skills/harness/harness-build/SKILL.md` | 构建：按契约实现、运行 CI、分流失败 |
| `/harness-eval` | `.cursor/skills/harness/harness-eval/SKILL.md` | 5 角色代码评审 + Fix-First 自动修复 |
| `/harness-ship` | `.cursor/skills/harness/harness-ship/SKILL.md` | 全自动流水线：测试 → 5 角色评审 → 修复 → 提交 → PR |
| `/harness-investigate` | `.cursor/skills/harness/harness-investigate/SKILL.md` | 系统化 bug 调查与最小修复 |
| `/harness-learn` | `.cursor/skills/harness/harness-learn/SKILL.md` | Memverse 知识管理 |
| `/harness-doc-release` | `.cursor/skills/harness/harness-doc-release/SKILL.md` | 代码变更后文档同步 |
| `/harness-retro` | `.cursor/skills/harness/harness-retro/SKILL.md` | 工程回顾与趋势分析 |
| 架构师 | `.cursor/agents/harness-architect.md` | 架构评审器（计划 + 代码双模式） |
| 产品负责人 | `.cursor/agents/harness-product-owner.md` | 产品评审器（计划 + 代码双模式） |
| 工程师 | `.cursor/agents/harness-engineer.md` | 工程评审器（计划 + 代码双模式） |
| QA | `.cursor/agents/harness-qa.md` | QA 评审器，CI 唯一执行者（计划 + 代码双模式） |
| 项目经理 | `.cursor/agents/harness-project-manager.md` | 交付评审器（计划 + 代码双模式） |
| 信任边界 | `.cursor/rules/harness-trust-boundary.mdc` | 始终生效：Builder 产出视为不可信 |
| Fix-First | `.cursor/rules/harness-fix-first.mdc` | 始终生效：发现先分类再呈现 |
| 工作流约定 | `.cursor/rules/harness-workflow.mdc` | 提交格式、分支命名、任务状态 |
| 安全护栏 | `.cursor/rules/harness-safety-guardrails.mdc` | 始终生效：破坏性命令检测与警告 |

更新配置后重新生成：

```bash
harness install --force
```

---

## 配置

项目设置位于 `.agents/config.toml`：

| 键 | 默认值 | 说明 |
|-----|---------|-------------|
| `workflow.mode` | "orchestrator" | `orchestrator` 或 `cursor-native` |
| `workflow.profile` | "standard" | `lite` / `standard` / `autonomous` |
| `workflow.max_iterations` | 3 | 每任务最大迭代次数 |
| `workflow.pass_threshold` | 7.0 | 评审通过阈值（满分 10） |
| `workflow.auto_merge` | true | 通过后自动合并分支 |
| `workflow.dual_evaluation` | false | 质量评审后再跑对齐评审 |
| `workflow.branch_prefix` | "agent" | 任务分支前缀 |
| `native.gate_full_review_min` | 5 | 完整人工审查的升级分数阈值 |
| `native.gate_summary_confirm_min` | 3 | 摘要确认的升级分数阈值 |
| `native.adversarial_model` | "gpt-4.1" | 跨模型审查器模型 |
| `native.adversarial_mechanism` | "auto" | 对抗评审调度模式。允许值：`subagent`、`cli`、`auto` |
| `native.review_gate` | "eng" | 评审门禁严格度。允许值：`eng`（硬门禁）、`advisory`（仅记录） |
| `native.plan_review_gate` | "auto" | 计划审阅门控模式。允许值：`human`（始终暂停）、`ai`（自动批准）、`auto`（复杂度自适应） |
| `native.retro_window_days` | 14 | 回顾分析默认时间窗口（天数，1–365） |
| `native.role_models.*` | `{}` | 每角色模型覆盖。键：`architect`、`product_owner`、`engineer`、`qa`、`project_manager` |
| `autonomous.max_tasks_per_session` | 10 | 每自主会话最大任务数 |
| `autonomous.consecutive_block_limit` | 2 | 连续阻塞达到此次数后停止 |

### 模型（可选）

在 `[models]` 下为不同角色配置模型。仅当解析结果非空时传递 `--model`。

**优先级**：`role_overrides.<角色>` → `driver_defaults.<驱动>` → `models.default` → 空。

```toml
[models]
default = ""

[models.driver_defaults]
# codex = "o3"
# cursor = "claude-4-opus"

[models.role_overrides]
# planner = "o3-pro"
# builder = ""  # 显式指定始终不传模型参数
```

### 工作流配置

| 配置 | 流程 | 适用场景 |
|---------|------|-------------|
| **lite** | planner → builder → eval（无 spec/contract 拆分；阈值 3.0；最多 2 轮） | 小改动、快速修复 |
| **standard** | planner → spec + contract → builder → eval（完整评审） | 日常开发（默认） |
| **autonomous** | strategist → standard 循环 → reflector | 基于 vision 的自主开发 |

---

## 任务工件

所有工件位于项目根目录的 `.agents/` 下：

```
.agents/
├── config.toml            # 项目配置
├── vision.md              # 项目 vision
├── state.json             # 运行时状态
├── .stop                  # 停止信号
├── runs/
│   └── <session-id>/
│       └── events.jsonl   # 结构化事件
├── tasks/
│   └── task-001/
│       ├── spec-r1.md     # Spec：分析与技术方案
│       ├── contract-r1.md # 契约（Markdown）
│       ├── contract-r1.json # 契约（JSON sidecar）
│       ├── evaluation-r1.md # 评审（Markdown）
│       ├── evaluation-r1.json # 评审（JSON sidecar）
│       ├── alignment-r1.md # 对齐评审（如开启 dual_evaluation）
│       ├── build-r1.log   # 构建日志
│       └── ...
└── archive/               # 归档会话
```

每一步可追溯。JSON sidecar 适合自动化与 UI，无需正则解析 Markdown。

**本地优先**：所有状态保留在磁盘，无云依赖。`.agents/` 树通常 gitignore。如需团队共享 `config.toml` 或 `vision.md`，使用 `git add -f .agents/config.toml`。

---

## 命令参考

| 命令 | 说明 |
|---------|-------------|
| `harness install [--force] [--lang]` | 安装 agent 定义到本地 IDE |
| `harness init [--name] [--ci] [--lang] [-y]` | 初始化项目配置（交互式向导） |
| `harness vision` | 创建或更新项目 vision |
| `harness run <需求> [--resume] [--verbose]` | 运行单次开发任务 |
| `harness auto [--resume] [--verbose]` | 启动自主开发循环 |
| `harness status` | 显示当前进度 |
| `harness stop` | 优雅停止当前任务 |
| `harness --version` | 显示版本 |

---

## 进阶：跨客户端编排器模式

Cursor 原生模式覆盖了大部分交互式开发场景。对于 **CI/CD 流水线**、**无头自动化**或**多 IDE 混合**（Cursor + Codex）场景，使用编排器模式。

### 前置条件

| 依赖 | 要求 | 说明 |
|------------|-------------|-------|
| **Python** | >= 3.9 | 运行 Harness CLI |
| **Cursor CLI 和/或 Codex CLI** | 至少其一 | 提供 agent 能力 |
| **Git** | 任意版本 | 项目须为 Git 仓库 |

IDE CLI 配置：

- **Cursor**：命令面板 → `Install 'cursor' command`
- **Codex**：`npm install -g @openai/codex` 或从 [GitHub](https://github.com/openai/codex) 安装

### 编排器 vs Cursor 原生

|  | 编排器模式 | Cursor 原生模式 |
|---|---|---|
| **运行方式** | 外部 `harness` CLI 生成 agent 进程 | Cursor IDE 内 skill + 子代理 |
| **入口** | `harness run` / `harness auto` | `/harness-brainstorm`、`/harness-vision`、`/harness-plan` |
| **跨模型评审** | 按角色配置 | 5 角色并行评审，支持 `native.role_models` 按角色指定模型 |
| **适用场景** | CI/CD、无头自动化、多 IDE | 交互式开发、纯 Cursor 工作流 |

### 角色架构

| 角色 | 职责 | `auto` 下默认后端 |
|------|----------------|-------------------------------|
| **Planner** | 分析需求；产出 spec 与契约 | Codex |
| **Builder** | 按契约实现；提交变更 | Cursor |
| **Evaluator** | 独立评审；四维评分 | Codex |
| **Alignment Evaluator** | 需求对齐与意图漂移检测 | Codex |
| **Strategist** | 自主模式下选取下一任务 | Codex |
| **Reflector** | 提炼经验到长期记忆 | Codex/Cursor |

各角色后端可在 `[drivers.roles]` 下独立配置。CLI 版本要求见 [docs/zh-CN/compatibility.md](docs/zh-CN/compatibility.md)。

### 编排器配置

```bash
# 1. 安装 agent 定义到 IDE 目录
harness install

# 2. 初始化（选择 "orchestrator" 模式）
cd /path/to/your/project
harness init

# 3. 创建项目 vision
harness vision

# 4. 运行
harness run "添加用户认证"    # 单任务
harness auto                  # 自主循环

# 5. 监控
harness status
harness stop
```

### 单任务流程（`harness run`）

```
需求
  → Planner：spec + 迭代契约
  → Builder：实现并提交
  → Evaluator：四维评分
      → 通过（≥ 7.0）→ 完成
      → 不通过 → 反馈给 Builder，迭代
  → 最大迭代（3）→ 阻塞
```

### 自主循环（`harness auto`）

```
Vision
  → Strategist：选取下一任务
  → 单任务流程
  → Reflector：提炼经验
  → 循环直到：全部完成 / 停止信号 / 阻塞上限 / 任务上限
```

### 双评审器

当 `workflow.dual_evaluation = true` 时，质量评审后再跑对齐评审：

- **质量** — 代码质量 + 回归（四维评分）
- **对齐** — 需求覆盖 + 契约契合 + 意图漂移

若对齐返回 `MISALIGNED`，任务迭代回 Builder。若 `CONTRACT_ISSUE`，反馈发给 Planner 修订契约。

```toml
[workflow]
dual_evaluation = true
```

---

## 排错

### 恢复中断的工作

```bash
harness run "原始需求" --resume
harness auto --resume
```

`--resume` 从 `state.json` 恢复并从中断阶段继续。

### 停止行为

`harness stop` 写入 `.agents/.stop`。任务在完成当前阶段后干净退出。立即中止用 `Ctrl+C` — Harness 会保存检查点。

### 未找到 IDE CLI

出现 `Neither Cursor nor Codex CLI detected` 时：

- **Cursor**：命令面板 → `Install 'cursor' command`
- **Codex**：`npm install -g @openai/codex`

确保二进制在 PATH 中。Cursor 原生模式下，Cursor CLI 是可选的 — harness 生成的文件直接在 IDE 内工作。

### 重新安装

如果 `harness install` 失败或安装异常：

```bash
harness install --force
```

会覆盖已有文件、重试 CLI 安装并重新生成原生工件。

---

## 可观测性

每个会话将结构化事件写入 `.agents/runs/<session-id>/events.jsonl`：

```json
{"ts": "2026-03-31T10:00:00.000Z", "event": "agent_end", "role": "planner", "driver": "codex", "exit_code": 0, "elapsed_ms": 12340}
```

事件类型：`agent_start`/`agent_end`、`ci_result`、`state_transition`、`task_start`/`task_end`。

---

## 仓库布局

```
harness-orchestrator/
├── src/harness/
│   ├── cli.py              # CLI 入口（Typer）
│   ├── commands/            # 子命令实现
│   ├── orchestrator/        # 工作流核心
│   ├── drivers/             # IDE agent 调用抽象
│   ├── core/                # 状态、配置、UI、事件
│   ├── methodology/         # 评审、评分、契约
│   ├── native/              # Cursor 原生模式生成器
│   ├── agents/              # 角色定义（Cursor / Codex）
│   ├── templates/           # 提示模板（编排器 + 原生）
│   └── integrations/        # Git、Memverse
├── tests/                   # 测试套件
├── docs/                    # 状态机、兼容性
└── pyproject.toml
```

---

## 适用与不适用

**适合：**

- 使用 Cursor，希望对 agent 输出有质量门禁而非单次盲信
- 希望在多步工作中保持可追溯性
- 希望对抗评审捕获单次评审遗漏的问题

**不适合：**

- 期望一键「全自动做完整个产品」
- 与编码无关的企业审批流程
- 无法安装 Python 或任何支持的 agent CLI（Cursor/Codex）的环境

---

## 国际化

```bash
harness init --lang zh    # 中文
harness init --lang en    # 英文（默认）
```

影响 CLI 消息、agent 提示、生成文件和安装的 agent 定义。存储在 `.agents/config.toml` 的 `[project] lang` 中。

---

## 开发

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
ruff format src/ tests/
```

Ruff 面向 Python 3.9，行宽 100。发布流程参见 [docs/releasing.md](docs/releasing.md)。

---

## 延伸阅读

| 文档 | 说明 |
|-----|-------------|
| [docs/zh-CN/state-machine.md](docs/zh-CN/state-machine.md) | 任务状态机 |
| [docs/zh-CN/compatibility.md](docs/zh-CN/compatibility.md) | CLI 版本要求 |
| [docs/releasing.md](docs/releasing.md) | 发布流程和 PyPI 发布 |
| [examples/todo-api-benchmark/](examples/todo-api-benchmark/) | 基准：五个任务，三种模式 |

---

## 许可

[MIT](LICENSE)
