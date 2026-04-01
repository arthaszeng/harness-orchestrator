[English](README.md)

# harness-orchestrator

> 契约驱动的多智能体开发框架 — 在 Cursor 内一条命令完成 计划-构建-评审-发布 全流程。

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AI 编程工具擅长单次任务，但持续开发需要更多：目标跟踪、质量门禁、对抗评审、审计轨迹。Harness 将这些组织成契约驱动的工程闭环，**直接运行在 Cursor IDE 内** — 无需独立编排进程，无需复杂配置。对于 CI/CD 和无头自动化场景，可选的[编排器模式](#进阶跨客户端编排器模式)通过外部 CLI 驱动 Cursor 和 Codex agent。

## 快速开始（Cursor 原生模式，3 分钟上手）

### 1. 安装 harness

```bash
git clone https://github.com/arthaszeng/harness-orchestrator.git
cd harness-orchestrator
./install.sh        # 或: pip install -e .
harness --version   # 验证（也可用: python3 -m harness --version）
```

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

在 Cursor 中打开项目，你现在拥有四个技能：

| 技能 | 功能 |
|-------|-------------|
| `/harness-plan` | 分析需求，产出 spec 和契约，含对抗式评审 |
| `/harness-build` | 按契约实现，运行 CI，分流失败，输出结构化构建日志 |
| `/harness-eval` | 三通道对抗代码评审（Claude + Claude 对抗 + GPT 跨模型） |
| `/harness-ship` | **一条命令走完全流程**：计划 → 构建 → 评审 → 修复 → 提交 → push → PR |

**现在就试试** — 打开 Cursor 聊天窗口，输入：

```
/harness-ship 给用户注册接口添加输入校验
```

Harness 会规划工作、实现代码、跑三通道对抗评审、自动修复琐碎问题、创建可二分提交并开 PR — 全程不离开 IDE。

---

## 背后发生了什么

```
你输入 /harness-ship "添加功能 X"
  → Rebase 到 main，运行测试
  → 三通道对抗评审：
      第一通道：Claude 结构化评审（4 个维度）
      第二通道：Claude 对抗子代理（攻击面）
      第三通道：GPT 跨模型评审（独立视角）
  → Fix-First：自动修复琐碎问题，重要问题询问你
  → 可二分提交 + push + PR
```

### 三通道对抗评审

每次代码变更经过三个独立审查者：

1. **结构化评审** — Claude 在完整性、质量、回归、设计四个维度评分
2. **Claude 对抗** — 全新上下文的 Claude 子代理搜寻安全漏洞、竞态条件、边界场景、资源泄漏
3. **GPT 跨模型** — 基于 GPT 的审查器（默认 `gpt-4.1`）从不同模型族提供独立视角

第二、三通道并行调度以加速。被 2+ 通道发现的问题标注为**高置信度**。对抗模型可在 `.agents/config.toml` 中配置。

### Fix-First 自动修复

评审发现在呈现前先分类：

- **AUTO-FIX** — 高确定性、影响面小、可逆。立即修复并提交。
- **ASK** — 安全发现、行为变更或低置信度。交由你决策。

琐碎问题不阻断发布，重要决策始终由人类判断。

### 优雅降级

| 第一通道（结构化） | 第二通道（Claude） | 第三通道（GPT） | 行为 |
|---------------------|-----------------|---------------|----------|
| 正常 | 正常 | 正常 | 完整三通道综合 |
| 正常 | 正常 | 失败 | 双通道，标记 `[claude-only]` |
| 正常 | 失败 | 正常 | 双通道，无 Claude 子代理 |
| 正常 | 失败 | 失败 | 单审查器模式 |
| 失败 | — | — | 致命 — 无法评估 |

---

## 生成的工件

选择 cursor-native 模式后，`harness init` 会生成：

| 工件 | 路径 | 用途 |
|----------|------|---------|
| `/harness-plan` | `.cursor/skills/harness/harness-plan/SKILL.md` | 规划与拆解任务，含对抗式 spec 评审 |
| `/harness-build` | `.cursor/skills/harness/harness-build/SKILL.md` | 构建：按契约实现、运行 CI、分流失败 |
| `/harness-eval` | `.cursor/skills/harness/harness-eval/SKILL.md` | 三通道评审 + Fix-First 自动修复 |
| `/harness-ship` | `.cursor/skills/harness/harness-ship/SKILL.md` | 全自动流水线：测试 → 评审 → 修复 → 提交 → PR |
| 对抗审查器 | `.cursor/agents/harness-adversarial-reviewer.md` | 跨模型代码审查器（模型可配置，`readonly: true`） |
| 评估器 | `.cursor/agents/harness-evaluator.md` | 结构化评估器，JSON 输出（`readonly: true`） |
| 信任边界 | `.cursor/rules/harness-trust-boundary.mdc` | 始终生效：Builder 产出视为不可信 |
| Fix-First | `.cursor/rules/harness-fix-first.mdc` | 始终生效：发现先分类再呈现 |
| 工作流约定 | `.cursor/rules/harness-workflow.mdc` | 提交格式、分支命名、任务状态 |

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
| `workflow.pass_threshold` | 3.5 | 评审通过阈值（满分 5） |
| `workflow.auto_merge` | true | 通过后自动合并分支 |
| `workflow.dual_evaluation` | false | 质量评审后再跑对齐评审 |
| `workflow.branch_prefix` | "agent" | 任务分支前缀 |
| `native.adversarial_model` | "gpt-4.1" | 跨模型审查器模型 |
| `native.adversarial_mechanism` | "auto" | 对抗评审调度：`subagent` / `cli` / `auto` |
| `native.review_gate` | "eng" | 哪些评审层为硬门禁 |
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
| **入口** | `harness run` / `harness auto` | `/harness-plan`、`/harness-build`、`/harness-eval`、`/harness-ship` |
| **跨模型评审** | 按角色配置 | 对抗子代理使用不同模型 |
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
      → 通过（≥ 3.5）→ 完成
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

Ruff 面向 Python 3.9，行宽 100。

---

## 延伸阅读

| 文档 | 说明 |
|-----|-------------|
| [docs/zh-CN/state-machine.md](docs/zh-CN/state-machine.md) | 任务状态机 |
| [docs/zh-CN/compatibility.md](docs/zh-CN/compatibility.md) | CLI 版本要求 |
| [examples/todo-api-benchmark/](examples/todo-api-benchmark/) | 基准：五个任务，三种模式 |

---

## 许可

[MIT](LICENSE)
