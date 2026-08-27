"""Tool ABC: validate -> execute -> clip, template method (docs/02 §4.1, docs/08 §4)."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from coding_agent.domain.messages import ToolCallRequest
from coding_agent.domain.results import ToolResult
from coding_agent.errors import SchemaValidationError, ToolError
from coding_agent.tools.workspace import Workspace

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolContext:
    workspace: Workspace
    timeout_s: float
    output_limit: int = 80_000


def clip(text: str, limit: int) -> str:
    """Keep head 70% / tail 20% of the budget; the tail often carries the
    error trace the model needs (docs/04 §4 stage 1)."""
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = int(limit * 0.2)
    return (
        f"[truncated by agent, original_chars={len(text)}]\n"
        f"{text[:head]}\n... middle omitted ...\n{text[-tail:]}"
    )


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[dict]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def validate_args(self, arguments_json: str) -> Mapping[str, Any]:
        """JSON parse + minimal schema-subset check. Extra keys are dropped;
        missing required keys / wrong types raise SchemaValidationError."""
        text = arguments_json.strip() or "{}"
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise SchemaValidationError(f"arguments are not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise SchemaValidationError("arguments must be a JSON object")
        properties: dict = self.parameters.get("properties", {})
        required = self.parameters.get("required", [])
        for key in required:
            if key not in data:
                raise SchemaValidationError(f"missing required argument: {key}")
        cleaned: dict[str, Any] = {}
        for key, spec in properties.items():
            if key not in data:
                continue
            value = data[key]
            if not _type_ok(value, spec.get("type")):
                raise SchemaValidationError(
                    f"argument {key} must be of type {spec.get('type')}, got {type(value).__name__}"
                )
            cleaned[key] = value
        return cleaned

    def run(self, call: ToolCallRequest, ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = self.validate_args(call.arguments_json)
            text = self.execute(args, ctx)
            ok, content = True, clip(text, ctx.output_limit)
        except SchemaValidationError as exc:
            ok, content = False, f"argument error: {exc}"
        except ToolError as exc:
            ok, content = False, str(exc)
        except Exception as exc:  # bug in a tool must still feed back to the model
            logger.exception("internal error in tool %s", self.name)
            ok, content = False, f"internal tool error: {type(exc).__name__}: {exc}"
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return ToolResult(
            tool_call_id=call.id,
            name=self.name,
            ok=ok,
            content=content,
            meta={"elapsed_ms": str(elapsed_ms)},
        )

    @abstractmethod
    def execute(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        """Return the text shown to the model; raise ToolError on failure."""


_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _type_ok(value: Any, json_type: str | None) -> bool:
    if json_type is None:
        return True
    expected = _JSON_TYPES.get(json_type)
    if expected is None:
        return True
    if json_type in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, expected)
