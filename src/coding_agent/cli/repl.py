"""Interactive REPL with slash commands (docs/09 §5-6)."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from coding_agent.agent.session import AgentSession
from coding_agent.cli.branding import CLI_NAME, PRODUCT_NAME
from coding_agent.config.settings import Settings

PROMPT = f"{CLI_NAME} ❯ "

_HELP = """斜杠命令：
  /help          列出命令与工具名
  /reset         清空对话（保留 system 与工作区）
  /tools         列出工具 schema 名与说明
  /status        工作区、模型、轮次、token 估计
  /think on|off  切换 thinking 模式
  /quit /exit /q 退出

其余输入将作为编程任务发给 Wavemio。行末 \\ 可续行。"""


class Repl:
    def __init__(self, session: AgentSession, console: Console, settings: Settings) -> None:
        self.session = session
        self.console = console
        self.settings = settings

    def run(self) -> int:
        self.session.start()
        while True:
            try:
                text = self._read_input()
            except (EOFError, KeyboardInterrupt):
                self.console.print(Text("\n再见！", style="title"))
                return 0
            if not text.strip():
                continue
            if text.startswith("/"):
                if self._handle_slash(text.strip()):
                    return 0
                continue
            try:
                self.session.ask(text)
            except KeyboardInterrupt:
                self.session.loop.state.cancel()
                self.console.print(Text("已取消。", style="warn"))
        return 0

    def _read_input(self) -> str:
        lines: list[str] = []
        prompt = PROMPT
        while True:
            line = self.console.input(f"[prompt]{prompt}[/prompt]")
            if line.endswith("\\"):
                lines.append(line[:-1])
                prompt = "... "
                continue
            lines.append(line)
            return "\n".join(lines)

    def _handle_slash(self, command: str) -> bool:
        """Returns True when the REPL should exit."""
        name, _, arg = command.partition(" ")
        match name:
            case "/quit" | "/exit" | "/q":
                self.console.print(Text(f"再见，{PRODUCT_NAME}。", style="title"))
                return True
            case "/help":
                self.console.print(Text(_HELP, style="assistant"))
                tools = ", ".join(self.session.loop.registry.names())
                self.console.print(Text(f"可用工具：{tools}", style="muted"))
            case "/reset":
                self.session.reset()
                self.console.print(Text("对话已清空（工作区保留）。", style="success"))
            case "/tools":
                for schema in self.session.loop.registry.schemas():
                    fn = schema["function"]
                    self.console.print(
                        Text(f"  {fn['name']}: {fn['description']}", style="tool")
                    )
            case "/status":
                state = self.session.loop.state
                self.console.print(
                    Text(
                        f"工作区: {self.settings.workdir.resolve()}\n"
                        f"模型: {self.settings.deepseek_model}"
                        f"（thinking={'on' if self.settings.thinking else 'off'}）\n"
                        f"上一次运行轮次: {state.turn}\n"
                        f"上一次 prompt token 估计: {state.estimated_prompt_tokens}",
                        style="muted",
                    )
                )
            case "/think":
                if arg not in ("on", "off"):
                    self.console.print(Text("用法：/think on|off", style="warn"))
                else:
                    enabled = arg == "on"
                    self.settings.thinking = enabled
                    self.session.loop.settings.thinking = enabled
                    self.console.print(Text(f"thinking = {arg}", style="success"))
            case _:
                self.console.print(Text(f"未知命令 {name}（不会发给模型）", style="warn"))
        return False
