"""Slash-command dispatch shared by the scrolling REPL and the fullscreen TUI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from coding_agent.agent.mode import MODE_DETAILS, MODES, allowed_tool_names, parse_mode
from coding_agent.agent.session import AgentSession
from coding_agent.cli.branding import PRODUCT_NAME
from coding_agent.cli.picker import CONTEXT_MAX, TURNS_MAX, TURNS_MIN, PickItem, context_min
from coding_agent.cli.sidebar import get_sidebar
from coding_agent.cli.sprites.bank import get_bank
from coding_agent.config.settings import Settings
from coding_agent.llm.catalog import discover_models, list_text, supports_thinking
from coding_agent.skills.bank import get_skills

_USAGE_MODEL = "请输入 /model 打开勾选列表。"
_USAGE_MODE = "用法：/mode  或  /mode ask|plan|agent"
_USAGE_THINK = "用法：/think on|off"
_USAGE_SETTING = "请输入 /setting 打开设置。"
_USAGE_SETTING_ARGS = (
    "用法：/setting thinking on|off  /setting stream on|off  "
    "/setting turns 数字  /setting context 数字"
)


@dataclass(frozen=True, slots=True)
class SlashSpec:
    name: str
    summary: str
    thinking: bool = False
    takes_arg: bool = False


SLASH_SPECS: tuple[SlashSpec, ...] = (
    SlashSpec("/help", "列出命令"),
    SlashSpec("/reset", "清空对话"),
    SlashSpec("/undo", "还原本任务的文件改动"),
    SlashSpec("/tools", "列出工具"),
    SlashSpec("/status", "工作区与模型"),
    SlashSpec("/model", "打开模型列表"),
    SlashSpec("/mode", "切换 ask / plan / agent", takes_arg=True),
    SlashSpec("/setting", "打开设置", takes_arg=True),
    SlashSpec("/think", "切换 thinking", thinking=True, takes_arg=True),
    SlashSpec("/mascot", "打开立绘列表"),
    SlashSpec("/skill", "打开 skill 列表"),
    SlashSpec("/vim", "用外部编辑器打开", takes_arg=True),
    SlashSpec("/quit", "退出"),
    SlashSpec("/exit", "退出"),
    SlashSpec("/q", "退出"),
)


def slash_prefix(buffer: str) -> str:
    """Command-name fragment while the user is still typing a slash command."""
    text = (buffer or "").replace("█", "")
    if not text.startswith("/") or any(ch.isspace() for ch in text):
        return ""
    return text


def slash_matches(buffer: str, *, thinking: bool) -> tuple[SlashSpec, ...]:
    prefix = slash_prefix(buffer)
    if not prefix:
        return ()
    needle = prefix.lower()
    matched = [
        spec
        for spec in SLASH_SPECS
        if (not spec.thinking or thinking) and spec.name.startswith(needle)
    ]
    exact = [spec for spec in matched if spec.name == needle]
    rest = [spec for spec in matched if spec.name != needle]
    return tuple(exact + rest)


def filled_command(spec: SlashSpec) -> str:
    return spec.name + (" " if spec.takes_arg else "")


def help_text(settings: Settings) -> str:
    think_line = ""
    if supports_thinking(settings.deepseek_model):
        think_line = "  /think on|off  切换 thinking 模式\n"
    return f"""斜杠命令：
  /help          列出命令
  /reset         清空对话，保留 system 与工作区
  /undo          还原本任务 write_file 与 edit_file 的磁盘改动，不还原 bash 的副作用
  /tools         列出工具名称与说明
  /status        工作区、模型、轮次与 token 估计
  /model         打开模型勾选列表
  /mode          切换 ask / plan / agent
  /setting       打开设置
{think_line}  /mascot        打开立绘包列表
  /skill         打开 skill 列表
  /vim 路径      用外部编辑器打开文件
  /quit /exit /q 退出

