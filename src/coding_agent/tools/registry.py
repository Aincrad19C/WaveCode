"""Tool registry (docs/02 §4.3). Open/closed: adding a tool never edits the loop."""

from __future__ import annotations

from coding_agent.errors import ConfigError, UnknownToolError
from coding_agent.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ConfigError(f"duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError(f"no such tool: {name}") from None

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)
