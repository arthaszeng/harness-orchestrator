# 预着陆评审清单

## 说明

评审 `git diff main..HEAD` 输出，查找以下列出的问题。要具体 — 引用 `file:line` 并建议修复。跳过没问题的内容。只标记真正的问题。

**两遍评审：**
- **第 1 遍（CRITICAL）：** 先运行 SQL 和数据安全、竞态条件、LLM 输出信任边界、Shell 注入和枚举完整性。最高严重度。
- **第 2 遍（INFORMATIONAL）：** 运行以下剩余类别。较低严重度但仍需处理。
- **专家类别（由并行子代理处理，不是本清单）：** 测试缺口、死代码、魔法数字、性能和包大小影响。见 `specialists/`。

所有发现通过 Fix-First Review 获得处理：明显的机械性修复自动应用，
真正有歧义的问题批量合入一个用户问题。

**输出格式：**

```
Pre-Landing Review: N issues (X critical, Y informational)

**AUTO-FIXED:**
- [file:line] Problem → fix applied

**NEEDS INPUT:**
- [file:line] Problem description
  Recommended fix: suggested fix
```

如果没有发现问题：`Pre-Landing Review: No issues found.`

要简洁。每个问题：一行描述问题，一行给出修复。不要前言、不要总结、不要"整体看起来不错"。

---

## 置信度校准

每个发现必须包含置信度评分（1-10）：

| 分数 | 含义 | 显示规则 |
|------|------|----------|
| 9-10 | 通过阅读具体代码验证。演示了具体的 bug 或漏洞。 | 正常显示 |
| 7-8 | 高置信度模式匹配。很可能正确。 | 正常显示 |
| 5-6 | 中等。可能是误报。 | 带提示显示："中等置信度 — 验证这是否确实是问题" |
| 3-4 | 低置信度。模式可疑但可能没问题。 | 从主报告中隐藏。仅包含在附录中。 |
| 1-2 | 推测。 | 仅在严重度为 CRITICAL 时报告。 |

**发现格式：**

`[SEVERITY] (confidence: N/10) file:line — description`

示例：
`[CRITICAL] (confidence: 9/10) app/models/user.py:42 — SQL injection via string interpolation in where clause`
`[INFORMATIONAL] (confidence: 5/10) app/services/gen.py:88 — Possible N+1 query, verify with production logs`

---

## 评审类别

### 第 1 遍 — CRITICAL

#### SQL 和数据安全
- SQL 中的字符串插值（即使值被转换 — 使用参数化查询）
- TOCTOU 竞态：检查-再-设置模式应该是原子 `WHERE` + `UPDATE`
- 绕过 ORM 验证的直接数据库写入
- N+1 查询：循环/视图中使用的关联缺失 eager loading

#### 竞态条件和并发
- 没有唯一约束或重复键错误处理的读-检查-写
- 没有唯一数据库索引的 find-or-create — 并发调用可能创建重复
- 不使用原子 `WHERE old_status = ? UPDATE SET new_status` 的状态转换
- 用户控制数据的不安全 HTML 渲染（XSS）

#### LLM 输出信任边界
- LLM 生成的值未经格式验证就写入数据库或传递给邮件程序
- 结构化工具输出在数据库写入前未进行类型/形状检查
- LLM 生成的 URL 未经允许列表过滤就被获取 — SSRF 风险
- LLM 输出未经清理就存储在知识库中 — 存储型 prompt 注入

#### Shell 注入
- `subprocess.run()` / `subprocess.call()` / `subprocess.Popen()` 使用 `shell=True` 且 f-string 插值 — 使用参数数组替代
- `os.system()` 带变量插值 — 替换为使用参数数组的 `subprocess.run()`
- 对 LLM 生成的代码使用 `eval()` / `exec()` 但无沙箱

#### 枚举和值完整性
当 diff 引入新的枚举值、状态字符串、层级名或类型常量时：
- **追踪所有消费者。** 读取每个 switch/filter/display 该值的文件。如果任何消费者未处理新值，标记它。
- **检查允许列表/过滤数组。** 搜索包含兄弟值的数组，验证新值在需要的地方被包含。
- **检查 `match`/`if-elif` 链。** 如果现有代码按枚举分支，新值是否会落入错误的 default？

