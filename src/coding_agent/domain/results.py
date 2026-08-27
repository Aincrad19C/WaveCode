"""Tool execution result (docs/02 §2.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_call_id: str
    name: str
    ok: bool
    content: str
    meta: Mapping[str, str] = field(default_factory=dict)
