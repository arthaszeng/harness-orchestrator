# B6 — Parallel Task Isolation + Worktree-Aware Status

> Vision 路线：W2 backlog item B6（最终项）
> 依赖：B1（canonical workflow state，已完成 PR #46）

## Spec

### Analysis

Cursor Parallel Agents 通过 git worktree 创建独立工作副本，每个 worktree
通过 `.cursor/worktrees.json` 中的 setup 脚本复制 `.agents/` 和 `.cursor/`。

当前存在三个隔离问题：

1. **Session state 串线** — `.agents/state.json` 在 worktree 创建时被复制，
   之后各 worktree 独立写入。但 `SessionState.load/save` 和 `status` 命令
   都假设 `.agents/state.json` 是当前工作空间的唯一会话，无法区分"这是哪个
   worktree 的会话"。
2. **Task 解析依赖"最新编号"** — `resolve_task_dir` 在无 session hint 时
   fallback 到数字最大的 `task-NNN`，在并行环境中可能选到另一个 worktree
   正在使用的任务。
3. **Status 无 worktree 感知** — `harness status` 不显示 worktree 身份、
   不隔离查询范围。

### Approach

**核心策略：worktree 感知的 task 绑定 + 环境变量隔离 + status 增强**

1. **`HARNESS_TASK_ID` 环境变量** — 在 `resolve_task_dir` 中作为最高优先级
   来源。Cursor parallel agent worktree 的 setup 脚本可以设置此变量。
   这避免了"最新编号"误选。
2. **Worktree 检测工具函数** — `detect_worktree() -> WorktreeInfo | None`，
   返回 `is_worktree: bool`、`common_dir: Path`、`git_dir: Path`。
   供 status、skill templates、workflow_state 使用。
3. **Status 增强** — worktree 模式下显示 worktree 标识（分支名或路径），
   并限定任务查询范围到 `HARNESS_TASK_ID`（如设置）。
4. **worktrees.json 增强** — setup 脚本中导出 `HARNESS_TASK_ID`
   以便自动绑定（需要 worktree 创建时知道 task-id，这在 Cursor 流程中
   通过分支名 `agent/task-NNN-*` 推断）。

**拒绝的替代方案：**
- 完整的分布式锁/文件锁：过于复杂，Cursor worktree 是短生命周期
- 修改 `state.json` 为多会话结构：破坏现有 schema，向后兼容代价高
- 进程级 IPC 协调：超出"仓库内可查询的流程语义"定位

### Impact

- `src/harness/core/workflow_state.py` — `resolve_task_dir` 增加 env 优先级
- `src/harness/core/worktree.py` — 新模块：worktree 检测
- `src/harness/commands/status.py` — worktree 标识显示 + task 范围限定
- `src/harness/native/skill_gen.py` — `_WORKTREES_JSON` setup 脚本增强
- `tests/` — 新增 worktree 检测 + 隔离测试

### Risks

| 风险 | 概率 | 缓解 |
|------|------|------|
| worktrees.json 变更后现有 worktree 不更新 | 中 | 文档说明 `harness update --force` 可刷新 |
| HARNESS_TASK_ID 未设置时 fallback 行为变化 | 低 | 保留现有"最新编号" fallback 不变 |
| 分支名解析 task-id 失败 | 低 | 只作为 best-effort hint，失败时不设置变量 |

---

# Contract

## Deliverables

### D1: Worktree 检测模块
- 新增 `src/harness/core/worktree.py`
- `detect_worktree() -> WorktreeInfo | None`：比较 `git rev-parse --git-common-dir`
  和 `--git-dir`，不等则为 worktree
- `WorktreeInfo` dataclass：`is_worktree`, `common_dir`, `git_dir`, `branch`
- 复用 `integrations/git_ops._run_git` 或抽取共享 git subprocess helper，
  避免与 `git_ops` 重复超时/错误处理风格
- 调用者需传入 `cwd`（默认 `Path.cwd()`），确保 repo root 明确
- **验收标准：** 非 worktree 返回 None；mock worktree 环境返回正确 info；
  git 失败/超时返回 None（不抛异常）