### 第 2 遍 — INFORMATIONAL

#### 异步/同步混合
- `async def` 端点内的同步 `subprocess.run()`、`open()`、`requests.get()` — 阻塞事件循环
- 异步函数内的 `time.sleep()` — 使用 `asyncio.sleep()`
- 异步上下文中未用 `run_in_executor()` 包装的同步数据库调用

#### 列/字段名安全
- 验证 ORM 查询中的列名与实际数据库 schema 一致 — 错误的名称会静默返回空结果
- 检查查询结果的 `.get()` 调用使用的是实际选择的列名

#### 死代码和一致性
- PR 标题与 VERSION/CHANGELOG 文件之间的版本不匹配
- CHANGELOG 条目不准确地描述变更

#### LLM Prompt 问题
- prompt 中使用 0-indexed 列表（LLM 可靠地返回 1-indexed）
- Prompt 文本列出的可用工具与实际接线的不匹配
- 在多个地方声明的 word/token 限制可能会漂移

#### 完整性缺口
- 完整版本实现成本 <30 分钟的捷径实现
- 添加缺失测试很直接的测试覆盖缺口
- 功能实现了 80-90% 但用适度的额外代码可以达到 100%

#### 时间窗口安全
- 假设"今天"覆盖 24 小时的日期键查找
- 相关功能之间不匹配的时间窗口

#### 边界处的类型转换
- 值跨越语言/序列化边界时类型可能变化
- 序列化前未归一化类型的 hash/digest 输入

#### 视图/前端
- 模板中的内联 `<style>` 块（每次渲染都重新解析）
- 视图中的 O(n*m) 查找（循环中的线性搜索而非 dict/set）

#### 发布和 CI/CD 管线
- CI/CD 工作流变更：验证构建工具版本、产物路径、密钥处理
- 新产物类型：验证存在发布/release 工作流
- VERSION 文件、git tags 和发布脚本之间的版本标签格式一致性

---

## 严重度分类

```
CRITICAL (最高严重度):           INFORMATIONAL (主代理):
├─ SQL 和数据安全                ├─ 异步/同步混合
├─ 竞态条件和并发                ├─ 列/字段名安全
├─ LLM 输出信任边界              ├─ 死代码（仅版本）
├─ Shell 注入                   ├─ LLM Prompt 问题
└─ 枚举和值完整性                ├─ 完整性缺口
                                ├─ 时间窗口安全
                                ├─ 边界处的类型转换
                                ├─ 视图/前端
                                └─ 发布和 CI/CD 管线
```

---

## Fix-First 启发式

```
AUTO-FIX (代理自行修复):              ASK (需要人工判断):
├─ 死代码 / 未使用变量                ├─ 安全（认证、XSS、注入）
├─ N+1 查询（缺失 eager loading）     ├─ 竞态条件
├─ 与代码矛盾的过时注释              ├─ 设计决策
├─ 缺失的 LLM 输出验证               ├─ 大型修复（>20 行）
├─ 版本/路径不匹配                   ├─ 枚举完整性
├─ 赋值但从未读取的变量              ├─ 移除功能
└─ 内联样式、O(n*m) 视图查找        └─ 任何改变用户可见行为的
```

**经验法则：** 如果修复是机械性的且资深工程师会不经讨论就应用它，
它就是 AUTO-FIX。如果合理的工程师对修复可能有不同意见，
它就是 ASK。

---

## 抑制 — 不要标记这些

- 当冗余无害且有助于可读性时的"X 与 Y 冗余"
- "添加注释解释为什么选择这个阈值" — 阈值会变，注释会腐烂
- 当断言已经覆盖行为时的"这个断言可以更严格"
- 没有功能性好处的仅一致性变更建议
- 当输入被约束且 X 永远不会发生时的"正则不处理边界情况 X"
- Eval 阈值变更 — 这些是凭经验调整的
- 无害的空操作
- diff 中已经处理的任何内容 — 在评论之前阅读完整 diff
