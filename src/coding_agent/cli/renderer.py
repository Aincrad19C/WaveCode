"""RichEventSink: compact Claude-Code-style activity (docs/09 §7).

Show what Wavemio is doing right now (thinking / which tool), never dump
reasoning tokens or streaming thought. Final answers appear once, as a block.
"""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.text import Text

from coding_agent.cli.branding import PRODUCT_NAME
from coding_agent.cli.theme import UI_DEEP, UI_PRIMARY
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
        self.console.print(
            Panel(
                Text(f"{PRODUCT_NAME} · DeepSeek", style="title"),
                border_style=UI_PRIMARY,
                expand=False,
            )
        )

    def _on_UserMessageAccepted(self, event: UserMessageAccepted) -> None:
        self.console.print(Panel(event.text, title="你", border_style=UI_DEEP, expand=False))

    def _on_LLMRequestStarted(self, event: LLMRequestStarted) -> None:
        self._set_status(f"{PRODUCT_NAME} 思考中…")

    def _on_ToolCallScheduled(self, event: ToolCallScheduled) -> None:
        activity = describe_tool(event.call)
        self._current_activity = activity
        self._set_status(f"{PRODUCT_NAME} {activity}…")

    def _on_ToolExecutionFinished(self, event: ToolExecutionFinished) -> None:
        self._stop_status()
        result = event.result
        label = self._current_activity or result.name
        if result.ok:
            self.console.print(Text(f"● {label}", style="success"))
        else:
            summary = (result.content.splitlines()[0] if result.content else "failed")[:80]
            self.console.print(Text(f"● {label}", style="error"))
            self.console.print(Text(f"  {summary}", style="muted"))

    def _on_ContextCompacted(self, event: ContextCompacted) -> None:
        self.console.print(Text("[上下文压缩]", style="muted"))

    def _on_FinalAnswer(self, event: FinalAnswer) -> None:
        self._stop_status()
        if event.text:
            self.console.print(
                Panel(event.text, title=PRODUCT_NAME, border_style=UI_PRIMARY, expand=False)
            )

    def _on_AgentWarned(self, event: AgentWarned) -> None:
        self._stop_status()
        self.console.print(Text(f"警告：{event.message}", style="warn"))

    def _on_AgentFailed(self, event: AgentFailed) -> None:
        self._stop_status()
        self.console.print(Text(f"失败：{event.message}", style="error"))

    def _on_SessionEnded(self, event: AgentEvent) -> None:
        self._stop_status()

    def _set_status(self, text: str) -> None:
        if not self.console.is_terminal:
            return
        if self._status is None:
            self._status = self.console.status(Text(text, style="muted"))
            self._status.start()
        else:
            self._status.update(Text(text, style="muted"))

    def _stop_status(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None


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
