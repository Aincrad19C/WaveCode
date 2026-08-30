"""Slash-command dispatch shared by the scrolling REPL and the fullscreen TUI."""

from __future__ import annotations

from dataclasses import dataclass

from coding_agent.agent.session import AgentSession
from coding_agent.cli.branding import PRODUCT_NAME
from coding_agent.cli.sidebar import get_sidebar
from coding_agent.cli.sprites.bank import get_bank
from coding_agent.config.settings import Settings
from coding_agent.llm.catalog import discover_models, list_text, supports_thinking
from coding_agent.skills.bank import get_skills

_USAGE_MODEL = "请输入 /model 打开勾选列表。"
_USAGE_THINK = "用法：/think on|off"


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
{think_line}  /mascot        打开立绘包列表
  /skill         打开 skill 列表
  /vim 路径      用外部编辑器打开文件
  /quit /exit /q 退出

其余输入作为编程任务发给 {PRODUCT_NAME}。行末 \\ 续行。
Tab 在输入、文件、Changes 之间循环。F1 对话，F2 文本，Ctrl+T 切换标签。
文件栏：j/k 或滚轮选择，Enter 展开目录或打开文件，常见语言高亮。
Changes：+ 新增为绿，− 删除为红，~ 为修改；Enter 打开红绿对照，而非原始 diff。
/undo 还原最近一次任务中 write_file 与 edit_file 改过的文件。新任务一旦再次改文件，上一窗口即失效。
PgUp / PgDn 滚动对话，↑ / ↓ 翻历史输入。
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
            for schema in session.loop.registry.schemas():
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
                f"轮次    {state.turn}\n"
                f"估计    {state.estimated_prompt_tokens} tokens"
            )
            return SlashOutcome(kind="status", title="status", body=body)
        case "/think":
            if not supports_thinking(settings.deepseek_model):
                return SlashOutcome(kind="warn", body="当前模型不支持 thinking。")
            if arg not in ("on", "off"):
                return SlashOutcome(kind="warn", body=_USAGE_THINK)
            enabled = arg == "on"
            settings.thinking = enabled
            session.loop.settings.thinking = enabled
            return SlashOutcome(kind="note", body=f"thinking = {arg}")
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
