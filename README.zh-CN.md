[English](README.md)

# harness-orchestrator

> 面向 Cursor 与 Codex 的契约驱动多智能体自主开发编排框架。

[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

今天的 AI 编程工具擅长单次任务，但持续开发往往受目标漂移、上下文断裂、质量门禁缺失与过程不透明所困。harness-orchestrator 将多种 agent 能力组织成契约驱动、可审计、可恢复的工程闭环：

- **需求按方法论推进** — Planner 分析需求产出 spec 并协商迭代契约，而不是直接跳到写代码
- **实现与审查分离** — Builder 按契约实现；Evaluator 独立审查，以四维评分作为质量门禁
- **自主但有边界** — Strategist 从 vision 中选任务，受迭代上限、通过阈值与停止信号约束
- **全程可追溯** — 每轮迭代的 spec、contract、evaluation 以 Markdown + JSON 保存，便于审计、自动化与中断后恢复
- **可观测** — 每次 agent 调用、CI 运行与状态变更都记录为结构化事件（`events.jsonl`），便于诊断与度量

> **设计思路**：核心架构受 GAN 对抗思想启发 — Builder（生成器）与 Evaluator（判别器）分离并迭代博弈，推动代码质量收敛；Planner 通过契约协议为双方建立共同基线。

## 快速开始

### 前置条件

| 依赖 | 要求 | 说明 |
|------------|-------------|-------|
| **Python** | >= 3.9 | 运行 Harness CLI |
| **Cursor CLI 和/或 Codex CLI** | 至少其一 | 提供实际 agent 能力 |
| **Git** | 任意版本 | 项目须为 Git 仓库；Harness 依赖 Git 做分支与变更跟踪 |

IDE CLI 配置：

- **Cursor**：在 Cursor → 命令面板 → `Install 'cursor' command`，确保 `cursor` 在 PATH 中
- **Codex**：通过 npm 或从 [GitHub](https://github.com/openai/codex) 安装，确保 `codex` 在 PATH 中

> `auto` 模式下的默认路由是**可替换的经验默认**（Builder→Cursor，其余角色→Codex）。这不是 Harness 的核心价值 — 核心资产是契约协议、评审量表、状态机、工件链与中断恢复。可在 `.agents/config.toml` 中为每个角色配置驱动。若只安装一种 CLI，所有角色都会经由该驱动执行。

### 安装

```bash
git clone https://github.com/arthaszeng/harness-orchestrator.git
cd harness-orchestrator
pip install -e .
```

验证：

```bash
harness --version
# harness-orchestrator 1.0.0
```

### 五步上手

```bash
# 1. 将 agent 定义安装到本地 IDE
harness install

# 2. 在项目中初始化配置
cd /path/to/your/project
harness init

# 3. 创建项目 vision
harness vision

# 4. 运行工作（任选其一）
harness run "add user authentication"   # 单任务模式
harness auto                            # 自主模式

# 5. 查看进度 / 停止
harness status
harness stop
```

下文展开每一步。

---

## 初始化与配置

### harness install

将角色定义文件安装到本地 IDE 目录（`~/.cursor/agents/` 和/或 `~/.codex/agents/`）。Harness 会检测已安装的 IDE，仅安装匹配的 agent 文件。使用 `--force` 可覆盖已有定义。

### harness init

在当前项目中启动交互式向导，共六步：

1. **项目信息** — 名称与描述
2. **IDE 环境** — 检测 Cursor/Codex，并可选择安装 agent 定义
3. **驱动模式** — 选择 auto（推荐：Builder→Cursor，其余→Codex）、cursor 或 codex
4. **CI 门禁** — 配置质量检查命令，可选 AI 建议
5. **Memverse 集成** — 可选启用长期记忆，在反思阶段持久化关键决策
6. **Vision** — 立即生成或稍后编辑

初始化后，项目根目录会创建 `.agents/`：

| 生成文件 | 用途 |
|----------------|---------|
| `.agents/config.toml` | 项目配置：驱动模式、CI 命令、工作流参数等 |
| `.agents/vision.md` | 项目 vision（若在向导中选择生成） |
| `.agents/state.json` | 运行时状态（首次任务运行时创建；建议加入 `.gitignore`） |

使用 `--non-interactive` 跳过向导并使用默认值：

```bash
harness init --name my-project --ci "make test" -y
```

### harness vision

与 Advisor agent 交互式问答，将简短描述扩展为结构化 vision 文档并写入 `.agents/vision.md`。Vision 是自主模式下 Strategist 选取任务的主要输入。也可直接编辑该文件。

---

## 核心工作流

### 角色架构

| 角色 | 职责 | `auto` 下默认后端 |
|------|----------------|----------------------------|
| **Planner** | 分析需求；产出 spec 与迭代契约 | Codex |
| **Builder** | 按契约实现；提交变更 | Cursor |
| **Evaluator** | 独立审查；四维评分（完整性 / 质量 / 回归 / 设计）；通过或迭代 | Codex |
| **Alignment Evaluator** | 需求对齐：契约契合、需求覆盖、意图漂移检测（需 `dual_evaluation`） | Codex |
| **Strategist** | 自主模式下，从 vision 与进度中选择下一任务 | Codex |
| **Reflector** | 任务结束后，将经验提炼为长期记忆 | Codex/Cursor |

**Advisor** 角色支持 `harness vision` 以及 `harness init` 期间的 AI 辅助分析。

> 各角色后端可在 `[drivers.roles]` 下独立配置。上表反映 `auto` 模式偏好，非硬绑定。CLI 版本要求见 [docs/zh-CN/compatibility.md](docs/zh-CN/compatibility.md)。

### 单任务流程（`harness run`）

```
User provides requirement
  → Planner: produce spec (analysis, technical approach, impact, risks)
  → Planner: negotiate iterative contract (deliverables, acceptance criteria, complexity)
  → Builder: implement per contract and commit
  → Evaluator: independent review, four-dimensional score
      → Score ≥ threshold (default 3.5) → PASS, task done
      → Score < threshold → feedback to Builder, next iteration
  → Max iterations (default 3) reached without pass → task blocked
```

### 自主循环（`harness auto`）

```
Read .agents/vision.md
  → Strategist: pick next task from vision and current progress
  → Run single-task flow (as above)
  → Reflector: distill this round's lessons
  → Loop until:
      - All tasks complete
      - Stop signal (harness stop)
      - Consecutive block limit (default 2)
      - Per-session task limit (default 10)
```

### 选择 `run` 与 `auto`

|  | `harness run` | `harness auto` |
|---|---|---|
| **适用场景** | 需求明确；完成一块工作 | 已有 vision，希望 Strategist 拆解任务 |
| **任务来源** | 命令行 | Strategist 从 vision 与进度选取 |
| **范围** | 单任务的 plan→build→eval 循环 | 跨多任务的持续循环 |
| **前置条件** | 已完成 `init` | `init` + `vision` |
| **如何停止** | 任务完成或达最大迭代 | 手动 `harness stop`、全部任务完成或安全阀 |

两种模式均支持 `--resume`（从中断处继续）与 `--verbose`（完整 agent 输出）。

---

## 命令参考

| 命令 | 说明 |
|---------|-------------|
| `harness install [--force / -f] [--lang / -l]` | 将 agent 定义安装到本地 IDE（Cursor / Codex） |
| `harness init [--name / -n NAME] [--ci CMD] [--lang / -l] [--non-interactive / -y]` | 在当前项目中初始化 harness 配置（交互式向导） |
| `harness vision` | 交互式创建或更新项目 vision（.agents/vision.md） |
| `harness run <requirement> [--resume / -r] [--verbose / -V]` | 运行单次开发任务 |
| `harness auto [--resume / -r] [--verbose / -V]` | 启动自主开发循环 |
| `harness status` | 显示当前进度与状态 |
| `harness stop` | 优雅停止当前运行中的任务 |
| `harness --version / -v` | 显示版本并退出 |

### 主要选项

- **`--resume / -r`** — 从 `state.json` 恢复上次会话，从中断阶段继续而非重头开始。用于异常退出或终端关闭后。
- **`--verbose / -V`** — 打印完整 agent 输入/输出以便调试。默认关闭以保持输出简洁。
- **`--force / -f`**（install）— 覆盖已安装的 agent 定义文件（例如升级后）。
- **`--lang / -l`**（init、install）— 提示与 agent 定义语言：`en`（默认）或 `zh`。install 省略时会回退到项目配置或 UI 语言。
- **`--non-interactive / -y`**（init）— 跳过向导并使用默认值。可与 `--name`、`--ci` 组合指定项目名与 CI 命令。

---

## 配置

项目设置位于 `.agents/config.toml`。重要键：

| 键 | 默认值 | 说明 |
|-----|---------|-------------|
| `workflow.profile` | "standard" | 工作流配置：`lite` / `standard` / `autonomous`（见下） |
| `workflow.max_iterations` | 3 | 每任务最大迭代次数 |
| `workflow.pass_threshold` | 3.5 | Evaluator 通过阈值（满分 5） |
| `workflow.auto_merge` | true | 通过后自动合并分支 |
| `workflow.branch_prefix` | "agent" | 任务分支前缀 |
| `workflow.dual_evaluation` | false | 双评审：质量评审后再跑对齐评审 |
| `autonomous.max_tasks_per_session` | 10 | 每自主会话最大任务数 |
| `autonomous.consecutive_block_limit` | 2 | 连续阻塞达到此次数后停止 |

### 工作流配置

| 配置 | 流程 | 适用场景 |
|---------|------|-------------|
| **lite** | planner → builder → eval（无 spec/contract 拆分；阈值上限 3.0；最多 2 轮） | 小改动、快速修复、探针 |
| **standard** | planner → spec + contract → builder → eval（完整四维评审） | 日常开发（默认） |
| **autonomous** | strategist → standard 循环 → reflector | 基于 vision 的自主开发 |

在 `.agents/config.toml` 中设置：

```toml
[workflow]
profile = "lite"  # or "standard" / "autonomous"
```

---

## 任务工件

Harness 在项目根目录的 `.agents/` 下保存所有工件：

```
.agents/
├── config.toml            # Project config (harness init)
├── vision.md              # Vision (harness vision)
├── state.json             # Runtime state
├── .stop                  # Stop signal (harness stop; cleared when the task ends)
├── runs/
│   └── <session-id>/
│       └── events.jsonl   # Structured events (agent calls, CI, state transitions)
├── tasks/
│   └── task-001/
│       ├── spec-r1.md     # Round 1 spec: analysis and technical plan
│       ├── contract-r1.md # Round 1 contract (Markdown)
│       ├── contract-r1.json # Round 1 contract (JSON sidecar, machine-friendly)
│       ├── evaluation-r1.md # Round 1 review (Markdown)
│       ├── evaluation-r1.json # Round 1 review (JSON sidecar: scores, verdict, feedback)
│       ├── alignment-r1.md # Alignment review (only if dual_evaluation)
│       ├── build-r1.log   # Builder log
│       ├── spec-r2.md     # Round 2 (if iterating)
│       └── ...
└── archive/               # Archived completed sessions
```

| 工件 | 产出方 | 说明 |
|----------|-------------|-------------|
| **spec** | Planner | 分析、技术方案、影响、风险 |
| **contract**（.md + .json） | Planner | 迭代契约：交付物、验收标准、复杂度 |
| **evaluation**（.md + .json） | Evaluator | 四维评分（完整性 / 质量 / 回归 / 设计）与反馈 |
| **alignment** | Alignment Evaluator | 对齐评审（仅当开启 `dual_evaluation`） |
| **events.jsonl** | 系统 | 每次 agent 调用、CI 运行、状态变更的结构化事件 |
| **state.json** | 系统 | 会话状态；支持 `--resume` |

每一步都可追溯 — 可回答谁做了什么、为何通过或阻塞。JSON 侧车适合自动化与 UI，无需正则解析 Markdown。

---

## 仓库布局

```
harness-orchestrator/
├── src/harness/
│   ├── cli.py              # CLI entry (Typer)
│   ├── __init__.py          # Package metadata
│   ├── commands/            # Commands: subcommand implementations
│   ├── orchestrator/        # Orchestration: workflow core
│   ├── drivers/             # Drivers: IDE agent invocation abstraction
│   ├── core/                # Core: state, config, UI, events
│   ├── methodology/         # Methodology: evaluation, scoring, contracts
│   ├── templates/           # Role prompt templates
│   └── integrations/        # Integrations: Git, Memverse
├── agents/                  # Role definition templates (Cursor / Codex)
├── tests/                   # Test suite (includes fixtures/)
├── docs/                    # Docs (state machine, compatibility matrix)
├── examples/                # Benchmarks and examples
├── pyproject.toml           # Metadata, dependencies, build
└── README.md
```

<details>
<summary>模块职责</summary>

- **`cli.py`** — 单一用户入口；用 Typer 注册子命令并委派到 `commands/`
- **`commands/`** — 参数解析与流程启动；调用 `orchestrator/` 中的工作流逻辑
- **`orchestrator/`** — 核心引擎：`workflow.py` 单任务循环，`autonomous.py` 自主循环，`vision_flow.py` vision，`safety.py` 安全阀
- **`drivers/`** — 封装 Cursor 与 Codex CLI 细节；上层使用 `AgentDriver` 协议；`resolver.py` 按模式（auto/cursor/codex）路由角色；启动时 capability probe 检查版本与 flags
- **`core/`** — 运行时状态（`state.py`）、项目配置（`config.py`）、终端 UI（`ui.py`）、结构化事件（`events.py`）、扫描、归档、索引
- **`methodology/`** — 解析评审输出、计算四维分数、契约模板、JSON 侧车
- **`integrations/`** — Git 分支与 Memverse 长期记忆

</details>

---

## 恢复、停止与排错

### 恢复中断的工作

若运行意外停止，Harness 会在 `state.json` 中打点：

```bash
harness run "original requirement" --resume
harness auto --resume
```

`--resume` 重新加载上次会话并从中断阶段继续。

### 停止行为

`harness stop` 不会杀进程；它写入 `.agents/.stop`。运行中的任务在完成**当前阶段**（plan/build/eval）后检测到信号并干净退出。要立即中止请用 `Ctrl+C`；Harness 在退出前会保存检查点。

### 未找到 IDE CLI

Harness 负责编排；agent 通过 Cursor 或 Codex CLI 运行。启动时 Harness 会执行 capability probe（版本与关键 flags）。不兼容环境可能记录警告，但执行仍会继续。

若出现 `Neither Cursor nor Codex CLI detected`（或类似信息）：

- **Cursor**：命令面板 → `Install 'cursor' command`
- **Codex**：npm 或 [GitHub](https://github.com/openai/codex)

确保二进制在 PATH 中；至少需要其一。版本细节见 [docs/zh-CN/compatibility.md](docs/zh-CN/compatibility.md)。

### Codex 集成

对 Codex 角色，Harness 将各角色的 `developer_instructions` 拼入 `codex exec` 输入；不依赖已弃用的 `codex exec --agent`。

### 本地优先

所有状态与工件保留在磁盘；无云依赖。通常整个 `.agents/` 树会 gitignore — 含本地运行时、`state.json`、任务工件与归档。若需团队共享 `config.toml` 或 `vision.md`，可按需使用 `git add -f .agents/config.toml` 等。

---

## 可观测性

每个会话将结构化事件写入 `.agents/runs/<session-id>/events.jsonl`，每行一个 JSON 对象：

```json
{"ts": "2026-03-31T10:00:00.000Z", "event": "agent_end", "role": "planner", "driver": "codex", "exit_code": 0, "elapsed_ms": 12340, "output_len": 2048, "iteration": 1}
```

事件类型包括：

| 事件 | 内容 |
|-------|----------|
| `agent_start` / `agent_end` | 角色、驱动、耗时、退出码、输出长度 |
| `ci_result` | CI 命令、退出码、结论、耗时 |
| `state_transition` | 从状态 → 到状态 |
| `task_start` / `task_end` | 任务 ID、需求、分支、最终结论与分数 |

查看日志：

```bash
cat .agents/runs/*/events.jsonl | python -m json.tool
```

---

## 双评审器

当 `workflow.dual_evaluation = true` 时，通过质量评审的任务还会经过对齐评审：

- **质量 Evaluator**（默认）— 代码质量 + 回归；四维评分
- **Alignment Evaluator** — 需求覆盖 + 契约契合 + 意图漂移

若对齐返回 `MISALIGNED`，任务回到 Builder；若 `CONTRACT_ISSUE`，反馈发给 Planner 而非 Builder。

```toml
[workflow]
dual_evaluation = true
```

---

## 延伸阅读

| 文档 | 说明 |
|-----|-------------|
| [docs/zh-CN/state-machine.md](docs/zh-CN/state-machine.md) | 任务状态机：合法转换、恢复、停止信号、BLOCKED |
| [docs/zh-CN/compatibility.md](docs/zh-CN/compatibility.md) | 运行时矩阵：Cursor/Codex CLI 版本与已知限制 |
| [examples/todo-api-benchmark/](examples/todo-api-benchmark/) | 基准：五个递增任务，三种模式（Codex / Cursor / Harness） |

---

## 适用与不适用

**适合：**

- 已使用 Cursor 或 Codex，希望 agent 在清晰方法论下推进工作
- 希望对 agent 输出有质量门禁，而非单次盲信
- 希望在多步工作中保持连续性与可追溯性

**不适合：**

- 期望一键「全自动做完整个产品」
- 需要企业审批、发布火车或与核心编码无关的数据编排
- 无法安装本地 CLI（Cursor/Codex）的环境

---

## 国际化

Harness 支持英文（默认）和中文。在初始化时设置语言：

```bash
harness init --lang zh    # 中文提示和生成文件
harness init --lang en    # 英文（默认）
```

语言设置影响：

- CLI 提示和消息
- 发送给 LLM 的 Agent 提示
- 生成的模板文件（vision.md、config.toml 注释）
- 安装到 IDE 的 Agent 定义指令

语言偏好存储在 `.agents/config.toml` 的 `[project] lang` 中。

---

## 开发

```bash
# Dev install (pytest + ruff)
pip install -e ".[dev]"

# Tests
pytest

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
```

Ruff 面向 Python 3.9，行宽 100。

---

## 许可

[MIT](LICENSE)
