# 10 · 实现规格（一键落地必须遵守）

本文是实现的唯一清单。读完 00–12 后按本文创建文件。不要发明第二套类名。产品显示名 **Wavemio**，禁止写回已废弃品牌词（Cobalt / Coba 等）。

## 0. 安全（第一条就做）

1. 根目录创建 `.gitignore`（全文见 §12）。
2. 创建 `.env.example`（无真实密钥）。
3. **任何文件不得出现 `sk-` 开头的真实密钥。** 从环境读取 `DEEPSEEK_API_KEY`。
4. 禁止依赖：langchain、langgraph、llama-index、autogen、crewai、openai-agents、claude-agent-sdk、deepseek-harness。`openai` Python SDK **也不要作为 V1 依赖**（我们用 httpx 自己解析，方便面试说「输出是自己 parse 的」）。允许可选 `pillow` 仅用于 PNG 精灵；无 Pillow 时必须仍能靠内嵌像素数据画出鲸鱼娘。
5. 每次改动必须更新 [CHANGELOG.md](./CHANGELOG.md) 并同步 `coding_agent.__version__` 与 `pyproject.toml` 的 `version`。规则：大功能 / 小功能 / 小 bug 分别加第一 / 第二 / 第三位。

## 1. 实现顺序（严格按此提交，保证 git 历史可读）

建议提交粒度（实现者可合并，但顺序不要乱）：

1. 工程骨架：`pyproject.toml`、`.gitignore`、`.env.example`、空包
2. errors + domain + settings
3. Workspace + 全部 builtin tools + 单测
4. Parser + StreamAssembler + 单测
5. ContextManager + TruncatingPolicy + 单测
6. Termination + 单测
7. DeepSeekClient（可用 httpx mock）
8. AgentLoop + FakeLLM 单测
9. CLI：半块像素鲸鱼娘 + 蓝主题 REPL（见 09、12；禁止 ASCII 猫）
10. bootstrap 接线 + README 运行说明

## 2. 目录树（必须原样创建）

```
Coding_Agent/
  pyproject.toml
  README.md                 # 填写如何安装运行；不要写密钥
  .gitignore
  .env.example
  src/coding_agent/
    __init__.py             # __version__ 必须等于 docs/CHANGELOG.md 最新版本，当前 "0.1.0"
    __main__.py             # from coding_agent.cli.app import main; main()
    py.typed
    app/
      __init__.py
      bootstrap.py
      system_prompt.py
    config/
      __init__.py
      settings.py
    domain/
      __init__.py
      events.py
      messages.py
      results.py
      ports.py
    errors/
      __init__.py
      hierarchy.py
    llm/
      __init__.py
      client.py
      types.py
      deepseek.py
      retry.py
      stream.py
    context/
      __init__.py
      manager.py
      store.py
      estimator.py
      policy.py
    tools/
      __init__.py
      base.py
      registry.py
      executor.py
      workspace.py
      builtin/
        __init__.py
        read_file.py
        write_file.py
        edit_file.py
        list_dir.py
        glob_search.py
        grep.py
        bash.py
    parsing/
      __init__.py
      base.py
      native.py
      fallback.py
      json_repair.py
      pipeline.py
    termination/
      __init__.py
      base.py
      conditions.py
      composite.py
    agent/
      __init__.py
      state.py
      loop.py
      session.py
    cli/
      __init__.py
      branding.py            # PRODUCT_NAME="Wavemio"、CLI_NAME="wavemio"
      theme.py
      pixel.py               # HalfBlockRenderer
      animator.py            # SpriteBank, FramePlayer, WhalechanAnimator
      renderer.py
      repl.py
      app.py
      sprites/
        __init__.py
        palette.py
        parse.py
        whalechan_sd.py
        whalechan_chibi.py
        whalechan_mini.py
  tests/
    conftest.py
    unit/
      test_workspace.py
      test_tools.py
      test_parser.py
      test_json_repair.py
      test_context.py
      test_termination.py
      test_loop.py
      test_retry.py
      test_pixel.py
    fakes/
      llm.py
      sink.py
```

不要把测试文件塞进 `src/`。

## 3. `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "wavemio"
version = "0.1.0"
description = "Wavemio: a from-scratch CLI coding agent for DeepSeek"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.27",
  "pydantic>=2.6",
  "pydantic-settings>=2.2",
  "python-dotenv>=1.0",
  "rich>=13.7",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
sprites = ["pillow>=10.0"]

[project.scripts]
wavemio = "coding_agent.cli.app:main"
coding-agent = "coding_agent.cli.app:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

## 4. 系统提示词 `app/system_prompt.py`

函数：`build_system_prompt(*, workspace_root: str, tool_names: Sequence[str]) -> str`

完整英文模板（实现时原样使用，可微调标点，不可删行为约束）：

