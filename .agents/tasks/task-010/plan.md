# Spec

## Analysis

v4.0.0 大重构移除了 orchestrator 模式，task-009 完成了主要清理（死代码删除、driver 默认值、
孤儿模板、README 重写、文档归档）。但仍存在一批 **vocabulary-level 遗留**：

1. **update.py 描述错误** — `"workflow mode and iteration settings"` 仍提及已移除的 `workflow.mode`
2. **Python API 中 `driver`/`driver_name` 参数命名** — events.py、tracker.py、ui.py 中参数名
   仍使用 orchestrator 时代的 "driver" 词汇，虽已默认 `"cursor"`，但对新贡献者造成认知混淆
3. **`DEFAULT_DRIVER` 常量命名** — roles.py 中的常量名和注释仍引用 "driver" / "orchestrator-routed"
4. **测试中的 `"codex"` 字面量** — test_ui.py (5处) 和 test_registry.py (1处) 使用 `"codex"`
   作为 driver 参数，暗示 Codex 仍是一等公民
5. **ui.py docstring** — `agent_step` docstring 说 "the driver writes raw stderr"
6. **空目录** — `.agents/archive/` 是空目录
7. **registry.py 的 SQLite `driver` 列** — task-009 明确决策保留（避免 schema 迁移），不在本次范围

## Approach

**分两个层次处理**：

### A. 词汇标准化 (driver → runtime)

将 Python API 中的 `driver`/`driver_name` 参数重命名为 `runtime`/`runtime_name`，
`DEFAULT_DRIVER` → `DEFAULT_RUNTIME`。这是一个纯粹的**内部 API 重命名**，不涉及：
- SQLite schema（`driver` 列保留，registry.py 内部继续向该列写入）
- 外部 API / CLI 输出
- 事件 JSONL 中的 `driver` 字段名（保持兼容）

影响文件有限且变更机械化，风险极低。

### B. 小修小补

- update.py 描述修正
- 测试中 codex → cursor
- 注释 / docstring 更新（含模块级 docstring）

### C. Breaking Change 声明

重命名 keyword-only 参数 (`driver=` → `runtime=`, `driver_name=` → `runtime_name=`)
是对 `harness.core.*` 内部 API 的 breaking change。由于本包无已知外部调用方
（所有使用都在 in-repo tests 和 tracker → registry/events 调用链中），
接受此变更并在 CHANGELOG 中注明。

**不做的事**：
- 不重命名 SQLite `driver` 列（task-009 已决策保留）
- 不修改 events.jsonl 中的 `driver` 字段名（向后兼容）
- 不重命名 `AgentRun.driver` dataclass 字段（映射 SQLite 列）
- 不修改历史 task artifacts

## Impact

- 修改文件: ~8 个源码/测试文件
- 删除文件: 0
- 新增文件: 0
- 爆炸半径: 小（纯内部 API 重命名 + 注释修正）

## Risks

| 风险 | 缓解 |
|------|------|
| `runtime` 参数名与 registry `driver` 列不一致 | registry.py 内部做映射，对外暴露 `runtime` |
| 事件 JSONL 字段名不一致 | events.py 内部 `_emit(driver=runtime)` 保持输出字段名 |
| 遗漏某处引用 | 全面 grep + pytest 验证 |

---

# Contract

## Deliverables

### 文件终态速查表

| 文件 | 变更 | Deliverable |
|------|------|-------------|
| `core/roles.py` | `DEFAULT_DRIVER` → `DEFAULT_RUNTIME`，更新注释 | D1 |
| `core/events.py` | 参数 `driver` → `runtime`，_emit 保持 `driver=runtime` | D2 |
| `core/tracker.py` | 参数 `driver_name` → `runtime_name`，docstring 更新 | D2 |
| `core/ui.py` | 参数/属性 `driver_name` → `runtime_name`，docstring 修正 | D2 |
| `core/registry.py` | `register()` 参数 `driver` → `runtime`，内部映射到 `driver` 列；log 消息更新 | D2 |
| `commands/update.py` | 修正 workflow 描述 | D3 |
| `tests/test_ui.py` | `"codex"` → `"cursor"`，参数名适配 | D4 |
| `tests/test_registry.py` | `driver=` → `runtime=`，`"codex"` → `"cursor"` | D4 |
| `ARCHITECTURE.md` | 更新 roles.py 描述中的 `DEFAULT_DRIVER` → `DEFAULT_RUNTIME` | D5 |

### D1: SSOT 常量重命名
- `roles.py`: `DEFAULT_DRIVER` → `DEFAULT_RUNTIME`
- 更新注释：移除 "orchestrator-routed" 和 "driver" 措辞
- AC: `rg 'DEFAULT_DRIVER' src/` 返回零结果；`rg 'orchestrator-routed' src/` 返回零结果

### D2: 内部 API 参数重命名 (driver → runtime)
- `events.py`: `agent_start/agent_end` 参数 `driver` → `runtime`，但 `_emit(driver=runtime)` 保持 JSONL 兼容
- `tracker.py`: `track()` 参数 `driver_name` → `runtime_name`；更新 **函数 docstring + 模块级 docstring**（"the driver is always" → "the runtime is always"）
- `ui.py`: `_TailRenderable.__init__` 和 `agent_step` 的 `driver_name` → `runtime_name`；修正 docstring "the driver writes" → "caller handles"
- `registry.py`: `register()` 参数 `driver` → `runtime`；内部 `_to_text(driver)` → `_to_text(runtime)`；更新 log.debug 消息；在 docstring 中注明 "value stored in the `driver` column for schema compatibility"
- AC: `rg 'driver_name' src/harness/core/` 返回零结果；`rg 'driver:' src/harness/core/events.py` 仅出现在 `_emit()` 调用中

