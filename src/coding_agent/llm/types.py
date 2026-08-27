"""Request / response value types for the LLM port (docs/02 §3.1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from coding_agent.domain.messages import ChatMessage


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    INSUFFICIENT = "insufficient_system_resource"
    UNKNOWN = "unknown"

    @classmethod
    def from_api(cls, raw: str | None) -> FinishReason:
        if raw is None:
            return cls.UNKNOWN
        try:
            return cls(raw)
        except ValueError:
            return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reasoning_tokens: int = 0
    cache_hit_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ModelRequest:
    messages: Sequence[ChatMessage]
    tools: Sequence[Mapping[str, Any]]
    model: str
    temperature: float
    max_tokens: int
    tool_choice: str | Mapping[str, Any] = "auto"
    stream: bool = True
    thinking_enabled: bool = False
    reasoning_effort: str = "high"


@dataclass(frozen=True, slots=True)
class ModelResponse:
    message: ChatMessage
    finish_reason: FinishReason
    usage: TokenUsage | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
