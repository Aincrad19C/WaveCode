"""Token estimation (docs/02 §5.1, docs/04 §5).

We count tokens ourselves because unlimited history would blow up cost and
latency long before hitting the advertised window (docs/00 §7 Q3). The
heuristic is calibrated against real API usage after each response.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from coding_agent.domain.messages import ChatMessage

_MESSAGE_OVERHEAD = 8


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x3000 <= code <= 0x30FF  # CJK punctuation + kana
        or 0xFF00 <= code <= 0xFFEF  # fullwidth forms
    )


def _estimate_text(text: str) -> float:
    cjk = sum(1 for char in text if _is_cjk(char))
    ascii_like = len(text) - cjk
    return ascii_like / 4.0 + cjk / 1.5


class TokenEstimator(ABC):
    @abstractmethod
    def estimate_message(self, message: ChatMessage) -> int: ...

    @abstractmethod
    def estimate_messages(self, messages: Sequence[ChatMessage]) -> int: ...

    @abstractmethod
    def estimate_tools(self, schemas: Sequence[Mapping[str, Any]]) -> int: ...


class HeuristicTokenEstimator(TokenEstimator):
    """ASCII ~4 chars/token, CJK ~1.5 chars/token, +8 tokens per message.

    ``ratio`` is a calibration multiplier maintained by ContextManager from
    real ``usage.prompt_tokens``; clamped to [0.6, 1.8].
    """

    def __init__(self) -> None:
        self.ratio: float = 1.0

    def estimate_message(self, message: ChatMessage) -> int:
        chars = 0.0
        if message.content:
            chars += _estimate_text(message.content)
        if message.reasoning_content:
            chars += _estimate_text(message.reasoning_content)
        for call in message.tool_calls:
            chars += _estimate_text(call.name) + _estimate_text(call.arguments_json) + 10
        return int((chars + _MESSAGE_OVERHEAD) * self.ratio) + 1

    def estimate_messages(self, messages: Sequence[ChatMessage]) -> int:
        return sum(self.estimate_message(message) for message in messages)

    def estimate_tools(self, schemas: Sequence[Mapping[str, Any]]) -> int:
        text = json.dumps(list(schemas), ensure_ascii=False)
        return int(_estimate_text(text) * self.ratio) + 1
