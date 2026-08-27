"""OutputParser ABC (docs/02 §6)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from coding_agent.llm.types import ModelResponse


class OutputParser(ABC):
    @abstractmethod
    def parse(self, response: ModelResponse) -> ModelResponse:
        """Return a (possibly enriched) response; raise ParseError only for
        unrecoverable structure (docs/06 §7)."""
