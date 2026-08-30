# 00 · 产品概述与第一版范围

## 1. 一句话

**Wavemio** 是一个用 Python 手写的命令行编程智能体：用户用自然语言下达编程任务，程序把对话发给 DeepSeek，根据模型返回的 **原生 tool calls** 在本地读写文件、搜索、执行命令，再把结果送回模型，直到任务完成或命中终止条件。名字取 wave（浪）与 mio／澪（航道）；CLI 吉祥物为社区二创 **鲸鱼娘**，以终端像素风动态绘制（见 09、12）。

它不是聊天机器人套一层终端，而是一个 **可扩展的 Agent Runtime**：CLI 只是第一种前端。

版本号见 [CHANGELOG.md](./CHANGELOG.md)，格式 `v大功能.小功能.小bug`。当前设计基线为 **v0.1.0**；第一次可运行实现合并进主线时升 **大功能** 到 `v1.0.0`。

## 2. 题目映射（必须全部覆盖）

| 题目要求 | 本设计落点 |
|----------|------------|
| 与大模型交互 | `DeepSeekClient` + Chat Completions |
| 自主读写文件、执行命令 | Tool 家族 + `ToolExecutor` |
| 对话历史与上下文管理 | `ContextManager` + `ContextPolicy` |
| 工具的定义与本地执行 | `Tool` ABC + `ToolRegistry` + 工作区沙箱 |
| 模型输出的解析 | `OutputParser` 管道（原生 + 兜底 + JSON 修复） |
| 循环终止条件 | `TerminationCondition` 组合 |
| 错误处理 | 异常谱系 + 重试策略 + 工具错误回灌 |
| 不用 agent 框架 | 组合根 `bootstrap.py` 手写接线 |
| 凭据不入库 | `pydantic-settings` 只读 `DEEPSEEK_API_KEY` |

## 3. 产品形态

- **形式**：CLI。进程内运行 Agent 循环，**第一版不做 HTTP 后端服务**。
- **启动**：
  - 交互：`wavemio` 或 `python -m coding_agent`
  - 单次：`wavemio run "在当前目录写一个 hello.py"`
- **主色**：蓝。吉祥物为像素风鲸鱼娘动态立绘（见 09、12），**不要** ASCII 机器猫。
- **模型**：DeepSeek 官方 API。
  - 默认：`deepseek-v4-flash`（快、适合工具循环演示）
  - 可配：`deepseek-v4-pro`（质量优先）；运行时 `/model` 勾选切换（有密钥则 `GET /models`，只列文本模型 id，不含视觉）
  - 兼容别名：若用户配置了已退役的 `deepseek-chat`，启动时打印警告并映射到 `deepseek-v4-flash` + `thinking.disabled`。
  - 无 thinking 的模型：HUD / `/help` / `/status` 不显示 thinking 开关。
- **API**：
  - Base URL：`https://api.deepseek.com`
  - 路径：`POST /chat/completions`（`/v1` 也可，实现时统一写成 `base_url.rstrip('/') + '/chat/completions'`）
  - 认证：`Authorization: Bearer $DEEPSEEK_API_KEY`
  - 工具：请求体 `tools` + 响应 `choices[0].message.tool_calls`（OpenAI 兼容，**本地执行**）

## 4. 第一版范围（V1 Freeze）

**做：**

- REPL 与 one-shot 两种入口
- 流式输出（content / reasoning_content / tool_calls 增量拼接）
- 7 个工具：`read_file` `write_file` `edit_file` `list_dir` `glob_search` `grep` `bash`
- 工作区沙箱（默认 `cwd`，可用 `--workdir`）
- 上下文：超预算时把最旧约 80% 交模型摘要，并截断大工具结果；预留下一轮 completion 配额
- 超预算时默认用一次无工具 LLM 把丢掉的旧轮次收成摘要（失败则回退 user 原文摘录）
- 发行包与用户/工作区 `SKILL.md` 包 + 斜杠 `/skill` 勾选装载进本会话 system（见 13）
- 终止条件组合（最大轮次、无工具且有正文、连续失败、用户取消、墙钟、上下文预算）
- LLM 传输层指数退避重试
- 单元测试：循环、解析、沙箱、终止、上下文（全部用 Fake LLM，不打真实网络）
- 会话日志：`.wavemio/logs/<timestamp>.jsonl`（可选，默认开）

**明确不做（V1 非目标）：**

- Web UI / VSCode 插件 / HTTP API 服务
- 多 Agent、子 Agent、计划-执行双模型编排
- MCP、插件市场
- 服务端 Code Interpreter / Files API
- 跨会话长期记忆向量库
- 自动 git commit（可在 bash 里由模型调用 git，但不做封装）
- `strict` tool 模式（需 beta base_url；V1 在本地做 schema 校验即可）

**预留扩展点（只设计接口，V1 给空实现或单一实现）：**

- `LLMClient` → 将来可加 OpenAI / 本地 vLLM
- `Tool` → 将来可加 `git_status` 等
- `EventSink` → 将来可加 WebSocket 前端
- `ConversationSummarizer` → 可换本地小模型；V1 用同一 `LLMClient` 无工具 complete

## 5. 凭据与安全红线

环境变量名（唯一官方来源）：

```text
DEEPSEEK_API_KEY
```

可选：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
WAVEMIO_WORKDIR=.
WAVEMIO_SUMMARIZE_CONTEXT=true
```

规则：

1. 代码、测试、文档、提交信息、演示脚本里 **出现字面量 `sk-` 即为缺陷**。
2. 仓库必须有 `.gitignore`：`.env`、`.env.*`（保留 `.env.example`）、`.wavemio/`（并忽略遗留的 `.coding_agent/`）。
3. `.env.example` 只写空键名。
4. `bash` 子进程环境必须 **剥离** `DEEPSEEK_API_KEY` 以及名称匹配 `.*API_KEY$` / `.*SECRET.*` / `.*TOKEN$` 的变量，防止模型通过 `env` 命令把密钥读进上下文。
5. 日志中的请求头必须脱敏（`Bearer ***`）。

## 6. 术语

| 术语 | 含义 |
|------|------|
| Turn / 轮 | 一次「调用模型 →（可选）执行工具 → 写回历史」 |
| Step / 步 | 轮内的一个工具调用 |
| Observation | 工具执行结果，作为 `role=tool` 消息回灌 |
| Finish reason | API 的 `choices[0].finish_reason` |
| Workspace | 文件工具允许触及的根目录 |
| Event | 循环向 UI 广播的领域事件 |
| Composition Root | `bootstrap.py`，唯一允许 `new` 具体类并接线的地方 |
| Skill | 用户投放的 `SKILL.md` 说明书；`/skill` 装载进本会话 system，不是工具 |

## 7. 质量标准（面试可辩护）

实现完成后，作者应能不看代码回答：

1. 为什么循环在「有 tool_calls」时不把 `content` 当最终答案？
2. 为什么工具失败不能抛到 CLI 直接崩掉，而要变成 Observation？
3. 为什么要自己数 token / 截断，而不能把无限历史丢给 1M 窗口？
4. 为什么路径必须相对 Workspace 解析？
5. 为什么 Parser 要有 Fallback，而不能只信 `tool_calls` 字段？

这些答案写在对应文档的「设计决策」节，代码注释只引用文档编号，不要复制长文。
