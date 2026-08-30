# 14 · 会话模式（ask / plan / agent）

三种模式共用同一条 `AgentLoop` 状态机（03），**不**新开循环、**不**增加第 8 个工具。差别在：发给模型的 `tools` 子集、system 口径、执行层拒绝、输入框前缀。默认 **agent**（与 v2 行为一致）。

## 1. 三种模式

| 模式 | 用户在做什么 | 模型可以调用 | 最终回复 |
|------|----------------|--------------|----------|
| **ask** | 问代码、问仓库 | 只读四件：`read_file` `list_dir` `glob_search` `grep` | 解答。不改磁盘、不写计划 |
| **plan** | 目标往往含糊 | 同上只读四件 | 每次只问一个问题（给序号选项，用户也可自定义）；信息够了则输出内部计划文档 |
| **agent** | 要落地改代码 | 全部 7 个工具 | 改文件、跑命令，直到任务完成 |

`bash` / `write_file` / `edit_file` 在 ask 与 plan 中：请求 schema **不发给模型**；若解析兜底仍抽出这些调用，`ToolExecutor` 返回失败 ToolResult 并回灌，磁盘不变。

## 2. 计划流程（对齐 Cursor Plan，落在终端）

不在一次 `run()` 里卡住等人确认：模型用「无工具 + 非空 content」自然结束一轮，TUI/REPL 回到输入框。这就是逐题确认。

1. 用户在 plan 模式写下模糊目标。
2. 模型可用只读工具摸仓库，然后**本条回复只问一个问题**。有把握时给 2–4 个编号选项，并写明也可以直接输入自己的答案。
3. 用户在输入框打序号或自定义文字，Enter。对话历史保留，下一轮继续。
4. 信息足够后，停止提问，输出 Markdown，**第一行必须是** `# 计划`。正文含：目标、现状、做法、要改的文件、步骤、风险、如何验证。对话里的助手最终回复按 Markdown 渲染（标题、列表、粗体、代码块）。
5. `AgentSession.ask` 若看到这份文档，写入 `session.plan_document`（内存，不写进仓库）。`/mode agent` 时 `rebuild_system` 把该文档注入 system。随后用户说「按这个做」或直接下达任务即可落地。

`/reset` 清空对话，**保留** `plan_document`（内部文档不是一轮聊天）。新的 `# 计划` 覆盖旧文档。

不做：计划画布、编辑计划文件、`run()` 中途 y/n 门闩。那些要拆工作线程，不属于本版。

## 3. 切换

- `/mode`：全屏单选列表；REPL 打印当前模式。
- `/mode ask|plan|agent`（别名：问答 / 计划 / 代理）立即切换并重写 system。
- 输入框最前方用颜色标当前模式名（`ask` 冰蓝、`plan` 金、`agent` 绿），其后仍是 `∼ wavecode ›`。
- CLI：`--mode ask|plan|agent`（`WAVEMIO_MODE`）。一次性 `run` 默认仍是 agent。

## 4. 代码落点

| 位置 | 做什么 |
|------|--------|
| `agent/mode.py` | 名称、别名、只读集合、计划文档判定、占位文案、颜色 |
| `config/settings.py` | `mode: ask\|plan\|agent` |
| `app/system_prompt.py` | 按 mode 换规则；可选注入 `plan_document` |
| `tools/registry.py` | `schemas(allowed)` / `names(allowed)` |
| `tools/executor.py` | `mode`；拒绝不在白名单的调用 |
| `agent/loop.py` | `_build_request` 只带允许的 tools；`sync_runtime_settings` 同步 executor.mode |
| `agent/session.py` | `plan_document`；plan 自然结束时捕获；`rebuild_system` 带 mode |
| `cli/commands.py` | `/mode` |
| `cli/picker.py` | `mode_picker` |
| `cli/tui.py` | 输入条前缀着色；助手回复 Markdown；斜杠命令补全 |
| `cli/repl.py` | 提示符同样前缀 |
