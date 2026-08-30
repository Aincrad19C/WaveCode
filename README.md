# WaveCode

**WaveCode** 是一个用 Python 从零手写的命令行编程智能体（coding agent）：把自然语言任务交给它，
它通过 Chat Completions 的**原生 tool calling** 在本地读写文件、搜索、执行命令，循环
推进直到任务完成。界面不绑定单一厂商；模型由配置选择。**自研 Agent 循环，不使用任何 agent 框架 / SDK**（无 LangChain / AutoGen /
OpenAI Agents SDK 等，也不依赖服务端 Code Interpreter / Files API）；对话历史与上下文管理、
工具定义与本地执行、模型输出解析、循环终止条件、错误处理全部为本仓库自己的代码。

CLI 为全屏独占聊天界面（备用屏幕，像 `top`）：启动动画结束后进入左轨 32×32 立绘（可播 GIF）、其下为紧邻的工作区文件树（默认折叠）与 Changes 框、右侧工作区 HUD。主区域是 Cursor 式标签页（对话 / 文本），底部为输入。Tab 在输入、文件、Changes 之间循环（Enter 展开目录或打开文件；Changes 用红绿对照改动）。管道与 `wavecode run` 仍是滚动文本。

设计文档见 [docs/](./docs/README.md)（00–13 + CHANGELOG）。

## 环境要求

- Python 3.11+
- 依赖仅：`httpx`、`pydantic`、`pydantic-settings`、`python-dotenv`、`rich`、`pygments`

## 安装

从源码：

```bash
pip install .
# 开发：
pip install -e ".[dev]"
```

打成 wheel 再装：

```bash
python -m build
pip install dist/wavecode-*.whl
```

## 自定义立绘

把一个文件夹放到 **`~/.wavecode/mascots/<包名>/`** 或当前工作区 **`<工作区>/.wavecode/mascots/<包名>/`**，里面至少要有 `idle.gif`（或 `idle.png` / `idle.txt`）。启动时会创建这两个目录，并把发行包 `default` 复制进去（已有文件不覆盖）。仍识别旧的 `.wavemio/mascots`。

`/mascot` 在全屏列出可用包并勾选切换；滚动 REPL 打印列表。

## 自定义 Skill

把文件夹放到 **`~/.wavecode/skills/<名>/`**，内含 `SKILL.md`（YAML frontmatter + Markdown 正文）。工作区也可用 `<工作区>/.wavecode/skills/`。启动全屏或 REPL 时会创建用户目录并写入说明。

随包装了 2 个默认 skill：`frontend-design`（仿 Anthropic 官方前端设计 skill：先定视觉方向再写页面）、`tdd`（仿 Matt Pocock 的红绿循环：先写失败测试再补实现）。`/skill` 在全屏列出全部包并勾选装载，最多 8 个；滚动 REPL 打印带 `[✓]` 的列表。用户或工作区同名目录覆盖同名内置包。目录里只放名称与一句话说明，全文按需装载。不执行 skill 目录里的脚本。详见 [docs/13-skills.md](./docs/13-skills.md)。

## 配置密钥（不要提交进仓库）

```bash
export DEEPSEEK_API_KEY=...      # 或：复制 .env.example 为 .env 再填写
```

可选环境变量：`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`（默认 `deepseek-v4-flash`）、
`WAVEMIO_WORKDIR`、`WAVEMIO_THINKING`、`WAVEMIO_MAX_TURNS` 等，
完整对照表见 `docs/10-implementation-spec.md` §11。

## 使用

```bash
wavecode                         # 全屏聊天界面（默认；退出后终端复原）
wavecode run "在当前目录写一个 hello.py 并运行它"
wavecode run -                   # 从 stdin 读任务
wavecode --workdir /path --max-turns 10 --think run "..."
```

`wavemio` 仍是同一入口的别名。

REPL 斜杠命令：`/help` `/reset` `/undo` `/tools` `/status` `/model` `/mode` `/setting` `/think on|off` `/mascot` `/skill` `/vim` `/quit`。三种模式：`ask`（只读问答）、`plan`（逐项确认后写内部计划）、`agent`（改文件，默认）。输入框最前用颜色标出当前模式。助手最终回复按 Markdown 渲染。输入 `/` 后 ↑↓ 选择命令、Enter 补全。Enter 发送，行末 `\` 续行。Tab 在输入、文件、Changes 之间循环；F1 / F2 / Ctrl+T 切换对话与文本标签。当前模型没有 thinking 时不显示 `/think`。
会话日志写入 `<workdir>/.wavecode/logs/<timestamp>.jsonl`（已 gitignore）。

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
- 上下文超预算时先截断过长 tool/assistant 文本（头 70% / 尾 20%），再把最旧约 80% 的轮次交给一次**无工具** LLM 收成备忘，只留最近约 20%（`WAVEMIO_SUMMARIZE_CONTEXT=false` 则只保留用户原句摘录）。摘要失败不影响主任务。规格见 [docs/04-context-management.md](./docs/04-context-management.md) §4.2。
- Skill 是用户 Markdown，会进 system prompt；只装自己信任的包。无 Web UI、无多 Agent、无 MCP、无跨会话向量记忆。
