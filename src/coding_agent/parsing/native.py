"""NativeToolCallParser: normalize API tool_calls (docs/06 §4)."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from coding_agent.domain.messages import ToolCallRequest
from coding_agent.errors import ToolCallParseError
from coding_agent.llm.types import FinishReason, ModelResponse
from coding_agent.parsing.base import OutputParser
from coding_agent.parsing.json_repair import repair_json_object

logger = logging.getLogger(__name__)


class NativeToolCallParser(OutputParser):
    def parse(self, response: ModelResponse) -> ModelResponse:
        raw_calls = response.message.tool_calls
        if not raw_calls:
            return response

        cleaned: list[ToolCallRequest] = []
        for call in raw_calls:
            name = call.name.strip()
            if not name:
                logger.warning("dropping tool call with empty name (id=%s)", call.id)
                continue
            arguments = call.arguments_json.strip() or "{}"
            arguments = self._normalize_arguments(arguments)
            cleaned.append(ToolCallRequest(id=call.id, name=name, arguments_json=arguments))

        if not cleaned:
            # All calls dropped: treat as no tools; fallback may still find some.
            message = replace(response.message, tool_calls=())
            return replace(response, message=message)

        # Some models mislabel finish_reason as stop; the tools win (docs/06 §4).
        message = replace(response.message, tool_calls=tuple(cleaned))
        return replace(response, message=message, finish_reason=FinishReason.TOOL_CALLS)

    @staticmethod
    def _normalize_arguments(arguments: str) -> str:
        try:
            data = json.loads(arguments)
        except ValueError:
            try:
                repaired = repair_json_object(arguments)
            except ToolCallParseError:
                # Keep the raw string; Tool.validate_args will produce the
                # failed ToolResult so the model can correct itself.
                return arguments
            data = json.loads(repaired)
            arguments = repaired
        if not isinstance(data, dict):
            return json.dumps({"_error": "arguments must be object"})
        return arguments