```
You are Wavemio, a local coding agent. You work inside this workspace:
{workspace_root}

You MUST solve programming tasks by calling tools. Available tools:
{comma-separated names}

Rules:
1. Prefer tools over guessing. Read a file before editing it.
2. Use edit_file for existing files when a unique old_text span exists; use write_file for new files or full rewrites.
3. Use glob_search/grep/list_dir to explore. Do not invent paths.
4. Use bash only inside the workspace. Do not print or request secrets, API keys, or environment variables that look like credentials.
5. After tools succeed, continue until the user task is actually done (tests passing if you can run them).
6. When finished, reply with a concise summary of what changed and how to run it. Do not call tools in that final message.
7. Tool arguments must be a JSON object. Paths are relative to the workspace root.
8. If a tool fails, read the error and recover. Do not claim success without evidence.
9. Match existing project style. Do not add unrelated refactors or extra markdown files unless asked.
10. Never include API keys in files you write.
```

## 5. 组合根 `app/bootstrap.py` 接线伪代码

```python
def load_settings() -> Settings:
    load_dotenv()  # 不覆盖已有环境变量
    return Settings()

def build_session(settings: Settings, extra_sinks: list[EventSink] | None = None) -> AgentSession:
    if not settings.deepseek_api_key:
        raise ConfigError("DEEPSEEK_API_KEY is missing. Export it or put it in a gitignored .env")
    ws = Workspace(settings.workdir)
    registry = ToolRegistry()
    for t in all_builtin_tools():
        registry.register(t)
    executor = ToolExecutor(registry, ws, timeout_s=settings.bash_timeout_s,
                            output_limit=settings.tool_output_max_chars)
    estimator = HeuristicTokenEstimator()
    policy = TruncatingContextPolicy(
        send_budget=settings.max_context_tokens - settings.completion_reserve_tokens,
        tool_output_max_chars=settings.tool_output_max_chars,
        estimator=estimator,
    )
    system = ChatMessage(role=Role.SYSTEM, content=build_system_prompt(
        workspace_root=str(ws.root), tool_names=registry.names()
    ))
    context = ContextManager(store=ConversationStore(system), policy=policy, estimator=estimator)
    parser = ParserPipeline([NativeToolCallParser(), ContentFallbackParser()])
    term = AnyOfTermination([
        CancelledCondition(),
        ConsecutiveFailureCondition(settings.max_consecutive_failures),
        WallClockCondition(settings.max_wallclock_s),
        ContextOverflowCondition(settings.max_context_tokens),
        MaxTurnsCondition(settings.max_turns),
        NaturalCompletionCondition(),
    ])
    http = httpx.Client(timeout=settings.http_timeout_s)
    llm = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        retry=ExponentialBackoffRetry(),
        http=http,
    )
    # sinks 由 CLI 传入 Fanout(Rich, Jsonl)
    loop = AgentLoop(llm=llm, context=context, executor=executor, registry=registry,
                     parser=parser, termination=term, settings=settings, sink=FanoutSink(...))
    return AgentSession(loop, context, sink)
```

CLI 负责创建 `RichEventSink` 与 `JsonlLogSink`。`JsonlLogSink` 目录 `settings.log_dir.mkdir(parents=True)`。

## 6. DeepSeek 请求体样例

非 thinking：

```json
{
  "model": "deepseek-v4-flash",
  "messages": [],
  "tools": [],
  "tool_choice": "auto",
  "temperature": 0.2,
  "max_tokens": 4096,
  "stream": true,
  "thinking": { "type": "disabled" }
}
```

thinking 开：`"thinking": {"type": "enabled"}, "reasoning_effort": "high"`。

Header：`Authorization: Bearer <key>`，`Content-Type: application/json`。  
URL：`{base}/chat/completions`（base 不要重复 slash）。

流式：逐行 `data: ` 前缀。

## 7. FakeLLM `tests/fakes/llm.py`

```python
class ScriptedLLM(LLMClient):
    def __init__(self, script: list[ModelResponse]):
        self.script = list(script)
        self.calls: list[ModelRequest] = []
    def complete(self, request):
        self.calls.append(request)
        if not self.script:
            raise LLMBadResponseError("script exhausted")
        return self.script.pop(0)
    def stream(self, request, sink):
        resp = self.complete(request)
        if resp.message.content:
            sink.on_event(ContentDelta(text=resp.message.content))
        return resp
```

辅助函数：`assistant_text(text)`、`assistant_tools(list[tuple[name, dict]])` 生成 ModelResponse。

## 8. README.md 应写什么

- 项目一句话 + 「自研循环，无 agent 框架」
- Python 3.11+
- `pip install -e .`
- `export DEEPSEEK_API_KEY=...` 或复制 `.env.example` 为 `.env`
- `wavemio run "Create hello.py that prints hello"`
- `wavemio` 进 REPL
- 注明产品名 Wavemio、CLI 吉祥物为社区二创鲸鱼娘像素风，参考 `Neko3000/deepseek-whalechan`（非官方）
- 不出现真实 key、不出现题目以外的夸大宣传

