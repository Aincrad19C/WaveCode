"""Context policies (docs/02 §5.3, algorithm in docs/04 §4)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from coding_agent.context.estimator import TokenEstimator
from coding_agent.domain.messages import ChatMessage, Role
from coding_agent.tools.base import clip

logger = logging.getLogger(__name__)

OMITTED_HEADER = "[context compacted] Older turns were omitted. Summary of omitted user tasks:"
OMITTED_FOOTER = (
    "Files already edited in omitted turns may exist on disk; "
    "use list_dir/grep rather than assuming memory."
)


class ContextPolicy(ABC):
    @abstractmethod
    def compact(
        self,
        messages: Sequence[ChatMessage],
        *,
        budget: int,
        estimator: TokenEstimator,
        tool_schemas: Sequence[Mapping[str, Any]],
    ) -> tuple[list[ChatMessage], str]:
        """Return (sendable messages, human-readable note). Never drops system."""


@dataclass(frozen=True, slots=True)
class _Block:
    """Indivisible group: a lone user/assistant message, or an
    assistant(tool_calls) plus its N tool replies (docs/04 stage 0)."""

    messages: tuple[ChatMessage, ...]


def _split_blocks(rest: Sequence[ChatMessage]) -> list[_Block]:
    blocks: list[_Block] = []
    i = 0
    while i < len(rest):
        msg = rest[i]
        if msg.role is Role.ASSISTANT and msg.tool_calls:
            expected = len(msg.tool_calls)
            group = [msg]
            j = i + 1
            while j < len(rest) and len(group) - 1 < expected and rest[j].role is Role.TOOL:
                group.append(rest[j])
                j += 1
            if len(group) - 1 != expected:
                logger.warning("tool pairing corrupted at index %d; keeping as plain block", i)
            blocks.append(_Block(messages=tuple(group)))
            i = j
        else:
            blocks.append(_Block(messages=(msg,)))
            i += 1
    return blocks


class TruncatingContextPolicy(ContextPolicy):
    def __init__(
        self,
        *,
        send_budget: int,
        tool_output_max_chars: int,
        estimator: TokenEstimator,
    ) -> None:
        self._send_budget = send_budget
        self._tool_output_max_chars = tool_output_max_chars
        self._estimator = estimator

    def compact(
        self,
        messages: Sequence[ChatMessage],
        *,
        budget: int | None = None,
        estimator: TokenEstimator | None = None,
        tool_schemas: Sequence[Mapping[str, Any]] = (),
    ) -> tuple[list[ChatMessage], str]:
        budget = self._send_budget if budget is None else budget
        estimator = estimator or self._estimator
        system, rest = messages[0], list(messages[1:])

        # Stage 1: clip oversized tool / assistant text.
        rest = [self._truncate_message(message) for message in rest]

        # Stage 2: sliding window over protected blocks, newest first.
        blocks = _split_blocks(rest)
        message_budget = budget - estimator.estimate_tools(tool_schemas)
        kept: list[_Block] = []
        used = estimator.estimate_message(system)
        dropped: list[_Block] = []
        for index, block in enumerate(reversed(blocks)):
            cost = sum(estimator.estimate_message(m) for m in block.messages)
            # Stage 3: the newest block is always kept, even over budget.
            if index == 0 or used + cost <= message_budget:
                kept.append(block)
                used += cost
            else:
                dropped = blocks[: len(blocks) - index]
                break
        kept.reverse()

        result: list[ChatMessage] = [system]
        note_parts: list[str] = []
        if dropped:
            result.append(self._omission_summary(dropped))
            note_parts.append(f"dropped {len(dropped)} old block(s)")
        for block in kept:
            result.extend(block.messages)

        final_cost = estimator.estimate_messages(result) + estimator.estimate_tools(tool_schemas)
        if final_cost > budget:
            note_parts.append("prompt_may_exceed_budget")
        return result, "; ".join(note_parts) or "truncated oversized messages"

    def _truncate_message(self, message: ChatMessage) -> ChatMessage:
        limit = self._tool_output_max_chars
        if message.role is Role.TOOL and message.content and len(message.content) > limit:
            return replace(message, content=clip(message.content, limit))
        if (
            message.role is Role.ASSISTANT
            and message.content
            and len(message.content) > limit
        ):
            return replace(message, content=clip(message.content, limit))
        return message

    @staticmethod
    def _omission_summary(dropped: Sequence[_Block]) -> ChatMessage:
        tasks = [
            message.content[:200]
            for block in dropped
            for message in block.messages
            if message.role is Role.USER and message.content
        ]
        lines = [OMITTED_HEADER]
        lines.extend(f"- {task}" for task in tasks)
        lines.append(OMITTED_FOOTER)
        return ChatMessage(role=Role.USER, content="\n".join(lines))


class SummarizingContextPolicy(ContextPolicy):
    """Reserved extension point (docs/00 §4); not wired in V1."""

    def __init__(self, llm: object) -> None:
        self._llm = llm

    def compact(self, messages, *, budget, estimator, tool_schemas):  # noqa: ANN001
        raise NotImplementedError("SummarizingContextPolicy is a V2 extension point")
