# State Machine

Harness 使用显式状态机管理任务的生命周期。所有合法转换在 `src/harness/core/state.py` 中声明，任何违反转换约束的操作将抛出 `ValueError`。

## 状态定义

| 状态 | 含义 |
|------|------|
| `idle` | 无活跃任务 |
| `planning` | Planner 正在生成 spec 和 contract |
| `contracted` | 合同已生成，等待 Builder 执行 |
| `building` | Builder 正在编写代码 |
| `evaluating` | Evaluator 正在审查（含 CI 门禁） |
| `done` | 任务通过，已归档 |
| `blocked` | 任务阻塞（达最大迭代 / 驱动错误 / 手动停止） |

## 合法转换

```
idle ──────────► planning
planning ──────► contracted
planning ──────► blocked         (planner 失败)
contracted ────► building
building ──────► evaluating
building ──────► blocked         (驱动级错误)
evaluating ────► done            (PASS)
evaluating ────► planning        (ITERATE — 进入下一轮)
evaluating ────► blocked         (达最大迭代 / evaluator 失败 / stop 信号)
done ──────────► idle            (任务完成，清理)
blocked ───────► idle            (任务结束，清理)
```

### 流程图

```
        ┌──────┐
        │ idle │
        └──┬───┘
           │ start_task()
           ▼
     ┌──────────┐
     │ planning │◄─────────────────────┐
     └────┬─────┘                      │
          │ spec + contract ok         │ ITERATE
          ▼                            │
   ┌────────────┐                      │
   │ contracted │                      │
   └─────┬──────┘                      │
         │                             │
         ▼                             │
    ┌──────────┐                       │
    │ building │                       │
    └────┬─────┘                       │
         │ build done                  │
         ▼                             │
   ┌────────────┐    PASS     ┌──────┐ │
   │ evaluating │────────────►│ done │ │
   └─────┬──────┘             └──────┘ │
         │                             │
         └─────────────────────────────┘
         │
         │ max iter / abort / stop
         ▼
     ┌─────────┐
     │ blocked │
     └─────────┘
```

## Resume 行为

`harness run --resume` 从 `.agents/state.json` 恢复上次会话：

- 如果中断发生在 `planning` 或之后，resume 从当前 `iteration` 继续，不重置计数器
- artifact 文件名使用 `spec-r{N}.md` / `contract-r{N}.md` / `evaluation-r{N}.md`，其中 N 是迭代号
- resume 不会覆盖之前迭代的 artifact（迭代号递增）

## Stop 信号

- `harness stop` 写入 `.agents/.stop` 文件
- 正在运行的任务在完成**当前阶段**（plan / build / eval）后检测到信号并优雅退出
- 任务转为 `blocked` 状态
- `Ctrl+C`（SIGINT）会立即保存 checkpoint 后退出（exit code 130）

## BLOCKED 处理

- `blocked` 任务不会自动重试
- `blocked → idle` 转换在 `complete_task()` 中自动完成
- 要重试被阻塞的任务，使用 `harness run "<需求>"` 重新提交（不带 `--resume`）
