# Runtime Compatibility Matrix

Harness 依赖 Cursor CLI 和/或 Codex CLI 提供实际 agent 能力。本文档记录已验证的版本范围和已知限制。

## Cursor CLI

| 项目 | 详情 |
|------|------|
| **最低版本** | 支持 `cursor agent --print --output-format stream-json` 的版本 |
| **必需 flags** | `--print`, `--trust`, `--output-format stream-json`, `--stream-partial-output`, `--approve-mcps` |
| **只读模式** | `--mode plan` |
| **写入模式** | `--force` |
| **安装方式** | Cursor 编辑器 → 命令面板 → `Install 'cursor' command` |

### 已知限制

- `cursor agent` 子命令需要 Cursor 编辑器已登录且 Pro 订阅有效
- `--stream-partial-output` 在较旧版本中可能不可用
- 部分版本的 `stream-json` 事件格式可能有细微差异；Harness 对无法解析的行做 fallback 处理

## Codex CLI

| 项目 | 详情 |
|------|------|
| **最低版本** | 支持 `codex exec --full-auto --output-last-message` 的版本 |
| **必需 flags** | `--full-auto`, `--color never`, `--output-last-message <file>`, `-C <dir>`, `-`（stdin 模式） |
| **安装方式** | `npm install -g @openai/codex` 或从 [GitHub](https://github.com/openai/codex) |

### 已知不兼容项

| 变更 | 影响 | Harness 应对 |
|------|------|-------------|
| `codex exec --agent` 入口已移除 | 无法通过 `--agent` 指定角色 | Harness 将 `developer_instructions` 从 TOML 解析后直接拼接进 stdin prompt |
| `--output-last-message` 文件为空 | 无法获取最终回复 | fallback 到 stdout 流式输出内容 |

## 版本检测

Harness 在启动时自动执行 capability probe：

1. `codex --version` / `cursor --version` — 检测版本号
2. `codex exec --help` / `cursor agent --help` — 验证关键 flag 存在
3. 不兼容时打印 warning，不阻塞执行

可通过 `harness status` 查看检测结果。

## Python 环境

| 依赖 | 最低版本 |
|------|----------|
| Python | >= 3.11 |
| typer | >= 0.12 |
| pydantic | >= 2.0 |
| jinja2 | >= 3.1 |
| rich | >= 13.0 |
