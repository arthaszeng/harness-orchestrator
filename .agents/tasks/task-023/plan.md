# Vision Completion Cleanup — 审计发现修复

> 来源：Vision B1–B6 完成后的审计报告
> 类型：chore + fix（无新功能，纯清理与对齐）

## Spec

### Analysis

Vision B1–B6 全部交付后，审计发现 6 个遗留问题：

1. **task-017 backlog 状态未同步** — B1 仍标记 `SELECTED`，B2–B6 仍为 `PENDING`，
   但全部已交付（PR #46–#51）。审计轨迹断裂。
2. **B4 遗留 `_build_context` 兼容包装** — `skill_gen.py` 中 `_build_context` 标记
   `TODO(B4-compat): remove after test migration`，20 个测试调用仍使用它。
   应迁移到 `_build_full_context` 或 `_build_layered_context` 并删除包装。
3. **`_build_context` 中 `role="planner"` 硬编码逻辑** — 包装中 `pop("builder_principles")`
   的角色过滤逻辑已被 `_ARTIFACT_LAYERS` 取代，是死代码。
4. **handoff Python API 缺乏生产路径引用** — `save_handoff`/`load_handoff`/`load_latest_handoff`
   仅在测试中调用，但 `__init__.py` 或 `__all__` 未导出，discoverable 性差。
   应从 `core/__init__.py` 或 `handoff.py` 的 `__all__` 中明确导出。
5. **vision.md 缺少完成标记** — 没有在 vision 文档中记录 W1+W2 完成里程碑。
6. **ARCHITECTURE.md 中 `_run_git` 引用已过时** — B6 将 `_run_git` 提升为 `run_git`，
   但如果文档中仍有 `_run_git` 引用需要对齐。

这些都是确定性修复，不涉及行为变更。

### Approach

**纯文档/代码清理，无功能变更。**

1. 更新 `task-017/plan.md` backlog 状态为 `DONE`
2. 迁移 20 个测试从 `_build_context` 到 `_build_full_context`，删除 `_build_context` 包装
3. 确保 `handoff.py` 有 `__all__` 导出公共 API
4. 在 `vision.md` 追加 W1+W2 完成里程碑条目
5. 检查 ARCHITECTURE.md 中是否有陈旧引用

### Impact

- `.agents/tasks/task-017/plan.md` — backlog 状态更新
- `.agents/vision.md` — 追加里程碑
- `src/harness/native/skill_gen.py` — 删除 `_build_context` 包装
- `src/harness/core/handoff.py` — 添加 `__all__`
- `tests/test_skill_gen_extended.py` — 迁移 `_build_context` 调用
- `tests/test_gate_thresholds.py` — 迁移 `_build_context` 调用
- `ARCHITECTURE.md` — 如有陈旧引用则更新

### Risks

| 风险 | 概率 | 缓解 |
|------|------|------|
| 迁移 `_build_context` 导致测试失败 | 低 | `_build_full_context` 是超集，逐个验证 |
| backlog 更新遗漏某个 item | 极低 | 逐项对照 PR 编号 |

---

# Contract

## Deliverables

### D1: task-017 Backlog 状态同步
- 更新 B1–B6 状态为 `DONE`，附 PR 编号
- **验收标准：** 每个 B-item 状态为 `DONE` 且有对应 PR 引用

### D2: 删除 `_build_context` 兼容包装
- 迁移 `tests/test_skill_gen_extended.py` 中常规调用到 `_build_full_context`
- 迁移 `tests/test_gate_thresholds.py` 中 2 处调用
- **特殊处理：** `test_build_context_planner_strips_builder_principles` — 删除此测试。
  `role="planner"` 的 `pop("builder_principles")` 逻辑从未在生产路径使用，
  layered context 路径 `_ARTIFACT_LAYERS` 中 plan skills 使用 layer {0,1,2}，
  包含 `builder_principles` 是正确行为（plan skill 需要看到构建原则来制定合理计划）
- **特殊处理：** `test_build_context_compat_wrapper_has_all_keys` — 改为断言
  `_build_full_context` 返回键集是 `_build_layered_context` 任意具体 artifact 键集的超集
- 删除 `skill_gen.py` 中的 `_build_context` 函数
- **验收标准：** `_build_context` 不再存在于代码库中；所有测试通过；
  planner-specific 测试已删除或转为 layered 等价断言

### D3: handoff.py 公共 API 导出
- 添加 `__all__` 到 `handoff.py`，导出 `StageHandoff`, `save_handoff`,
  `load_handoff`, `load_latest_handoff`
- **验收标准：** `handoff.py` 有 `__all__`；导出列表覆盖公共 API

### D4: vision.md 完成里程碑
- 追加 `[2026-04-02] — W1 + W2 Vision Backlog Complete` 条目
- 简要记录 B1–B6 交付摘要
- 在 Success Signals 段中标注 W1/W2 已通过 B1–B6 完成
- **验收标准：** vision.md 包含完成里程碑且 PR 引用正确；
  Success Signals 有完成标记或链接到里程碑

### D5: ARCHITECTURE.md 陈旧引用检查
- 如有 `_run_git` 或其他已过时引用，更新
- **验收标准：** 无已知陈旧 API 引用

## Acceptance Criteria
- 所有 449+ 测试通过
- ruff lint clean
- `_build_context` 函数不再存在
- task-017 backlog 状态全部 DONE
- vision.md 有完成里程碑

## Out of Scope
- 新功能开发
- B5 memory pack 深化（需要独立 backlog item）
- Ship gate 自动拦截（需要架构决策）
- Handoff 的 CLI/生产路径集成（需要设计）

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected Alternative |
|---|-------|----------|---------------|-----------|-----------|---------------------|
| 1 | Scope | 只做确定性清理，不做功能增强 | Mechanical | #3 务实 | 审计发现都是机械性修复 | 同时做 B5 深化 |
| 2 | Migration | 直接迁移到 `_build_full_context` | Mechanical | #4 DRY | `_build_context` 是冗余包装 | 保留并标记 deprecated |
| 3 | Export | `__all__` 而非 `__init__` re-export | Mechanical | #5 显式 | 模块级导出更清晰 | 从 core/__init__.py 导出 |
