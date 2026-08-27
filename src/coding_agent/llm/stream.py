"""SSE delta assembler (docs/02 §3.5, docs/06 §3).

Accumulates content / reasoning_content buffers and index-keyed tool_call
fragments into the same ModelResponse shape a non-streaming call returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from coding_agent.domain.messages import ChatMessage, Role, ToolCallRequest
from coding_agent.errors import LLMBadResponseError
from coding_agent.llm.types import FinishReason, ModelResponse, TokenUsage


@dataclass
class _ToolCallAcc:
    id: str = ""
    name: str = ""
    # list-of-fragments then join once: avoids O(n^2) string concat
    arguments: list[str] = field(default_factory=list)


def parse_usage(raw: Mapping[str, Any] | None) -> TokenUsage | None:
    if not raw:
        return None
    details = raw.get("completion_tokens_details") or {}
    return TokenUsage(
        prompt_tokens=int(raw.get("prompt_tokens", 0)),
        completion_tokens=int(raw.get("completion_tokens", 0)),
        total_tokens=int(raw.get("total_tokens", 0)),
        reasoning_tokens=int(details.get("reasoning_tokens", 0)),
        cache_hit_tokens=int(raw.get("prompt_cache_hit_tokens", 0)),
    )


class StreamAssembler:
    def __init__(self) -> None:
        self._content: list[str] = []
        self._reasoning: list[str] = []
        self._calls: dict[int, _ToolCallAcc] = {}
        self._finish_reason: str | None = None
        self._usage: TokenUsage | None = None
        self._saw_choice = False

    def feed(self, chunk: Mapping[str, Any]) -> None:
        if usage := chunk.get("usage"):
            self._usage = parse_usage(usage)
        choices = chunk.get("choices") or []
        if not choices:
            return
        self._saw_choice = True
        choice = choices[0]
        if reason := choice.get("finish_reason"):
            self._finish_reason = reason
        delta = choice.get("delta") or {}
        if text := delta.get("content"):
            self._content.append(text)
        if text := delta.get("reasoning_content"):
            self._reasoning.append(text)
        for frag in delta.get("tool_calls") or []:
            acc = self._calls.setdefault(int(frag.get("index", 0)), _ToolCallAcc())
            if frag.get("id"):
                acc.id = frag["id"]
            fn = frag.get("function") or {}
            if fn.get("name"):
                acc.name = fn["name"]
            if fn.get("arguments"):
                acc.arguments.append(fn["arguments"])

    @property
    def content_so_far(self) -> str:
        return "".join(self._content)

    def finish(self) -> ModelResponse:
        if not self._saw_choice:
            raise LLMBadResponseError("stream ended without any choices")
        calls = tuple(
            ToolCallRequest(id=acc.id, name=acc.name, arguments_json="".join(acc.arguments))
            for _, acc in sorted(self._calls.items())
        )
        content = "".join(self._content) or None
        reasoning = "".join(self._reasoning) or None
        message = ChatMessage(
            role=Role.ASSISTANT,
            content=content,
            reasoning_content=reasoning,
            tool_calls=calls,
        )
        return ModelResponse(
            message=message,
            finish_reason=FinishReason.from_api(self._finish_reason),
            usage=self._usage,
            raw={"stream": True, "finish_reason": self._finish_reason},
        )