### D3: update.py 描述修正
- `"workflow mode and iteration settings"` → `"iteration and branch settings"`
- AC: `rg 'workflow mode' src/` 返回零结果

### D4: 测试适配 + JSONL 向后兼容测试
- `test_ui.py`: 所有 `"codex"` → `"cursor"`；参数名 `driver_name` → `runtime_name`（如有直接引用）
- `test_registry.py`: `driver=` → `runtime=`；`"codex"` → `"cursor"`
- **新增**: `test_events.py` 或在已有测试中新增用例，断言 `EventEmitter.agent_start` 输出的 JSONL 行包含 `"driver"` 键（非 `"runtime"`），验证向后兼容
- AC: `rg '\bcodex\b' tests/test_ui.py tests/test_registry.py` 返回零结果；JSONL 兼容测试通过；`python -m pytest tests/ -v` 全部通过

### D5: 文档更新
- `ARCHITECTURE.md`: `DEFAULT_DRIVER` → `DEFAULT_RUNTIME`，相关描述更新
- AC: `rg 'DEFAULT_DRIVER' ARCHITECTURE.md` 返回零结果

## Acceptance Criteria

- `python -m pytest tests/ -v` 全部通过
- `ruff check src/ tests/` 无新增 lint 错误
- `rg 'DEFAULT_DRIVER' src/` 返回零结果
- `rg 'driver_name' src/harness/core/` 返回零结果
- `rg '\bcodex\b' tests/test_ui.py tests/test_registry.py` 返回零结果
- `rg 'workflow mode' src/` 返回零结果
- `rg 'orchestrator-routed' src/` 返回零结果
- 事件 JSONL 输出仍包含 `"driver"` 字段（向后兼容）
- SQLite `driver` 列不变

## Commit Strategy

每个 commit 保持树可编译且测试全绿 (bisect-safe)：

1. `refactor(core): rename driver → runtime in Python API` — D1 + D2 + D4（源码重命名 + 测试同步更新，一起提交确保 bisectability）
2. `fix(update): correct workflow section description` — D3
3. `docs: update ARCHITECTURE.md for runtime rename` — D5

## Out of Scope

- SQLite `driver` 列重命名（task-009 决策保留）
- `AgentRun.driver` dataclass 字段（映射 SQLite 列，保持一致）
- events.jsonl 中 `driver` 字段名（向后兼容）
- `.agents/tasks/` 历史审计文件
- test_config.py 中的 `[drivers]` section（测试旧配置兼容性）
- test_update.py 中的 `mode = "orchestrator"`（测试迁移兼容性）
- `.agents/archive/` 空目录（无害，已在项目中存在，不额外处理）

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected Alternative |
|---|-------|----------|---------------|-----------|-----------|---------------------|
| 1 | Naming | `driver` → `runtime` (非 `client`) | Taste | #5 Explicit | runtime 更准确描述执行环境；client 暗示网络交互 | `client`, `backend`, `engine` |
| 2 | Compat | 保留 events.jsonl `driver` 字段名 | Mechanical | #3 Pragmatic | JSONL 是审计日志，修改字段名破坏向后兼容 | 重命名为 `runtime` |
| 3 | Compat | 保留 `AgentRun.driver` dataclass 字段 | Mechanical | #3 Pragmatic | 直接映射 SQLite 列名，保持一致 | 引入 alias 映射 |
| 4 | Scope | 不清理空 `.agents/archive/` 目录 | Taste | #6 Bias to action | 无害，不值得单独 commit | 删除或加 .gitkeep |
| 5 | Scope | 不修改 test_config/test_update 中的 orchestrator 引用 | Mechanical | #1 Completeness | 这些是有意的兼容性回归测试 | 清理掉 |

---

## Plan Review Summary

### Round 1 — 5-Role Review (Score: 7.8/10)

| Role | Score | Verdict |
|------|-------|---------|
| Architect | 9/10 | PASS |
| Product Owner | 8/10 | ISSUES_FOUND |
| Engineer | 8/10 | ISSUES_FOUND |
| QA | 7/10 | ISSUES_FOUND |
| Project Manager | 7/10 | ISSUES_FOUND |

**[HIGH CONFIDENCE] Commit bisectability** (3/5 roles):
→ 已修复：将 D1+D2+D4 合并为单个 commit，确保源码重命名和测试更新同步

**[HIGH CONFIDENCE] Breaking change 未声明** (3/5 roles):
→ 已修复：新增 Section C 明确声明 breaking change 并接受（无外部调用方）

**[HIGH CONFIDENCE] 缺少 JSONL 向后兼容测试** (2/5 roles):
→ 已修复：D4 新增 JSONL 兼容性测试用例

**[WARN] Scope 叙述矛盾** (2/5 roles):
→ 已修复：移除 Approach B 中的 "清理空目录"，与 Out of Scope 保持一致

**[INFO] 模块级 docstring 也应更新** (2/5 roles):
→ 已修复：D2 中明确包含 tracker.py 模块级 docstring 和 registry.py docstring 更新
