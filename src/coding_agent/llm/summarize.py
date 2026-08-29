"""No-tools completion that turns dropped turns into a compact memo."""

from __future__ import annotations

from collections.abc import Sequence

from coding_agent.domain.messages import ChatMessage, Role
from coding_agent.llm.client import LLMClient
from coding_agent.llm.types import ModelRequest

_SYSTEM = (
    "You compress dropped coding-agent turns into a brief memo for a later model call. "
    "Include: user goals, files touched, key decisions, errors, remaining work. "
    "Do not invent files or commands. Plain text, at most 400 words. No markdown tables."
)
_PER_MESSAGE = 1500
_TOTAL = 24_000
_MAX_TOKENS = 512


def _clip_join(parts: list[str]) -> str:
    text = "\n".join(parts)
    return text if len(text) <= _TOTAL else text[:_TOTAL]


def _line(message: ChatMessage) -> str:
    body = (message.content or "")[:_PER_MESSAGE]
    if message.tool_calls:
        names = ",".join(call.name for call in message.tool_calls)
        return f"[{message.role.value} tools={names}] {body}".rstrip()
    return f"[{message.role.value}] {body}".rstrip()


class LlmConversationSummarizer:
    def __init__(self, llm: LLMClient, *, model: str) -> None:
        self._llm = llm
        self._model = model

    def set_model(self, model: str) -> None:
        self._model = model

    def summarize(
        self,
        *,
        dropped: Sequence[ChatMessage],
        previous_summary: str | None,
    ) -> str:
        parts: list[str] = []
        if previous_summary:
            parts.append("Previous summary:\n" + previous_summary[:_TOTAL])
        parts.append("Dropped turns:")
        parts.extend(_line(message) for message in dropped)
        request = ModelRequest(
            messages=(
                ChatMessage(role=Role.SYSTEM, content=_SYSTEM),
                ChatMessage(role=Role.USER, content=_clip_join(parts)),
            ),
            tools=(),
            model=self._model,
            temperature=0.2,
            max_tokens=_MAX_TOKENS,
            stream=False,
            thinking_enabled=False,
        )
        text = (self._llm.complete(request).message.content or "").strip()
        if not text:
            raise ValueError("empty summary")
        return text
