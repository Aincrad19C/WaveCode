"""Domain events broadcast by the loop to EventSinks (docs/02 §2.3).

All events are frozen, keyword-only dataclasses; ``ts`` defaults to now so
call sites only pass payload fields.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent.domain.messages import ToolCallRequest
from coding_agent.domain.results import ToolResult

if TYPE_CHECKING:
    from coding_agent.llm.types import TokenUsage


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentEvent:
    ts: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionStarted(AgentEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class UserMessageAccepted(AgentEvent):
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnStarted(AgentEvent):
    turn: int


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMRequestStarted(AgentEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ReasoningDelta(AgentEvent):
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentDelta(AgentEvent):
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMRequestFinished(AgentEvent):
    finish_reason: str
    usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallScheduled(AgentEvent):
    call: ToolCallRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolExecutionStarted(AgentEvent):
    call: ToolCallRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolExecutionFinished(AgentEvent):
    result: ToolResult


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextCompacted(AgentEvent):
    before_tokens: int
    after_tokens: int
    note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnFinished(AgentEvent):
    turn: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalAnswer(AgentEvent):
    text: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentWarned(AgentEvent):
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentFailed(AgentEvent):
    message: str
    cause: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionEnded(AgentEvent):
    reason: str
