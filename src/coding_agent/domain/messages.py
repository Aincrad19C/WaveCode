"""Chat message types (docs/02 §2.1, wire contract in docs/11)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """One tool invocation proposed by the model.

    ``arguments_json`` keeps the raw string so the assistant message can be
    replayed verbatim to the API (docs/11 §3).
    """

    id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str | None = None
    reasoning_content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
