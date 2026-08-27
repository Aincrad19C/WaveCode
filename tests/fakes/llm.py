"""Scripted LLM double (docs/10 §7). Unit tests never touch the network."""

from __future__ import annotations

import json

from coding_agent.domain.events import ContentDelta
from coding_agent.domain.messages import ChatMessage, Role, ToolCallRequest
from coding_agent.domain.ports import EventSink
from coding_agent.errors import LLMBadResponseError
from coding_agent.llm.client import LLMClient
from coding_agent.llm.types import FinishReason, ModelRequest, ModelResponse


class ScriptedLLM(LLMClient):
    def __init__(self, script: list[ModelResponse]) -> None:
        self.script = list(script)
        self.calls: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if not self.script:
            raise LLMBadResponseError("script exhausted")
        return self.script.pop(0)

    def stream(self, request: ModelRequest, sink: EventSink) -> ModelResponse:
        response = self.complete(request)
        if response.message.content:
            sink.on_event(ContentDelta(text=response.message.content))
        return response


class RaisingLLM(LLMClient):
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls = 0

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        raise self.exc

    def stream(self, request: ModelRequest, sink: EventSink) -> ModelResponse:
        return self.complete(request)


def assistant_text(text: str, finish: FinishReason = FinishReason.STOP) -> ModelResponse:
    return ModelResponse(
        message=ChatMessage(role=Role.ASSISTANT, content=text),
        finish_reason=finish,
    )


def assistant_tools(
    calls: list[tuple[str, dict]], content: str | None = None
) -> ModelResponse:
    requests = tuple(
        ToolCallRequest(id=f"call_{i}", name=name, arguments_json=json.dumps(args))
        for i, (name, args) in enumerate(calls)
    )
    return ModelResponse(
        message=ChatMessage(role=Role.ASSISTANT, content=content, tool_calls=requests),
        finish_reason=FinishReason.TOOL_CALLS,
    )
