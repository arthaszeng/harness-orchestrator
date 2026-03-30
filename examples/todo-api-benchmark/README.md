# Benchmark: TODO API

对比 Harness 编排模式与直接使用 Codex / Cursor 的效果差异。

## 测试项目

一个简单的 Python TODO API（FastAPI + SQLite），从空项目开始。

## 5 个递增任务

| # | 任务 | 预期复杂度 |
|---|------|-----------|
| 1 | 初始化 FastAPI 项目，添加健康检查端点和基础项目结构 | simple |
| 2 | 实现 TODO CRUD API（创建、读取、更新、删除）+ SQLite 存储 | medium |
| 3 | 添加输入验证、错误处理和 Pydantic 模型 | medium |
| 4 | 实现分页、过滤（按状态）和排序功能 | medium |
| 5 | 添加完整的 pytest 测试套件，覆盖所有端点和边界情况 | complex |

## 三种模式

### A. 直接 Codex
```bash
codex exec --full-auto - <<< "任务描述"
```

### B. 直接 Cursor
```bash
cursor agent --print --force "任务描述"
```

### C. Harness 编排
```bash
harness init --name todo-api --ci "pytest" -y
harness run "任务描述"
```

## 对比指标

| 指标 | 说明 |
|------|------|
| **完成率** | 5 个任务中成功完成的比例 |
| **平均迭代次数** | 每个任务从开始到通过的迭代轮数 |
| **CI 首次通过率** | 第一轮 build 后 CI 即通过的比例 |
| **人工干预次数** | 需要人工修改代码才能继续的次数 |
| **可回放性** | 事后能否完整追溯每个决策的原因 |

## 运行步骤

### 准备
```bash
mkdir /tmp/todo-benchmark && cd /tmp/todo-benchmark
git init && git commit --allow-empty -m "init"
```

### 模式 C: Harness（推荐先跑这个，生成完整 artifacts）
```bash
pip install harness-orchestrator
harness install
harness init --name todo-api --ci "pytest" -y

# 逐任务执行
harness run "初始化 FastAPI 项目，添加健康检查端点和基础项目结构"
harness run "实现 TODO CRUD API（创建、读取、更新、删除）+ SQLite 存储"
harness run "添加输入验证、错误处理和 Pydantic 模型"
harness run "实现分页、过滤（按状态）和排序功能"
harness run "添加完整的 pytest 测试套件，覆盖所有端点和边界情况"
```

### 演示亮点

- **中途 Ctrl+C 后 resume**：在任务 3 执行中按 Ctrl+C，然后 `harness run "..." --resume`
- **查看 artifacts**：`ls .agents/tasks/` 查看每轮的 spec、contract、evaluation
- **查看 events**：`cat .agents/runs/*/events.jsonl | python -m json.tool`
- **JSON sidecar**：`cat .agents/tasks/task-001/contract-r1.json`

## 结果记录模板

```markdown
| 指标 | Codex | Cursor | Harness |
|------|-------|--------|---------|
| 完成率 | ?/5 | ?/5 | ?/5 |
| 平均迭代次数 | N/A | N/A | ? |
| CI 首次通过率 | ?% | ?% | ?% |
| 人工干预 | ? 次 | ? 次 | ? 次 |
| 可回放性 | 无 | 无 | 完整 |
```
