"""AgentSession: what the REPL holds on to (docs/02 §8.3)."""

from __future__ import annotations

from coding_agent.agent.loop import AgentLoop
from coding_agent.context.manager import ContextManager
from coding_agent.domain.events import SessionStarted
from coding_agent.domain.ports import EventSink


class AgentSession:
    def __init__(self, loop: AgentLoop, context: ContextManager, sink: EventSink) -> None:
        self.loop = loop
        self.context = context
        self.sink = sink

    def start(self) -> None:
        self.sink.on_event(SessionStarted())

    def ask(self, user_text: str) -> str:
        return self.loop.run(user_text)

    def reset(self) -> None:
        self.context.store().reset_keeping_system()
        executor = getattr(self.loop, "executor", None)
        if executor is not None:
            executor.workspace.reset_cwd()
