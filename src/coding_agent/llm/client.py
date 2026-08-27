"""Abstract LLM client (docs/02 §3.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from coding_agent.domain.ports import EventSink
from coding_agent.llm.types import ModelRequest, ModelResponse


class LLMClient(ABC):
    @abstractmethod
    def complete(self, request: ModelRequest) -> ModelResponse:
        """Blocking, non-streaming completion."""

    @abstractmethod
    def stream(self, request: ModelRequest, sink: EventSink) -> ModelResponse:
        """SSE streaming; emits ReasoningDelta/ContentDelta while assembling
        the same ModelResponse shape complete() would return."""
