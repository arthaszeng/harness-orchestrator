[中文版](zh-CN/compatibility.md)

# Runtime Compatibility Matrix

Harness depends on the Cursor CLI and/or Codex CLI for actual agent capability. This document records validated version ranges and known limitations.

## Cursor CLI

| Item | Details |
|------|------|
| **Minimum version** | A version that supports `cursor agent --print --output-format stream-json` |
| **Required flags** | `--print`, `--trust`, `--output-format stream-json`, `--stream-partial-output`, `--approve-mcps` |
| **Read-only mode** | `--mode plan` |
| **Write mode** | `--force` |
| **Installation** | Cursor editor → Command Palette → `Install 'cursor' command` |

### Known limitations

- The `cursor agent` subcommand requires the Cursor editor to be signed in with an active Pro subscription
- `--stream-partial-output` may be unavailable in older versions
- `stream-json` event shapes can differ slightly across versions; Harness falls back on lines it cannot parse

## Codex CLI

| Item | Details |
|------|------|
| **Minimum version** | A version that supports `codex exec --full-auto --output-last-message` |
| **Required flags** | `--full-auto`, `--color never`, `--output-last-message <file>`, `-C <dir>`, `-` (stdin mode) |
| **Installation** | `npm install -g @openai/codex` or from [GitHub](https://github.com/openai/codex) |

### Known incompatibilities

| Change | Impact | Harness mitigation |
|------|------|-------------|
| `codex exec --agent` entry removed | Cannot select a role via `--agent` | Harness parses `developer_instructions` from TOML and concatenates them into the stdin prompt |
| `--output-last-message` file is empty | Final reply cannot be read | Fallback to stdout streamed output |

## Version detection

Harness runs an automatic capability probe at startup:

1. `codex --version` / `cursor --version` — detect version numbers
2. `codex exec --help` / `cursor agent --help` — verify critical flags exist
3. On incompatibility, print a warning without blocking execution

Use `harness status` to inspect probe results.

## Python environment

| Dependency | Minimum version |
|------|----------|
| Python | >= 3.9 |
| typer | >= 0.12 |
| pydantic | >= 2.0 |
| jinja2 | >= 3.1 |
| rich | >= 13.0 |
