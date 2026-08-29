"""Interactive REPL with slash commands (docs/09 §5-6).

TTY sessions use the alternate-screen TUI. This scrolling loop is the
fallback for pipes / non-interactive stdin.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from coding_agent.agent.session import AgentSession
from coding_agent.cli.branding import GLYPH_WAVE, PRODUCT_NAME, PROMPT
from coding_agent.cli.chrome import ocean_panel, wave_strip
from coding_agent.cli.commands import dispatch_slash
from coding_agent.cli.sprites.pack import ensure_user_packs
from coding_agent.cli.theme import UI_CYAN, UI_ICE
from coding_agent.config.settings import Settings


class Repl:
    def __init__(self, session: AgentSession, console: Console, settings: Settings) -> None:
        self.session = session
        self.console = console
        self.settings = settings

    def run(self) -> int:
        ensure_user_packs()
        self.session.start()
        while True:
            try:
                text = self._read_input()
            except (EOFError, KeyboardInterrupt):
                self._farewell()
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
                self.console.print(Text(f"  {GLYPH_WAVE} 已取消。", style="warn"))
        return 0

    def _read_input(self) -> str:
        lines: list[str] = []
        prompt = PROMPT
        while True:
            line = self.console.input(f"[prompt]{prompt}[/prompt]")
            if line.endswith("\\"):
                lines.append(line[:-1])
                prompt = f"{GLYPH_WAVE} … "
                continue
            lines.append(line)
            return "\n".join(lines)

    def _farewell(self) -> None:
        width = min(max(self.console.width - 2, 24), 76)
        self.console.print()
        self.console.print(wave_strip(width))
        self.console.print(Text(f"  {GLYPH_WAVE} 已退出。再见，{PRODUCT_NAME}。", style=UI_CYAN))

    def _handle_slash(self, command: str) -> bool:
        """Returns True when the REPL should exit."""
        outcome = dispatch_slash(command, self.session, self.settings)
        if outcome.quit:
            self._farewell()
            return True
        if outcome.kind in ("help", "tools", "status"):
            border = UI_CYAN if outcome.kind == "help" else UI_ICE
            self.console.print(
                ocean_panel(outcome.body, title=outcome.title or outcome.kind, border=border)
            )
        elif outcome.kind == "warn":
            self.console.print(Text(f"  {GLYPH_WAVE} {outcome.body}", style="warn"))
        elif outcome.body:
            self.console.print(Text(f"  {GLYPH_WAVE} {outcome.body}", style="success"))
        return False
