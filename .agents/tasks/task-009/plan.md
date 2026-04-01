# Spec

## Analysis

v4.0.0 大重构（移除 orchestrator 模式，专注 cursor-native）删除了 ~10,800 行代码，但留下了显著的遗留问题：

1. **死代码模块**：3 个 Python 模块完全无调用方可直接删除：`utils/retry.py`、`core/archive.py`、`core/index.py`
2. **生产代码未使用但测试引用的模块**：`core/tracker.py` 和 `core/events.py` 在 `src/` 的生产路径中无调用方，但被 `test_registry.py` 引用。这些模块的 `driver` 参数是 orchestrator 残留，需要清理但保留模块本身
3. **Orchestrator 时代的数据模型残留**：Registry 的 `driver` 列、events 的 `driver` 参数、status 命令的 "Driver" 表头、UI 中的 Codex ON/OFF 显示和 strategist 方法
4. **模板 Bug**：`_workspace-preflight.md.j2` 中 `branch_prefix` 缺少 `/` 分隔符，生成 `agenttask-NNN` 而非 `agent/task-NNN`
5. **孤儿模板**：3 个 section templates 从未被 include、3 个根级模板和 2 个 calibration 文件从未被代码引用
6. **配置不一致**：`init.py` 传递 `workflow_mode`/`memverse_driver` 给模板但模板不使用；`memverse.py` 的 `create_memverse(driver=)` 参数无用
7. **文档严重过时**：`docs/` 下 3 份文档仍描述旧 CLI 命令、driver 架构和 state machine；`ARCHITECTURE.md` 有过时声明
8. **state.py 残留**：`StopContext` docstring 引用 "autonomous loop"
9. **README 问题**：仍包含 v3→v4 迁移指南（无用户需要迁移）；仍有 orchestrator 时代残留叙事；缺少 Cursor-native 的品牌感

## Approach

分三条主线并行推进：

**A. 死代码清理**（D1）：删除 3 个完全无调用方的模块

**B. Driver 残留清理**（D2）：
- `events.py`、`tracker.py` **保留**（被 registry/测试使用），但 `driver` 参数改为可选且默认 `"cursor"`
- `registry.py` 保留 SQLite `driver` 列（不做 schema 迁移），但更新 docstring
- `ui.py` 移除 Codex ON/OFF 显示和 strategist 方法
- `status.py` 移除 "Driver" 列
- 引入 `DEFAULT_DRIVER = "cursor"` 常量避免散落 hardcode

**C. Bug 修复 + 配置清理**（D3–D6）

**D. 文档重构**（D7–D8）：
- README（EN/ZH）：移除迁移段落，围绕 Cursor-native 重新打造；Parallel Development 简化为一段（保留功能描述但去除冗余）
- `docs/` 下历史文档：删除并合并为 `docs/historical.md`，在 README 中添加指向链接
- `ARCHITECTURE.md`：修正过时描述

**不使用的方案**：
- 不重构 Registry 的 SQLite schema（会破坏现有 registry.db）——保留 `driver` 列但传默认值
- 不删除 `events.py`/`tracker.py`（仍被 registry 测试路径使用）

## Impact

- 删除文件：3 个 Python 模块 + 8 个模板文件 + 6 个旧文档
- 修改文件：~18 个（含测试）
- 新增文件：1 个 `docs/historical.md`（归档）

## Risks

1. **Registry `driver` 列不可删**：SQLite schema 迁移需要重建表。
   → 缓解：保留列，代码中使用 `DEFAULT_DRIVER` 常量
2. **README 大改可能遗漏信息**：
   → 缓解：保留所有功能描述，只移除过时的迁移/orchestrator 内容
3. **branch_prefix 规范化**：用户可能配置带尾部 `/` 的 prefix，拼接后产生 `//`
   → 缓解：模板中使用 `{{ branch_prefix | regex_replace('/$', '') }}/`（或在 skill_gen 中 strip）

---

# Contract

## Deliverables

### 文件终态速查表

