"""Slash-command dispatch shared by the scrolling REPL and the fullscreen TUI."""

from __future__ import annotations

from dataclasses import dataclass

from coding_agent.agent.session import AgentSession
from coding_agent.cli.branding import PRODUCT_NAME
from coding_agent.cli.sprites.bank import get_bank
from coding_agent.config.settings import Settings

HELP_TEXT = f"""斜杠命令：
  /help          列出命令与工具名
  /reset         清空对话（保留 system 与工作区）
  /tools         列出工具 schema 名与说明
  /status        工作区、模型、轮次、token 估计
  /think on|off  切换 thinking 模式
  /mascot        列出立绘包与动作
  /mascot 包名   切换立绘包
  /mascot idle|think|tool|ok|err  切换动作帧
  /quit /exit /q 退出

其余输入将作为编程任务发给 {PRODUCT_NAME}。行末 \\ 可续行。
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
            return SlashOutcome(kind="help", title="help", body=HELP_TEXT)
        case "/reset":
            session.reset()
            return SlashOutcome(kind="note", body="对话已清空（工作区保留）。")
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
            body = (
                f"工作区  {cwd}\n"
                f"模型    {settings.deepseek_model}"
                f"  thinking={'on' if settings.thinking else 'off'}\n"
                f"轮次    {state.turn}\n"
                f"估计    {state.estimated_prompt_tokens} tokens"
            )
            return SlashOutcome(kind="status", title="status", body=body)
        case "/think":
            if arg not in ("on", "off"):
                return SlashOutcome(kind="warn", body="用法：/think on|off")
            enabled = arg == "on"
            settings.thinking = enabled
            session.loop.settings.thinking = enabled
            return SlashOutcome(kind="note", body=f"thinking = {arg}")
        case "/mascot":
            bank = get_bank()
            bank.set_workdir(settings.workdir)
            kind, body = bank.apply(arg)
            title = "mascot" if kind == "status" else ""
            return SlashOutcome(kind=kind, title=title, body=body)
        case _:
            return SlashOutcome(kind="warn", body=f"未知命令 {name}（不会发给模型）")
