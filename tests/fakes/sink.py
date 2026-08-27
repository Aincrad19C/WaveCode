"""Recording event sink for assertions."""

from __future__ import annotations

from coding_agent.domain.events import AgentEvent


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def on_event(self, event: AgentEvent) -> None:
        self.events.append(event)

    def of_type(self, event_type: type) -> list[AgentEvent]:
        return [event for event in self.events if isinstance(event, event_type)]
