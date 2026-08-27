"""EventSink port plus trivial implementations (docs/02 §2.4)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from coding_agent.domain.events import AgentEvent


@runtime_checkable
class EventSink(Protocol):
    def on_event(self, event: AgentEvent) -> None: ...


class NullSink:
    def on_event(self, event: AgentEvent) -> None:  # noqa: ARG002
        return


class FanoutSink:
    """Forward each event to every child sink; one failing sink must not
    silence the others (UI bugs should not kill logging)."""

    def __init__(self, sinks: list[EventSink]) -> None:
        self._sinks = list(sinks)

    def on_event(self, event: AgentEvent) -> None:
        for sink in self._sinks:
            try:
                sink.on_event(event)
            except Exception:  # pragma: no cover - defensive
                import logging

                logging.getLogger(__name__).exception("event sink failed")
