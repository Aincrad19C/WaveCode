# Wavemio

**Wavemio** 是一个用 Python 从零手写的命令行编程智能体（coding agent）：把自然语言任务交给它，
它通过 DeepSeek Chat Completions 的**原生 tool calling** 在本地读写文件、搜索、执行命令，循环
推进直到任务完成。**自研 Agent 循环，不使用任何 agent 框架 / SDK**（无 LangChain / AutoGen /
OpenAI Agents SDK 等，也不依赖服务端 Code Interpreter / Files API）；对话历史与上下文管理、
工具定义与本地执行、模型输出解析、循环终止条件、错误处理全部为本仓库自己的代码。

CLI 为全屏独占聊天界面（备用屏幕，像 `top`）：左侧吉祥物区留空、工作区信息（目录/模型/轮次）、对话区与底部输入。不绘制像素立绘。管道与 `wavemio run` 仍是滚动文本。

设计文档见 [docs/](./docs/README.md)（00–12 + CHANGELOG）。

## 环境要求

- Python 3.11+
- 依赖仅：`httpx`、`pydantic`、`pydantic-settings`、`python-dotenv`、`rich`

## 安装

```bash
pip install -e ".[dev]"
```

## 配置密钥（不要提交进仓库）

```bash
export DEEPSEEK_API_KEY=...      # 或：复制 .env.example 为 .env 再填写
```

可选环境变量：`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`（默认 `deepseek-v4-flash`）、
`WAVEMIO_WORKDIR`、`WAVEMIO_THINKING`、`WAVEMIO_MAX_TURNS` 等，
完整对照表见 `docs/10-implementation-spec.md` §11。

## 使用

```bash
wavemio                          # 全屏聊天界面（默认；退出后终端复原）
wavemio run "在当前目录写一个 hello.py 并运行它"
wavemio run -                    # 从 stdin 读任务
wavemio --workdir /path --max-turns 10 --think run "..."
```

REPL 斜杠命令：`/help` `/reset` `/tools` `/status` `/think on|off` `/quit`。
会话日志写入 `<workdir>/.wavemio/logs/<timestamp>.jsonl`（已 gitignore）。

## 开发与测试

```bash
ruff check src tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest    # 全部单测离线运行（禁网）
```

单元测试使用 Fake LLM（`tests/fakes/llm.py`），不访问真实 API。

## 能力边界（诚实声明）

- `bash` 工具**不是完整沙箱**：文件工具被限制在工作区内（路径逃逸会被拒绝），但 shell 命令本身
  仍可 `cd` 出去；仅做了极小的危险命令黑名单，请在可信目录下使用。
- 子进程环境会剥离 `DEEPSEEK_API_KEY` 及形如 `*_KEY / *_TOKEN / *SECRET*` 的变量，防止密钥泄漏进模型上下文。
- 上下文超预算时做本地截断压缩（不调用模型做摘要）；超长工具输出保留头 70% / 尾 20%。
- V1 无 Web UI、无多 Agent、无 MCP、无跨会话记忆。