| 文件 | 终态 | 归属 Deliverable |
|------|------|-----------------|
| `utils/retry.py` | **删除** | D1 |
| `core/archive.py` | **删除** | D1 |
| `core/index.py` | **删除** | D1 |
| `core/events.py` | **保留，改 driver 默认值** | D2 |
| `core/tracker.py` | **保留，改 driver 默认值** | D2 |
| `core/registry.py` | **保留，更新 docstring** | D2 |
| `core/ui.py` | **保留，移除 Codex/strategist** | D2 |
| `commands/status.py` | **保留，移除 Driver 列** | D2 |
| `integrations/memverse.py` | **保留，移除 driver 参数** | D5 |
| `core/state.py` | **保留，更新 docstring** | D6 |
| 3 个 orphan section templates | **删除** | D4 |
| 3 个根级模板 + 2 个 calibration | **删除** | D4 |
| 6 个 docs/*.md 旧文档 | **删除，归档到 historical.md** | D8 |

### D1: 删除完全无调用方的死代码模块
- 移除 `utils/retry.py`、`core/archive.py`、`core/index.py`
- 清理 `utils/__init__.py`（如果引用了 retry）
- AC: 这些文件不再存在；所有测试通过

### D2: 清理 driver 残留
- 在 `core/` 下引入 `DEFAULT_DRIVER = "cursor"` 常量
- `events.py`: `driver` 参数改为 `driver: str = DEFAULT_DRIVER`
- `tracker.py`: `driver_name` 参数改为 `driver_name: str = DEFAULT_DRIVER`
- `registry.py`: 更新 module docstring（移除 "planner, builder, evaluator, strategist, reflector, CI" 描述）
- `ui.py`: 移除 `system_status` 中 Codex ON/OFF、`strategist_result`、`strategist_done` 方法
- `status.py`: 移除 "Driver" 列
- AC: `harness status` 不再显示 "Driver" 列；UI 无 Codex 引用；events/tracker 的 `driver` 参数有默认值

### D3: 修复 branch prefix 模板 Bug
- `_workspace-preflight.md.j2` 中使用 `{{ branch_prefix }}/task-NNN`（在 branch_prefix 和 task 间加 `/`）
- 在 `skill_gen.py` 的 `_build_context` 中对 `branch_prefix` 做 rstrip("/") 以防双斜杠
- AC: 生成的 skill 中分支名为 `agent/task-NNN-xxx`

### D4: 删除孤儿模板
- Section templates: `_review-dispatch.md.j2`、`_output-format-eval.md.j2`、`_ci-verification.md.j2`
- 根级模板: `evaluation.md.j2`、`contract.md.j2`、`spec.md.j2`
- 静态文件: `calibration.md`、`calibration.zh.md`
- AC: 这些文件不再存在；`harness install --force` 正常工作

### D5: 清理 init.py 和 memverse.py
- `init.py`: 移除 `tmpl.render()` 中无用的 `workflow_mode` 和 `memverse_driver` 参数
- `memverse.py`: 移除 `create_memverse` 的 `driver` 参数
- AC: init 流程正常；`create_memverse(enabled=True)` 不需要 driver 参数

### D6: 清理 state.py docstring
- 更新 `StopContext` docstring：移除 "autonomous loop" 引用，改为 "when a task is stopped"
- AC: docstring 不再引用 "autonomous loop"

### D7: 重构 README（EN + ZH）
- 移除 "Upgrading from 3.x" / "从 3.x 升级" 段落
- 标题描述改为强调 Cursor-native 定位
- Parallel Development 简化为一段功能简介（保留）
- 配置表格与 `NativeModeConfig` 实际字段对齐
- 添加 "Historical documentation" 链接指向 `docs/historical.md`
- AC: README 无迁移指南；标题和描述突出 Cursor-native 定位

### D8: 文档清理与归档
- 删除: `docs/compatibility.md`、`docs/state-machine.md`、`docs/project-vision.md` 及 `docs/zh-CN/` 下对应中文版
- 新增: `docs/historical.md` 归档旧内容要点
- `ARCHITECTURE.md`: 修正 "SCORING_DIMENSIONS used in templates" 描述；更新 registry/events 相关段落
- AC: docs/ 下不再有描述旧 CLI/driver 架构的活跃文档；ARCHITECTURE.md 与代码实际匹配

### D9: 测试对齐
测试文件 → Deliverable 映射：
| 测试文件 | 影响来源 | 需要的变更 |
|----------|---------|-----------|
| `test_registry.py` | D2 | 更新 `RunTracker`/`EventEmitter` 的 driver 默认值用法 |
| `test_ui.py` | D2 | 移除 `test_system_status_shows_ide` 中 Codex 断言；移除 strategist 测试 |
| `test_status.py` | D2 | 移除 Driver 列断言（如有） |
| `test_init.py` | D5 | 验证 memverse_driver 移除后 init 仍正常 |
| `test_install.py` / `test_skill_gen_extended.py` | D3/D4 | 验证模板删除后 install 仍正常 |
| `test_state.py` | D6 | 无代码变更（仅 docstring），可能无影响 |
| `test_progress.py` | — | 检查 mode="run"/"auto" 引用是否需更新 |
- AC: `python -m pytest tests/ -v` 全部通过；无测试引用已删除的模块

## Suggested Commit Structure

1. `chore: remove dead modules (retry, archive, index)`
2. `refactor: clean driver remnants and add DEFAULT_DRIVER constant`
3. `fix: branch_prefix template separator`
4. `chore: remove orphan templates`
5. `refactor: clean init.py and memverse.py unused params`
6. `docs: rewrite README for Cursor-native branding`
7. `docs: archive historical docs, update ARCHITECTURE.md`
8. `test: align tests with code cleanup`

## Acceptance Criteria

- 所有测试通过（`python -m pytest tests/ -v`）
- `ruff check src/ tests/` 无新增 lint 错误
- `harness install --force` 正常工作
- 无功能回归（harness init, install, status, update 全部正常）
- README 清晰反映 Cursor-native 定位，无 orchestrator 时代残留

## Out of Scope

- SQLite schema 迁移（不改 registry.db 的表结构）
- i18n 死键清理（`init.opt_custom`, `update.config_new_key`）——影响小，留待后续
- config.toml.j2 扩展（添加 `plan_review_gate`/`hooks`/`role_models` 等字段）——属于功能增强
- PyPI README rendering 优化
- `SessionState.mode` 值重命名（`run`/`auto` → 其他）——影响面大，需单独评估

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected Alternative |
|---|-------|----------|---------------|-----------|-----------|---------------------|
| 1 | Approach | 保留 Registry `driver` 列但引入 DEFAULT_DRIVER 常量 | Mechanical | #3 Pragmatic + #4 DRY | Schema 迁移破坏现有 DB；单常量避免 hardcode 散落 | 删除 driver 列 / 多处 hardcode "cursor" |
| 2 | Approach | events.py/tracker.py 保留并清理（非删除） | Mechanical | #1 Completeness | 被 test_registry 的 RunTracker 路径使用 | 删除后重写 registry 测试 |
| 3 | Approach | 合并旧 docs 为归档文件 + README 链接 | Taste | #3 Pragmatic | 旧内容有历史参考价值但不应作为活跃文档 | 逐一更新 / 直接删除 |
| 4 | Approach | 移除 README 迁移段落 | Mechanical | #5 Explicit | 无现有用户需要迁移 | 保留迁移指南 |
| 5 | Approach | 修复 branch_prefix 用 rstrip + `/` | Mechanical | #1 Completeness | 防止配置带尾斜杠时产生 `//` | 仅在模板中加 `/` |
| 6 | Approach | README 品牌重塑 "Cursor-native AI engineering framework" | Taste | #5 Explicit | 突出差异化定位 | 保持现有描述 |
| 7 | Approach | Parallel Development 简化保留 | Taste | #3 Pragmatic | 功能仍存在，只是去除冗余描述 | 完全删除该段落 |

---

## Plan Review Summary

### Round 1 — 5-Role Review (Score: 7.4/10)

| Role | Score | Verdict |
|------|-------|---------|
| Architect | 8/10 | ISSUES_FOUND |
| Product Owner | 8/10 | ISSUES_FOUND |
| Engineer | 8/10 | ISSUES_FOUND |
| QA | 6/10 | ISSUES_FOUND |
| Project Manager | 7/10 | ISSUES_FOUND |

**[HIGH CONFIDENCE] events.py/tracker.py 终态不明确**（4/5 角色指出）：
→ 已修复：新增「文件终态速查表」明确每个文件的处理方式

**已采纳的改进：**
1. 分离"完全无调用方"（D1: 删除）和"仅生产代码无调用方"（D2: 保留清理）
2. D6 AC 收窄为仅改 docstring（可测）
3. D7 明确 Parallel Development 保留并简化（非开放决策）
4. D8 增加入口文档指向历史归档的链接
5. 引入 `DEFAULT_DRIVER` 常量避免 hardcode 散落
6. branch_prefix 在 skill_gen 中 rstrip("/") 防双斜杠
7. 新增 commit 结构建议
8. D9 新增测试文件 → Deliverable 映射表