### D2: HARNESS_TASK_ID 环境变量支持
- 在 `resolve_task_dir` 中增加 `env_task_id` 参数，默认从
  `os.environ.get("HARNESS_TASK_ID")` 读取
- 优先级：`explicit_task_id` → `env_task_id` → `session_task_id` → 最新编号
- `env_task_id` 与 `explicit_task_id` 享有同等安全验证（`_safe_child`、
  `^task-\d+$`）；非法值（traversal、非 task 格式）被拒绝并 fallback
- **`load_current_workflow_state` 适配：** 当 `env_task_id` 命中时，
  视为与 `explicit_task_id` 同等权威——跳过 session mismatch guard，
  避免 worktree 中复制的 `state.json` 内旧 session_task_id 导致
  整段 workflow 状态被清空
- 同步检查 `progress.py` 等所有 `load_current_workflow_state` 调用路径
- **验收标准：** 设置 `HARNESS_TASK_ID=task-005` 后 resolve 返回该目录；
  `load_current_workflow_state` 在 env 命中时不受 session mismatch 影响；
  traversal/非法值被拒绝；未设置时行为不变

### D3: Status worktree 感知
- `run_status` 调用 `detect_worktree()`
- worktree 模式下显示 `[Worktree: <branch>]` 标识
- 如有 `HARNESS_TASK_ID`，优先使用其限定任务范围
- **验收标准：** worktree 环境显示标识；非 worktree 无变化

### D4: worktrees.json 增强
- setup-worktree-unix 脚本中增加 `HARNESS_TASK_ID` 导出逻辑：
  从当前分支名 `agent/task-NNN-*` 提取 `task-NNN`
- setup-worktree-windows 同步更新
- **验收标准：** 生成的 worktrees.json 包含 task-id 提取命令

### D5: 测试 + 文档
- worktree 检测：正常环境 + mock worktree
- HARNESS_TASK_ID：优先级测试（env > session > latest）
- status worktree 显示
- worktrees.json 内容断言
- ARCHITECTURE.md 更新
- **验收标准：** 全部测试通过；新增 ≥ 6 个测试

## Acceptance Criteria
- 所有测试通过（预期 ≥ 435，当前基线 429）
- ruff lint clean
- 非 worktree 环境行为完全不变（零回归）
- worktree 环境中 HARNESS_TASK_ID 正确隔离 task 解析
- `harness status` 在 worktree 中显示身份标识

## Out of Scope
- 分布式文件锁 / 进程间协调
- `state.json` schema 变更
- 多会话并发写入保护
- Cursor parallel agent 创建 UI/API（由 Cursor 控制）
- 跨 worktree 任务聚合视图

## Commit Strategy
1. `feat(core): worktree detection module` — D1
2. `feat(workflow): HARNESS_TASK_ID env support in resolve_task_dir` — D2
3. `feat(status): worktree-aware status display` — D3
4. `feat(native): enhance worktrees.json with task-id export` — D4
5. `test(isolation): parallel task isolation tests + docs` — D5

## Stop Conditions
- 大面积测试失败（> 5 个非新测试 fail）→ 回退
- `resolve_task_dir` 变更导致现有测试的 fallback 逻辑中断 → 审查优先级链
- git subprocess 在 CI 中行为不一致 → 将 git 调用改为可 mock

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected Alternative |
|---|-------|----------|---------------|-----------|-----------|---------------------|
| 1 | Architecture | 环境变量隔离而非文件锁 | Mechanical | #3 务实 | Cursor worktree 短生命周期，env 足够 | 分布式文件锁 |
| 2 | Architecture | 新增 worktree.py 模块而非嵌入 workflow_state | Mechanical | #5 显式优于巧妙 | 关注点分离：worktree 检测是独立能力 | 内嵌到 workflow_state.py |
| 3 | Scope | 保留 state.json 单会话 schema | Mechanical | #4 DRY | 避免 schema 迁移和向后兼容代价 | 多会话 state.json |
| 4 | Integration | 从分支名推断 task-id 作为 best-effort | Taste | #1 完整性 | 自动化优先，失败静默降级 | 要求用户手动设置 env |
