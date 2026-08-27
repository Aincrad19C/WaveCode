"""ContentFallbackParser: extract tool calls the model wrote into content
instead of the native tool_calls field (docs/06 §5).

Why a fallback at all: models occasionally emit the tool protocol as text.
Trusting only the native field would turn those turns into dead ends;
extracting them keeps the loop moving (docs/00 §7 Q5).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import replace

from coding_agent.domain.messages import ToolCallRequest
from coding_agent.errors import ToolCallParseError
from coding_agent.llm.types import FinishReason, ModelResponse
from coding_agent.parsing.base import OutputParser
from coding_agent.parsing.json_repair import repair_json_object

_XML_BLOCK_RE = re.compile(
    r"<tool_call>\s*<name>(?P<name>[a-z0-9_]{1,64})</name>\s*"
    r"<arguments>(?P<args>.*?)</arguments>\s*</tool_call>",
    re.DOTALL,
)
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(?P<body>\{.*?\})\s*```", re.DOTALL)


def _new_id() -> str:
    return f"call_fb_{uuid.uuid4().hex[:8]}"


class ContentFallbackParser(OutputParser):
    def parse(self, response: ModelResponse) -> ModelResponse:
        if response.message.tool_calls:
            return response
        content = response.message.content or ""
        if not content.strip():
            return response

        calls, remaining = self._extract_xml(content)
        if not calls:
            calls, remaining = self._extract_fenced_json(content)
        if not calls:
            return response

        message = replace(
            response.message,
            content=remaining.strip() or None,
            tool_calls=tuple(calls),
        )
        return replace(response, message=message, finish_reason=FinishReason.TOOL_CALLS)

    @staticmethod
    def _extract_xml(content: str) -> tuple[list[ToolCallRequest], str]:
        calls: list[ToolCallRequest] = []

        def _consume(match: re.Match[str]) -> str:
            raw_args = match.group("args").strip()
            try:
                arguments = repair_json_object(raw_args) if raw_args else "{}"
            except ToolCallParseError:
                arguments = json.dumps({"_raw": raw_args})
            calls.append(
                ToolCallRequest(id=_new_id(), name=match.group("name"), arguments_json=arguments)
            )
            return ""

        remaining = _XML_BLOCK_RE.sub(_consume, content)
        return calls, remaining

    @staticmethod
    def _extract_fenced_json(content: str) -> tuple[list[ToolCallRequest], str]:
        calls: list[ToolCallRequest] = []

        def _consume(match: re.Match[str]) -> str:
            body = match.group("body")
            try:
                data = json.loads(repair_json_object(body))
            except (ToolCallParseError, ValueError):
                return match.group(0)
            name = data.get("tool") or data.get("name")
            # Plain code blocks must not be mistaken for tool calls.
            if not isinstance(name, str) or "arguments" not in data:
                return match.group(0)
            arguments = data["arguments"]
            if not isinstance(arguments, dict):
                return match.group(0)
            calls.append(
                ToolCallRequest(
                    id=_new_id(), name=name.strip(), arguments_json=json.dumps(arguments)
                )
            )
            return ""

        remaining = _FENCED_JSON_RE.sub(_consume, content)
        return calls, remaining
