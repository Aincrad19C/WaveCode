"""Mutable per-run loop state implementing LoopView (docs/02 §8.1)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from coding_agent.llm.types import ModelResponse


@dataclass
class LoopState:
    started_at: float = field(default_factory=time.time)
    turn: int = 0
    consecutive_llm_failures: int = 0
    parse_failures: int = 0
    last_response: ModelResponse | None = None
    last_parsed_had_tools: bool = False
    last_assistant_text: str = ""
    estimated_prompt_tokens: int = 0
    overflow_hits: int = 0
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True