其余输入作为编程任务发给 {PRODUCT_NAME}。行末 \\ 续行。
Tab 在输入、文件、Changes 之间循环。F1 对话，F2 文本，Ctrl+T 切换标签。
文件栏：j/k 或滚轮选择，Enter 展开目录或打开文件，常见语言高亮。
Changes：+ 新增为绿，− 删除为红，~ 为修改；Enter 打开红绿对照，而非原始 diff。
/undo 还原最近一次任务中 write_file 与 edit_file 改过的文件。新任务一旦再次改文件，上一窗口即失效。
PgUp / PgDn 滚动对话。输入 / 时 ↑↓ 选择命令、Enter 补全；否则 ↑↓ 翻历史输入。
长输入会折行；超出输入框时用 ← → / Home / End 带动底部滚动条。"""


@dataclass(frozen=True, slots=True)
class SlashOutcome:
    quit: bool = False
    kind: str = "note"
    title: str = ""
    body: str = ""


def dispatch_slash(command: str, session: AgentSession, settings: Settings) -> SlashOutcome:
    name, _, arg = command.partition(" ")
    match name:
        case "/quit" | "/exit" | "/q":
            return SlashOutcome(quit=True)
        case "/help":
            return SlashOutcome(kind="help", title="help", body=help_text(settings))
        case "/reset":
            session.reset()
            return SlashOutcome(kind="note", body="对话已清空，工作区保留。")
        case "/undo":
            return _undo_files(session)
        case "/tools":
            lines = []
            for schema in session.loop.registry.schemas(allowed_tool_names(settings.mode)):
                fn = schema["function"]
                lines.append(f"{fn['name']}\n  {fn['description']}")
            return SlashOutcome(kind="tools", title="tools", body="\n".join(lines))
        case "/status":
            state = session.loop.state
            cwd = settings.workdir.resolve()
            executor = getattr(session.loop, "executor", None)
            if executor is not None:
                cwd = executor.workspace.cwd.resolve()
            think = ""
            if supports_thinking(settings.deepseek_model):
                think = f"  thinking={'on' if settings.thinking else 'off'}"
            body = (
                f"工作区  {cwd}\n"
                f"模型    {settings.deepseek_model}{think}\n"
                f"模式    {settings.mode}\n"
                f"轮次    {state.turn}\n"
                f"估计    {state.estimated_prompt_tokens} tokens"
            )
            return SlashOutcome(kind="status", title="status", body=body)
        case "/think":
            if not supports_thinking(settings.deepseek_model):
                return SlashOutcome(kind="warn", body="当前模型不支持 thinking。")
            if arg not in ("on", "off"):
                return SlashOutcome(kind="warn", body=_USAGE_THINK)
            kind, body = apply_runtime_settings(session, settings, thinking=arg == "on")
            if kind == "note":
                body = f"thinking = {arg}"
            return SlashOutcome(kind=kind, body=body)
        case "/setting":
            if not arg.strip():
                return SlashOutcome(kind="pick", title="setting", body=setting_list_text(settings))
            kind, body = apply_setting_args(session, settings, arg)
            return SlashOutcome(kind=kind, body=body)
        case "/model":
            if arg.strip():
                return SlashOutcome(kind="warn", body=_USAGE_MODEL)
            llm = getattr(getattr(session, "loop", None), "llm", None)
            models = discover_models(llm, current=settings.deepseek_model)
            return SlashOutcome(
                kind="pick",
                title="model",
                body=list_text(models, current=settings.deepseek_model),
            )
        case "/mode":
            if not arg.strip():
                return SlashOutcome(kind="pick", title="mode", body=mode_list_text(settings))
            kind, body = apply_mode(session, settings, arg)
            return SlashOutcome(kind=kind, body=body)
        case "/mascot":
            bank = get_bank()
            bank.set_workdir(settings.workdir)
            kind, body = bank.apply(arg)
            title = "mascot" if kind in {"pick", "status"} else ""
            return SlashOutcome(kind=kind, title=title, body=body)
        case "/skill":
            skills = get_skills()
            skills.set_workdir(settings.workdir)
            kind, body = skills.apply(arg)
            title = "skill" if kind in {"pick", "status"} else ""
            return SlashOutcome(kind=kind, title=title, body=body)
        case "/vim":
            return SlashOutcome(kind="vim", body=arg.strip())
        case _:
            return SlashOutcome(kind="warn", body=f"未知命令 {name}，不会发给模型。")


def _undo_files(session: AgentSession) -> SlashOutcome:
    executor = getattr(session.loop, "executor", None)
    workspace = getattr(executor, "workspace", None)
    if workspace is None or not hasattr(workspace, "restore_task_files"):
        return SlashOutcome(kind="warn", body="当前会话没有工作区，无法 /undo。")
    paths = workspace.restore_task_files()
    if not paths:
        return SlashOutcome(
            kind="warn",
            body="没有可撤回的改动。/undo 只还原本任务的 write_file 与 edit_file。",
        )
    get_sidebar().forget(paths)
    listing = "、".join(paths[:12])
    extra = f" 等 {len(paths)} 个" if len(paths) > 12 else ""
    return SlashOutcome(kind="note", body=f"已还原 {listing}{extra}。")


def mode_list_text(settings: Settings) -> str:
    current = parse_mode(settings.mode) or "agent"
    lines = [f"当前模式  {current}", ""]
    for name in MODES:
        mark = "✓" if name == current else " "
        lines.append(f"  [{mark}] {name}  {MODE_DETAILS[name]}")
    return "\n".join(lines)


def apply_mode(session: AgentSession, settings: Settings, raw: str) -> tuple[str, str]:
    parsed = parse_mode(raw)
    if parsed is None:
        return "warn", _USAGE_MODE
    settings.mode = parsed  # type: ignore[assignment]
    loop = getattr(session, "loop", None)
    loop_settings = getattr(loop, "settings", None)
    if loop_settings is not None:
        loop_settings.mode = parsed
    sync = getattr(loop, "sync_runtime_settings", None)
    if callable(sync):
        sync()
    rebuild = getattr(session, "rebuild_system", None)
    if callable(rebuild):
        rebuild()
    return "note", f"模式 = {parsed}"


def setting_list_text(settings: Settings) -> str:
    lines = ["当前", ""]
    if supports_thinking(settings.deepseek_model):
        mark = "✓" if settings.thinking else " "
        lines.append(f"  [{mark}] thinking")
    mark = "✓" if settings.stream else " "
    lines.append(f"  [{mark}] 流式")
    lines.append(f"  轮次     {settings.max_turns}")
    lines.append(f"  上下文   {settings.max_context_tokens}")
    return "\n".join(lines)


def apply_setting_args(session: AgentSession, settings: Settings, arg: str) -> tuple[str, str]:
    parts = arg.split()
    if len(parts) != 2:
        return "warn", _USAGE_SETTING_ARGS
    key, raw = parts[0], parts[1]
    if key in {"thinking", "think"}:
        if raw not in {"on", "off"}:
            return "warn", _USAGE_SETTING_ARGS
        return apply_runtime_settings(session, settings, thinking=raw == "on")
    if key in {"stream", "流式"}:
        if raw not in {"on", "off"}:
            return "warn", _USAGE_SETTING_ARGS
        return apply_runtime_settings(session, settings, stream=raw == "on")
    if key in {"turns", "轮次"}:
        try:
            n = int(raw)
        except ValueError:
            return "warn", _USAGE_SETTING_ARGS
        return apply_runtime_settings(session, settings, max_turns=n)
    if key in {"context", "上下文"}:
        try:
            n = int(raw)
        except ValueError:
            return "warn", _USAGE_SETTING_ARGS
        return apply_runtime_settings(session, settings, max_context_tokens=n)
    return "warn", _USAGE_SETTING_ARGS


def apply_setting_items(
    session: AgentSession, settings: Settings, items: Sequence[PickItem]
) -> tuple[str, str]:
    kwargs: dict[str, bool | int] = {}
    for item in items:
        if item.name == "thinking":
            kwargs["thinking"] = item.detail == "on"
        elif item.name == "stream":
            kwargs["stream"] = item.detail == "on"
        elif item.name == "turns":
            kwargs["max_turns"] = int(item.detail)
        elif item.name == "context":
            kwargs["max_context_tokens"] = int(item.detail)
    return apply_runtime_settings(session, settings, **kwargs)


def apply_runtime_settings(
    session: AgentSession,
    settings: Settings,
    *,
    thinking: bool | None = None,
    stream: bool | None = None,
    max_turns: int | None = None,
    max_context_tokens: int | None = None,
) -> tuple[str, str]:
    if thinking is True and not supports_thinking(settings.deepseek_model):
        return "warn", "当前模型不支持 thinking。"
    if max_turns is not None and not TURNS_MIN <= max_turns <= TURNS_MAX:
        return "warn", f"轮次须在 {TURNS_MIN} 到 {TURNS_MAX} 之间。"
    if max_context_tokens is not None:
        low = context_min(settings.completion_reserve_tokens)
        if not low <= max_context_tokens <= CONTEXT_MAX:
            return "warn", f"上下文须在 {low} 到 {CONTEXT_MAX} 之间。"
    loop = getattr(session, "loop", None)
    loop_settings = getattr(loop, "settings", None)
    changed: list[str] = []
    if thinking is not None:
        settings.thinking = thinking
        if loop_settings is not None:
            loop_settings.thinking = thinking
        changed.append(f"thinking={'on' if thinking else 'off'}")
    if stream is not None:
        settings.stream = stream
        if loop_settings is not None:
            loop_settings.stream = stream
        changed.append(f"流式={'on' if stream else 'off'}")
    if max_turns is not None:
        settings.max_turns = max_turns
        if loop_settings is not None:
            loop_settings.max_turns = max_turns
        changed.append(f"轮次={max_turns}")
    if max_context_tokens is not None:
        settings.max_context_tokens = max_context_tokens
        if loop_settings is not None:
            loop_settings.max_context_tokens = max_context_tokens
        changed.append(f"上下文={max_context_tokens}")
    sync = getattr(loop, "sync_runtime_settings", None)
    if callable(sync):
        sync()
    if not changed:
        return "warn", _USAGE_SETTING
    return "note", "已更新  " + "  ".join(changed)
