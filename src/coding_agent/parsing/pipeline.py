"""ParserPipeline: native first, then content fallback (docs/06 §7)."""

from __future__ import annotations

from collections.abc import Sequence

from coding_agent.llm.types import ModelResponse
from coding_agent.parsing.base import OutputParser


class ParserPipeline(OutputParser):
    def __init__(self, parsers: Sequence[OutputParser]) -> None:
        if not parsers:
            raise ValueError("ParserPipeline needs at least one parser")
        self._parsers = list(parsers)

    def parse(self, response: ModelResponse) -> ModelResponse:
        result = response
        for parser in self._parsers:
            result = parser.parse(result)
            if result.message.tool_calls:
                return result
        return result
