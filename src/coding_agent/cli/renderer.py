"""Event sinks: scrolling RichEventSink (pipes / one-shot) and TuiEventSink."""

from __future__ import annotations

import json

from rich.console import Console
from rich.status import Status
from rich.text import Text

from coding_agent.cli.branding import GLYPH_WAVE, PRODUCT_NAME
from coding_agent.cli.chrome import activity_line, ocean_banner, ocean_panel
from coding_agent.cli.theme import UI_CYAN, UI_ERR, UI_ICE, UI_PRIMARY
from coding_agent.cli.view import ChatView
from coding_agent.domain.events import (
    AgentEvent,
    AgentFailed,
    AgentWarned,
    ContextCompacted,
    FinalAnswer,
    LLMRequestStarted,
    SessionStarted,
    ToolCallScheduled,
    ToolExecutionFinished,
    UserMessageAccepted,
)
from coding_agent.domain.messages import ToolCallRequest

_VERBS = {
    "read_file": "Read",
    "write_file": "Write",
    "edit_file": "Edit",
    "list_dir": "List",
    "glob_search": "Glob",
    "grep": "Grep",
    "bash": "Bash",
}


class RichEventSink:
    def __init__(self, console: Console) -> None:
        self.console = console
        self._status: Status | None = None
        self._current_activity = ""

    def on_event(self, event: AgentEvent) -> None:
        handler = getattr(self, f"_on_{type(event).__name__}", None)
        if handler is not None:
            handler(event)

    def _on_SessionStarted(self, event: SessionStarted) -> None:
        ocean_banner(self.console)

    def _on_UserMessageAccepted(self, event: UserMessageAccepted) -> None:
        self.console.print(ocean_panel(event.text, title="你", border=UI_PRIMARY))

    def _on_LLMRequestStarted(self, event: LLMRequestStarted) -> None:
        self._set_status(f"{GLYPH_WAVE} {PRODUCT_NAME} 思考中…")

    def _on_ToolCallScheduled(self, event: ToolCallScheduled) -> None:
        activity = describe_tool(event.call)
        self._current_activity = activity
        self._set_status(f"{GLYPH_WAVE} {PRODUCT_NAME} {activity}…")

    def _on_ToolExecutionFinished(self, event: ToolExecutionFinished) -> None:
        self._stop_status()
        result = event.result
        label = self._current_activity or result.name
        self.console.print(activity_line(ok=result.ok, label=label))
        if not result.ok:
            summary = (result.content.splitlines()[0] if result.content else "failed")[:80]
            self.console.print(Text(f"     {summary}", style="muted"))

    def _on_ContextCompacted(self, event: ContextCompacted) -> None:
        self.console.print(Text(f"  {GLYPH_WAVE} 上下文压缩", style="muted"))

    def _on_FinalAnswer(self, event: FinalAnswer) -> None:
        self._stop_status()
        if event.text:
            self.console.print()
            self.console.print(ocean_panel(event.text, title=PRODUCT_NAME, border=UI_CYAN))

    def _on_AgentWarned(self, event: AgentWarned) -> None:
        self._stop_status()
        self.console.print(Text(f"  {GLYPH_WAVE} {event.message}", style="warn"))

    def _on_AgentFailed(self, event: AgentFailed) -> None:
        self._stop_status()
        self.console.print(
            ocean_panel(event.message, title="失败", border=UI_ERR)
        )

    def _on_SessionEnded(self, event: AgentEvent) -> None:
        self._stop_status()

    def _set_status(self, text: str) -> None:
        if not self.console.is_terminal:
            return
        styled = Text(text, style=UI_ICE)
        if self._status is None:
            self._status = self.console.status(styled, spinner="dots", spinner_style=UI_CYAN)
            self._status.start()
        else:
            self._status.update(styled)

    def _stop_status(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None


class TuiEventSink:
    """Mutate ChatView instead of printing; used by the alternate-screen TUI."""

    def __init__(self, view: ChatView) -> None:
        self.view = view
        self._current_activity = ""

    def on_event(self, event: AgentEvent) -> None:
        handler = getattr(self, f"_on_{type(event).__name__}", None)
        if handler is not None:
            handler(event)

    def _on_UserMessageAccepted(self, event: UserMessageAccepted) -> None:
        self.view.append("user", event.text)

    def _on_LLMRequestStarted(self, event: LLMRequestStarted) -> None:
        self.view.set_status(f"{GLYPH_WAVE} {PRODUCT_NAME} 思考中…")

    def _on_ToolCallScheduled(self, event: ToolCallScheduled) -> None:
        activity = describe_tool(event.call)
        self._current_activity = activity
        self.view.set_status(f"{GLYPH_WAVE} {PRODUCT_NAME} {activity}…")

    def _on_ToolExecutionFinished(self, event: ToolExecutionFinished) -> None:
        result = event.result
        label = self._current_activity or result.name
        text = label
        if not result.ok:
            summary = (result.content.splitlines()[0] if result.content else "failed")[:80]
            text = f"{label}\n{summary}"
        self.view.append("tool", text, ok=result.ok)

    def _on_ContextCompacted(self, event: ContextCompacted) -> None:
        self.view.append("note", "上下文压缩")

    def _on_FinalAnswer(self, event: FinalAnswer) -> None:
        self.view.set_status("")
        if event.text:
            self.view.append("assistant", event.text)

    def _on_AgentWarned(self, event: AgentWarned) -> None:
        self.view.set_status("")
        self.view.append("note", event.message)

    def _on_AgentFailed(self, event: AgentFailed) -> None:
        self.view.set_status("")
        self.view.append("error", event.message)

    def _on_SessionEnded(self, event: AgentEvent) -> None:
        self.view.set_status("")
        self.view.set_busy(False)


def describe_tool(call: ToolCallRequest) -> str:
    verb = _VERBS.get(call.name, call.name)
    target = _tool_target(call.name, call.arguments_json)
    return f"{verb} {target}".rstrip() if target else verb


def _tool_target(name: str, arguments_json: str) -> str:
    try:
        data = json.loads(arguments_json or "{}")
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    if name == "bash":
        return _short(str(data.get("command", "")), 60)
    if name in ("glob_search", "grep"):
        return _short(str(data.get("pattern", "")), 50)
    return _short(str(data.get("path", "")), 50)


def _short(value: str, limit: int) -> str:
    text = value.replace("\n", " ").strip()
    return text[:limit] + ("…" if len(text) > limit else "")
