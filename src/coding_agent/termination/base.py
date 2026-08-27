"""TerminationCondition contract and the LoopView protocol (docs/02 §7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from coding_agent.llm.types import ModelResponse


@dataclass(frozen=True, slots=True)
class TerminationDecision:
    stop: bool
    reason: str
    message: str

    @staticmethod
    def go() -> TerminationDecision:
        return TerminationDecision(stop=False, reason="", message="")


class LoopView(Protocol):
    @property
    def turn(self) -> int: ...
    @property
    def consecutive_llm_failures(self) -> int: ...
    @property
    def last_response(self) -> ModelResponse | None: ...
    @property
    def last_parsed_had_tools(self) -> bool: ...
    @property
    def last_assistant_text(self) -> str: ...
    @property
    def started_at(self) -> float: ...
    @property
    def estimated_prompt_tokens(self) -> int: ...
    @property
    def cancelled(self) -> bool: ...
    @property
    def overflow_hits(self) -> int: ...


class TerminationCondition(ABC):
    @abstractmethod
    def evaluate(self, view: LoopView) -> TerminationDecision: ...
