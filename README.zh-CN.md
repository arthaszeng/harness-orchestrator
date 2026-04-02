[English](README.md)

# harness-flow

> **Cursor 原生 AI 工程框架** — 在 Cursor 内完成计划、构建、评审、发布的完整流程，内置结构化质量门禁。
>
> 安装: `pip install harness-flow` · 导入: `import harness` · CLI: `harness`

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AI 编程工具擅长单次任务，但持续开发需要更多：目标跟踪、质量门禁、对抗评审、审计轨迹。Harness 将这些组织成契约驱动的工程闭环，**直接运行在 Cursor IDE 内** — 无需独立进程，无需复杂配置。

---

## 快速开始

### 1. 安装

```bash
pip install harness-flow
harness --version
```

<details>
<summary>从源码安装（贡献者）</summary>

```bash
git clone https://github.com/arthaszeng/harness-flow.git
cd harness-flow
pip install -e ".[dev]"
```

</details>

### 2. 初始化项目

```bash
cd /path/to/your/project
harness init
```

向导引导你完成配置：项目信息、主干分支、CI 命令、Memverse 集成和评估器模型。Skills、subagents 和 rules 直接生成到 `.cursor/` 目录。

### 3. 开始使用

在 Cursor 中打开项目。三个主要入口覆盖所有任务体量：

| 技能 | 何时用 | 功能 |
|------|--------|------|
| `/harness-brainstorm` | "我有个想法" | 发散探索 → 结构化 vision → roadmap/backlog → 迭代式构建/评审/发布循环 |
| `/harness-vision` | "我有个方向" | 澄清 vision → 计划 → 自动构建/评审/发布/回顾 |
| `/harness-plan` | "我有个需求" | 细化计划 + 5 角色审查 → 自动构建/评审/发布/回顾 |

当你需要长期方向、自主探索和连续推进时，用 `/harness-brainstorm`。
当你的方向已经清楚，只想先澄清一个增量愿景再继续规划和交付时，用 `/harness-vision`。
当你已经有一个明确任务，只想走单轮 plan → ship 时，用 `/harness-plan`。
这些入口仍共享愿景沉淀、多角色评审和 review → ship 等核心构件。

**工具类技能：**

| 技能 | 功能 |
|------|------|
| `/harness-investigate` | 系统化 bug 调查：复现 → 假设 → 验证 → 最小修复 |
| `/harness-learn` | Memverse 知识管理：存储、检索、更新项目经验 |
| `/harness-retro` | 工程回顾：提交分析、热点检测、趋势追踪 |

**管线技能**（细粒度控制）：

| 技能 | 功能 |
|------|------|
| `/harness-build` | 按契约实现，运行 CI，分流失败，输出结构化构建日志 |
| `/harness-eval` | 5 角色代码评审（架构师 + 产品负责人 + 工程师 + QA + 项目经理） |
| `/harness-ship` | 全自动流水线：测试 → 评审 → 修复 → 提交 → push → PR |
| `/harness-doc-release` | 文档同步：检测代码变更导致的文档过时 |

**现在就试试：**

```
/harness-plan 给用户注册接口添加输入校验
```

---

## 工作原理

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

### 5 角色评审系统

同一组 5 个专业角色同时审查**计划**和**代码**，全部并行调度：

| 角色 | 计划审查 | 代码评审 |
|------|---------|---------|
| **架构师** | 可行性、模块影响、依赖变更 | 架构合规性、分层、耦合、安全 |
| **产品负责人** | vision 对齐、用户价值、验收标准 | 需求覆盖、行为正确性 |
| **工程师** | 实现可行性、代码复用、技术债 | 代码质量、DRY、模式一致、性能 |
| **QA** | 测试策略、边界值、回归风险 | 测试覆盖、边界场景、CI 健康度 |
| **项目经理** | 任务分解、并行度、scope | scope 漂移、计划完成度、交付风险 |

被 2+ 角色发现的问题标注为**高置信度**。每个角色可通过 `[native.role_models]` 使用不同模型。若配置了无效模型，或本地 Cursor 状态里看不到该模型，生成 agent 模板时会自动回退到 IDE 默认模型，而不是把错误模型硬写进去。

### Fix-First 自动修复

评审发现在呈现前先分类：

- **AUTO-FIX** — 高确定性、影响面小、可逆。立即修复并提交。
- **ASK** — 安全发现、行为变更或低置信度。交由你决策。

---

## 配置

项目设置位于 `.agents/config.toml`：

| 键 | 默认值 | 说明 |
|-----|--------|------|
| `workflow.max_iterations` | 3 | 每任务最大评审迭代次数 |
| `workflow.pass_threshold` | 7.0 | 评审通过阈值（1-10） |
| `workflow.auto_merge` | true | 通过后自动合并分支 |
| `workflow.branch_prefix` | "agent" | 任务分支前缀 |
| `native.evaluator_model` | "inherit" | 5 个评审角色的默认偏好模型；若无效或本地不可用则回退到 IDE 默认模型 |
| `native.review_gate` | "eng" | 评审门禁（`eng` = 硬门禁，`advisory` = 仅记录） |
| `native.plan_review_gate` | "auto" | 计划审阅门控（`human` / `ai` / `auto`） |
| `native.gate_full_review_min` | 5 | 完整人工审查的升级分数阈值 |
| `native.gate_summary_confirm_min` | 3 | 摘要确认的升级分数阈值 |
| `native.retro_window_days` | 14 | 回顾分析窗口（天） |
| `native.role_models.*` | `{}` | 每角色模型覆盖；优先级高于 `native.evaluator_model`，但无效或本地不可用时同样回退到 IDE 默认模型 |

---

## 命令参考

| 命令 | 说明 |
|------|------|
| `harness init [--name] [--ci] [-y] [--force]` | 初始化项目（交互式向导）；`--force` 重新生成产物 |
| `harness status` | 显示当前任务进度 |
| `harness update [--check] [--force]` | 自更新，重装产物 |
| `harness --version` | 显示版本 |

---

## 仓库布局

```
harness-flow/
├── src/harness/
│   ├── cli.py              # CLI 入口（Typer）
│   ├── commands/            # init、update、status
│   ├── core/                # 配置、状态、UI、事件
│   ├── native/              # Cursor 原生产物生成器
│   ├── templates/           # Jinja2 模板
│   └── integrations/        # Git、Memverse
├── tests/
├── docs/
└── pyproject.toml
```

---

## 国际化

```bash
harness init --lang zh    # 中文
harness init --lang en    # 英文（默认）
```

---

## 开发

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
ruff format src/ tests/
```

---

## 历史文档

早期版本的架构说明（编排器模式、状态机、驱动兼容性）保存在 [`docs/historical.md`](docs/historical.md)。

---

## 许可

[MIT](LICENSE)
