"""Port for compacting dropped turns into a memo (docs/04 §4.2)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from coding_agent.domain.messages import ChatMessage


@runtime_checkable
class ConversationSummarizer(Protocol):
    def summarize(
        self,
        *,
        dropped: Sequence[ChatMessage],
        previous_summary: str | None,
    ) -> str:
        """Plain-text memo. Raise LLMError or ValueError to trigger fallback."""
