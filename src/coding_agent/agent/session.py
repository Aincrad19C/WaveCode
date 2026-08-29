"""AgentSession: what the REPL holds on to (docs/02 §8.3)."""

from __future__ import annotations

from coding_agent.agent.loop import AgentLoop
from coding_agent.app.system_prompt import build_system_prompt
from coding_agent.context.manager import ContextManager
from coding_agent.domain.events import SessionStarted
from coding_agent.domain.messages import ChatMessage, Role
from coding_agent.domain.ports import EventSink
from coding_agent.skills.bank import get_skills


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

    def rebuild_system(self) -> None:
        skills = get_skills()
        executor = getattr(self.loop, "executor", None)
        registry = getattr(self.loop, "registry", None)
        if executor is None or registry is None:
            return
        content = build_system_prompt(
            workspace_root=str(executor.workspace.root),
            tool_names=registry.names(),
            skill_catalog=skills.catalog(),
            active_skills=skills.active_bodies(),
        )
        self.context.store().replace_system(ChatMessage(role=Role.SYSTEM, content=content))
