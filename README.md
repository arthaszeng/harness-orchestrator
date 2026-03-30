# harness-orchestrator

> 合同驱动的多 Agent 自主开发编排框架，支持 Cursor 和 Codex。

[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/harness-orchestrator)](https://pypi.org/project/harness-orchestrator/)

当前 AI 编码工具在单次任务上表现出色，但在连续开发中容易出现目标漂移、上下文断裂、质量门禁缺失和过程不可追踪。harness-orchestrator 将多种 agent 能力组织进一个合同驱动、可审计、可恢复的工程闭环：

- **需求推进有方法** — Planner 分析需求生成 spec，协商迭代合同，而非直接让 agent 写代码
- **实现与评审分离** — Builder 按合同编码，Evaluator 独立审查并四维评分，实现质量门禁
- **自治但可控** — Strategist 根据 vision 自主选择任务，但受迭代上限、通过阈值和停止信号约束
- **全程留痕** — 每轮迭代的 spec、contract、evaluation 均以 Markdown + JSON 双格式保存，支持事后审计、自动化消费和中断恢复
- **可观测** — 每次 agent 调用、CI 执行和状态转换均记录为结构化事件（`events.jsonl`），便于诊断和度量

> **设计理念**：核心架构受 GAN 对抗思想启发——Builder（生成器）和 Evaluator（判别器）的分离与迭代博弈推动代码质量收敛，Planner 通过合同协议为双方建立共同基准。

## 快速开始

### 前置条件

| 依赖 | 要求 | 说明 |
|------|------|------|
| **Python** | >= 3.11 | 运行 Harness CLI 本身 |
| **Cursor CLI 和/或 Codex CLI** | 至少安装一个 | 提供实际 agent 能力 |
| **Git** | 任意版本 | 项目需已初始化 Git 仓库，Harness 依赖 Git 进行分支管理和变更追踪 |

IDE CLI 安装方式：

- **Cursor**：打开 Cursor 编辑器 → 命令面板 → `Install 'cursor' command`，确保 `cursor` 命令在 PATH 中可用
- **Codex**：通过 npm 或从 [GitHub](https://github.com/openai/codex) 安装，确保 `codex` 命令在 PATH 中可用

> `auto` 模式下的默认路由是**可替换的经验默认值**（Builder→Cursor，其余角色→Codex）。这不是 Harness 的核心价值——核心资产是合同协议、评估标尺、状态机、工件链和中断恢复机制。你可以在 `.agents/config.toml` 中为每个角色独立配置驱动。仅有一个 CLI 时，所有角色将通过该驱动运行。

### 安装

从 PyPI 安装：

```bash
pip install harness-orchestrator
```

或从源码安装（开发用途）：

```bash
git clone https://github.com/arthaszeng/harness-orchestrator.git
cd harness-orchestrator
pip install -e .
```

验证安装：

```bash
harness --version
# harness-orchestrator 0.2.7
```

### 五步上手

```bash
# 1. 安装 agent 定义到本地 IDE
harness install

# 2. 在项目中初始化配置
cd /path/to/your/project
harness init

# 3. 创建项目愿景
harness vision

# 4. 执行任务（二选一）
harness run "add user authentication"   # 单任务模式
harness auto                            # 自治模式

# 5. 查看进度 / 停止
harness status
harness stop
```

以下各节对每个步骤展开说明。

---

## 初始化与配置

### harness install

将角色定义文件安装到本地 IDE 目录（`~/.cursor/agents/` 和/或 `~/.codex/agents/`）。Harness 会自动检测已安装的 IDE，仅安装对应的 agent 文件。使用 `--force` 可覆盖已有定义。

### harness init

在当前项目中启动交互式向导，完成六个步骤：

1. **项目信息** — 名称和描述
2. **IDE 环境** — 检测 Cursor/Codex 并可选安装 agent 定义
3. **驱动模式** — 选择 auto（推荐：Builder→Cursor，其余→Codex）、cursor 或 codex
4. **CI 门禁** — 配置用于质量检查的命令，支持 AI 分析推荐
5. **Memverse 集成** — 可选开启长期记忆，在反思阶段持久化关键决策
6. **Vision** — 选择立即生成或稍后编辑

初始化完成后在项目根目录生成 `.agents/` 目录，包含以下关键文件：

| 生成文件 | 说明 |
|----------|------|
| `.agents/config.toml` | 项目配置：驱动模式、CI 命令、工作流参数等 |
| `.agents/vision.md` | 项目愿景（如在向导中选择立即生成） |
| `.agents/state.json` | 运行时状态（首次运行任务时自动创建，建议加入 `.gitignore`） |

也可通过 `--non-interactive` 跳过向导使用默认值：

```bash
harness init --name my-project --ci "make test" -y
```

### harness vision

通过交互式问答，由 Advisor agent 帮助将简短描述展开为结构化的 vision 文档，写入 `.agents/vision.md`。Vision 是 Strategist 在自治模式下选择任务的核心依据。也可以直接编辑该文件。

---

## 核心工作流

### 角色架构

| 角色 | 职责 | auto 默认后端 |
|------|------|--------------|
| **Planner** | 分析需求，生成 spec 和迭代合同 | Codex |
| **Builder** | 按合同编写代码，提交变更 | Cursor |
| **Evaluator** | 独立审查代码，四维评分（完整性/质量/回归/设计），决定通过或继续迭代 | Codex |
| **Alignment Evaluator** | 需求对齐检查：合同符合度、需求覆盖度、意图偏离检测（需开启 `dual_evaluation`） | Codex |
| **Strategist** | 在自治模式下根据 vision 和进展选择下一个任务 | Codex |
| **Reflector** | 任务完成后提炼经验，写入长期记忆 | Codex/Cursor |

另有 **Advisor** 角色用于 `harness vision` 和 `harness init` 中的 AI 辅助分析。

> 每个角色的后端均可通过 `[drivers.roles]` 独立配置。上表中的默认值是 `auto` 模式下的经验偏好，不是固定绑定。详见 [docs/compatibility.md](docs/compatibility.md) 了解 CLI 版本要求。

### 单任务流程 (`harness run`)

```
用户输入需求
  → Planner: 生成 spec（需求分析、技术方案、影响范围、风险点）
  → Planner: 协商迭代合同（交付物清单、验收标准、复杂度评估）
  → Builder: 按合同编写代码并提交
  → Evaluator: 独立审查，四维评分
      → 得分 ≥ 阈值（默认 3.5）→ PASS，任务完成
      → 得分 < 阈值 → 反馈给 Builder，进入下一轮迭代
  → 达到最大迭代次数（默认 3）仍未通过 → 任务阻塞
```

### 自治循环 (`harness auto`)

```
读取 .agents/vision.md
  → Strategist: 根据 vision 和当前进展选择下一个任务
  → 执行单任务流程（同上）
  → Reflector: 提炼本轮经验
  → 循环继续，直到：
      - 所有任务完成
      - 收到停止信号（harness stop）
      - 连续阻塞次数达上限（默认 2）
      - 达到单次会话任务上限（默认 10）
```

### `run` 与 `auto` 的选择

|  | `harness run` | `harness auto` |
|---|---|---|
| **适用场景** | 已有明确需求，需要一次完成 | 有 vision 但不确定拆分方式，交给 Strategist 规划 |
| **任务来源** | 用户通过命令行传入 | Strategist 根据 vision 和进展自动选择 |
| **执行范围** | 单个任务的 plan→build→eval 循环 | 多个任务的持续循环 |
| **前置要求** | 已完成 `init` | 已完成 `init` + `vision` |
| **停止方式** | 任务完成或达到最大迭代次数 | 手动 `harness stop`、所有任务完成、或触发安全阀 |

两种模式都支持 `--resume`（从上次中断处恢复）和 `--verbose`（显示完整 agent 输出）。

---

## 命令参考

| 命令 | 说明 |
|------|------|
| `harness install [--force / -f]` | 安装 agent 定义到本地 IDE |
| `harness init [--name / -n NAME] [--ci CMD] [--non-interactive / -y]` | 在项目中初始化 harness 配置 |
| `harness vision` | 交互式创建或更新项目愿景 |
| `harness run <需求> [--resume / -r] [--verbose / -V]` | 执行单个开发任务 |
| `harness auto [--resume / -r] [--verbose / -V]` | 启动自治开发循环 |
| `harness status` | 查看当前进度和状态 |
| `harness stop` | 优雅停止当前运行的任务 |
| `harness --version / -v` | 显示版本号 |

### 关键参数说明

- **`--resume / -r`** — 从 `state.json` 恢复上次会话状态，从中断的阶段继续执行而非重新开始。适用于进程退出、终端关闭等意外中断后的恢复。
- **`--verbose / -V`** — 显示完整的 agent 输入输出内容，用于调试或了解 agent 的具体行为。默认关闭以保持输出简洁。
- **`--force / -f`**（install） — 覆盖已安装的 agent 定义文件，用于更新到新版本。
- **`--non-interactive / -y`**（init） — 跳过交互式向导，使用默认值完成初始化。可配合 `--name` 和 `--ci` 指定项目名称和 CI 命令。

---

## 配置参数

项目级配置位于 `.agents/config.toml`，关键参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `workflow.profile` | "standard" | 工作流档位：`lite` / `standard` / `autonomous`（见下文） |
| `workflow.max_iterations` | 3 | 单任务最大迭代轮数 |
| `workflow.pass_threshold` | 3.5 | Evaluator 通过阈值（满分 5） |
| `workflow.auto_merge` | true | 通过后自动合并分支 |
| `workflow.branch_prefix` | "agent" | 任务分支前缀 |
| `workflow.dual_evaluation` | false | 开启双 Evaluator：quality review 通过后追加 alignment review |
| `autonomous.max_tasks_per_session` | 10 | 自治模式单次会话最大任务数 |
| `autonomous.consecutive_block_limit` | 2 | 连续阻塞次数上限，超过则停止 |

### Workflow Profiles

| Profile | 流程 | 适用场景 |
|---------|------|----------|
| **lite** | planner → builder → eval（跳过 spec/contract 拆分，阈值上限 3.0，最多 2 轮） | 小需求、快速修复、原型验证 |
| **standard** | planner → spec + contract → builder → eval（完整四维评审） | 日常开发任务（默认） |
| **autonomous** | strategist → standard 循环 → reflector（多任务连续推进） | 有 vision 的自治开发 |

通过 `.agents/config.toml` 设置：

```toml
[workflow]
profile = "lite"  # 或 "standard" / "autonomous"
```

---

## 任务工件

Harness 在项目根目录的 `.agents/` 下管理所有工件：

```
.agents/
├── config.toml            # 项目配置（harness init 生成）
├── vision.md              # 项目愿景（harness vision 生成）
├── state.json             # 运行时状态
├── .stop                  # 停止信号文件（harness stop 写入，任务结束后自动清除）
├── runs/
│   └── <session-id>/
│       └── events.jsonl   # 结构化事件日志（agent 调用、CI、状态转换）
├── tasks/
│   └── task-001/
│       ├── spec-r1.md     # 第 1 轮 spec：需求分析和技术方案
│       ├── contract-r1.md # 第 1 轮合同（Markdown）
│       ├── contract-r1.json # 第 1 轮合同（JSON sidecar，机器友好）
│       ├── evaluation-r1.md # 第 1 轮评审（Markdown）
│       ├── evaluation-r1.json # 第 1 轮评审（JSON sidecar：分数、verdict、反馈）
│       ├── alignment-r1.md # 对齐评审（仅 dual_evaluation 开启时）
│       ├── build-r1.log   # Builder 工作日志
│       ├── spec-r2.md     # 第 2 轮（如需迭代）
│       └── ...
└── archive/               # 已完成会话的归档
```

| 工件 | 生成者 | 说明 |
|------|--------|------|
| **spec** | Planner | 需求分析、技术方案、影响范围和风险点 |
| **contract** (.md + .json) | Planner | 迭代合同：交付物清单、验收标准和复杂度评估 |
| **evaluation** (.md + .json) | Evaluator | 四维评分（completeness / quality / regression / design）和详细反馈 |
| **alignment** | Alignment Evaluator | 需求对齐评审（仅 `dual_evaluation` 开启时生成） |
| **events.jsonl** | 系统 | 每个 agent 调用、CI 执行和状态转换的结构化事件 |
| **state.json** | 系统 | 会话运行状态，支持 `--resume` 恢复 |

每一次任务推进都可追溯——你可以回答"为什么做这个任务、谁做了什么、为什么通过或被阻塞"。JSON sidecar 便于自动化工具和 UI 消费，无需从 Markdown 正则提取数据。

---

## 仓库结构

```
harness-orchestrator/
├── src/harness/
│   ├── cli.py              # CLI 入口（Typer）
│   ├── __init__.py          # 包元信息
│   ├── commands/            # 命令层：子命令实现
│   ├── orchestrator/        # 编排层：工作流核心逻辑
│   ├── drivers/             # 驱动层：IDE agent 调用抽象
│   ├── core/                # 核心层：状态、配置、UI、事件
│   ├── methodology/         # 方法论层：评估、评分、合同
│   ├── templates/           # 角色 prompt 模板
│   └── integrations/        # 集成层：Git、Memverse
├── agents/                  # 角色定义模板（Cursor / Codex）
├── tests/                   # 测试套件（含 fixtures/）
├── docs/                    # 项目文档（状态机、兼容性矩阵）
├── examples/                # Benchmark 和示例
├── pyproject.toml           # 项目元信息、依赖和构建配置
└── README.md
```

<details>
<summary>模块职责详情</summary>

- **`cli.py`** — 唯一的用户入口，通过 Typer 注册子命令，委托给 `commands/` 下的对应模块
- **`commands/`** — 参数解析和流程启动，调用 `orchestrator/` 中的工作流逻辑
- **`orchestrator/`** — 核心编排引擎：`workflow.py` 驱动单任务循环，`autonomous.py` 驱动自治循环，`vision_flow.py` 处理 vision 生成，`safety.py` 管理安全阀
- **`drivers/`** — 封装 Cursor 和 Codex 的 CLI 调用细节，上层通过 `AgentDriver` 协议统一使用；`resolver.py` 根据驱动模式（auto/cursor/codex）将角色路由到对应实现；启动时执行 capability probe 检测版本和 flag 兼容性
- **`core/`** — 运行时状态（`state.py`）、项目配置（`config.py`）、终端 UI（`ui.py`）、结构化事件日志（`events.py`）、文件扫描、归档和索引
- **`methodology/`** — 评估结果解析、四维评分计算、合同模板处理和 JSON sidecar 生成
- **`integrations/`** — Git 分支管理和 Memverse 长期记忆对接

</details>

---

## 恢复、停止与常见问题

### 恢复中断的任务

如果执行中断（进程退出、终端关闭等），Harness 会通过 `state.json` 保存检查点：

```bash
harness run "原始需求" --resume
harness auto --resume
```

`--resume` 从 `state.json` 中恢复上次会话状态，从中断的阶段继续执行。

### 停止机制

`harness stop` 不会强制终止进程，而是写入 `.agents/.stop` 信号文件。正在运行的任务会在完成当前阶段（plan/build/eval）后检测到信号并优雅退出。如需立即终止，使用 `Ctrl+C`，Harness 会在退出前保存 checkpoint。

### IDE CLI 未找到

Harness 是编排层，实际 agent 能力由 Cursor CLI 或 Codex CLI 提供。启动时 Harness 会自动执行 capability probe——检测 CLI 版本号并验证关键 flag 是否可用。不兼容时打印 warning 但不阻塞执行。

如果启动时报 `未检测到 Cursor 或 Codex CLI`：

- **Cursor**：打开 Cursor 编辑器 → 命令面板 → `Install 'cursor' command`
- **Codex**：通过 npm 或从 [GitHub](https://github.com/openai/codex) 安装

确保对应命令在 PATH 中可用。至少安装其中一个即可。详细版本要求见 [docs/compatibility.md](docs/compatibility.md)。

### Codex 集成方式

Harness 在运行 Codex 角色时，将角色的 `developer_instructions` 直接拼接进 `codex exec` 的输入，不依赖旧版 `codex exec --agent` 入口。

### 本地优先

所有状态和工件保存在本地文件系统，不依赖云服务。`.agents/` 整个目录默认被 `.gitignore` 排除——它是本地运行时目录，包含 `state.json`、任务工件、归档等。如需将 `config.toml` 或 `vision.md` 纳入版本控制供团队共享，使用 `git add -f .agents/config.toml` 手动添加。

---

## 可观测性

每次会话运行时，Harness 将结构化事件写入 `.agents/runs/<session-id>/events.jsonl`，每行一个 JSON 对象：

```json
{"ts": "2026-03-31T10:00:00.000Z", "event": "agent_end", "role": "planner", "driver": "codex", "exit_code": 0, "elapsed_ms": 12340, "output_len": 2048, "iteration": 1}
```

事件类型包括：

| 事件 | 内容 |
|------|------|
| `agent_start` / `agent_end` | 角色、驱动、耗时、退出码、输出长度 |
| `ci_result` | CI 命令、退出码、verdict、耗时 |
| `state_transition` | 来源状态 → 目标状态 |
| `task_start` / `task_end` | 任务 ID、需求、分支、最终 verdict 和得分 |

查看事件日志：

```bash
cat .agents/runs/*/events.jsonl | python -m json.tool
```

---

## 双 Evaluator

开启 `workflow.dual_evaluation = true` 后，quality review 通过的任务会额外经过 alignment review：

- **Quality Evaluator**（默认）— 代码质量 + 回归检查，四维评分
- **Alignment Evaluator** — 需求覆盖度 + 合同符合度 + 意图偏离检测

如果 alignment 判定为 `MISALIGNED`，任务回到 Builder 迭代；如果判定为 `CONTRACT_ISSUE`，反馈指向 Planner 而非 Builder。

```toml
[workflow]
dual_evaluation = true
```

---

## 进一步了解

| 文档 | 说明 |
|------|------|
| [docs/state-machine.md](docs/state-machine.md) | 任务状态机：合法转换、resume 行为、stop 信号、BLOCKED 处理 |
| [docs/compatibility.md](docs/compatibility.md) | 运行时兼容性矩阵：Cursor/Codex CLI 版本要求、已知限制 |
| [examples/todo-api-benchmark/](examples/todo-api-benchmark/) | Benchmark demo：5 个递增任务，三种模式对比（Codex / Cursor / Harness） |

---

## 适用与不适用场景

**适用：**

- 已在使用 Cursor 或 Codex，希望让 agent 在明确方法论下持续推进项目
- 需要对 agent 行为建立质量门禁，而非完全信任单次输出
- 希望多轮开发任务之间有连续上下文和可追踪记录

**不适用：**

- 追求"一键生成整个产品"的全自动方案
- 需要企业级审批、发布、数据编排等与核心编码无关的工作流
- 不愿意安装本地 CLI 工具（Cursor/Codex）的环境

---

## 开发

```bash
# 开发安装（包含 pytest 和 ruff）
pip install -e ".[dev]"

# 运行测试
pytest

# 静态检查
ruff check src/ tests/

# 格式化
ruff format src/ tests/
```

Ruff 目标版本为 Python 3.11，行宽限制 100 字符。

---

## 许可证

[MIT](LICENSE)