空的根 README 现在就该被实现者写成上述内容。

## 9. 验收清单（实现结束前逐条打勾）

功能：

- [ ] `wavemio --help` 可用
- [ ] 缺 key 时 exit 2 且无 traceback 洪水
- [ ] REPL boot 为像素鲸鱼娘（鳍耳+蓝发可辨认），蓝色边框；**禁止机器猫 ASCII**
- [ ] think 状态 Live 换帧（≥4 帧）
- [ ] one-shot 能创建文件（工作区可见）
- [ ] 模型 tool_calls 被执行，失败也会继续
- [ ] Ctrl+C 取消
- [ ] `/reset` `/help` `/quit` 工作
- [ ] `.wavemio/logs/*.jsonl` 产生
- [ ] `bash` 子进程看不到 `DEEPSEEK_API_KEY`

架构：

- [ ] `rg -i "langchain|autogen|crewai|agents.sdk"` 无匹配
- [ ] `rg "sk-" src tests docs README.md` 无真实密钥（文档里说 `sk-` 作为脱敏模式允许出现在 08 的正则说明中）
- [ ] `AgentLoop` 不 import `coding_agent.cli`
- [ ] 每个 Tool 是独立类，继承 `Tool`

测试：

- [ ] `wavemio --version` 与 `docs/CHANGELOG.md` 最新版本一致
- [ ] `pytest -q` 全绿，且默认不访问网络（httpx 未 mock 的测试不得实连）

## 10. 各文件职责速查（防止空文件）

| 文件 | 必须包含 |
|------|----------|
| `errors/hierarchy.py` | 02 节异常树全部类 |
| `domain/messages.py` | Role, ToolCallRequest, ChatMessage |
| `domain/events.py` | 02 列出的全部事件 dataclass |
| `domain/ports.py` | EventSink, NullSink, FanoutSink |
| `llm/deepseek.py` | complete + stream + 状态码映射 |
| `llm/stream.py` | StreamAssembler |
| `parsing/pipeline.py` | Native 然后 Fallback |
| `agent/loop.py` | 03 状态机，可拆私有方法但行为一致 |
| `cli/app.py` | argparse + main() |
| `cli/branding.py` | `PRODUCT_NAME = "Wavemio"`、`CLI_NAME = "wavemio"` |
| `cli/pixel.py` | HalfBlockRenderer |
| `cli/sprites/whalechan_sd.py` | 可辨认的内嵌像素帧 |
| `cli/animator.py` | 09/12 规定的动画组 |

## 11. Settings 环境变量对照

| 字段 | 环境变量 | 默认 |
|------|----------|------|
| deepseek_api_key | DEEPSEEK_API_KEY | "" |
| deepseek_base_url | DEEPSEEK_BASE_URL | https://api.deepseek.com |
| deepseek_model | DEEPSEEK_MODEL | deepseek-v4-flash |
| workdir | WAVEMIO_WORKDIR | cwd |
| stream | WAVEMIO_STREAM | true |
| thinking | WAVEMIO_THINKING | false |
| max_turns | WAVEMIO_MAX_TURNS | 30 |
| debug | WAVEMIO_DEBUG | false |
| ascii_fallback | WAVEMIO_ASCII | false |

CLI 参数覆盖 Settings（workdir、model、think、max-turns、verbose）。

`deepseek-chat` → 警告 + 当作 `deepseek-v4-flash`。  
`deepseek-reasoner` → 警告 + `deepseek-v4-flash` 且 `thinking=True`。

## 12. `.gitignore` 全文

```
.env
.env.*
!.env.example
.wavemio/
.coding_agent/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/
dist/
build/
*.egg-info/
.idea/
.vscode/
```

## 13. `.env.example` 全文

```
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
# WAVEMIO_WORKDIR=.
# WAVEMIO_THINKING=false
```

## 14. 风格

- 行宽软限制 100。
- 类型注解齐全。
- 不用 `from module import *`。
- 工具模块不打 print。
- 中文用户可见字符串可以中英混合：UI 用中文短句 + 英文工具名。

## 15. 若规格与官网临时不一致

以 **能跑通 Chat Completions + tools** 为准：模型 ID 若 400，读取错误信息并允许配置覆盖。不要改循环去迁就。把默认模型留在 Settings。

## 16. 明确不要做的「加分项」

不要在 V1 加：Web、Docker 必选、向量记忆、自动 commit、多模型路由、插件系统、Prompt 市场、运行时生图 API。把时间花在循环正确性、沙箱、测试和 **像素鲸鱼娘动画** 上。
