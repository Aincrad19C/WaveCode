"""Context policies (docs/02 §5.3, algorithm in docs/04 §4)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from coding_agent.context.estimator import TokenEstimator
from coding_agent.context.summarizer import ConversationSummarizer
from coding_agent.domain.messages import ChatMessage, Role
from coding_agent.errors import CancelledError, LLMError
from coding_agent.tools.base import clip

logger = logging.getLogger(__name__)

OMITTED_HEADER = "[context compacted] Older turns were omitted. Summary of omitted user tasks:"
SUMMARY_HEADER = "[context compacted] Summary of omitted turns:"
OMITTED_FOOTER = (
    "Files already edited in omitted turns may exist on disk; "
    "use list_dir/grep rather than assuming memory."
)
_COMPACT_MARK = "[context compacted]"


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


@dataclass(frozen=True, slots=True)
class _Window:
    system: ChatMessage
    dropped: tuple[_Block, ...]
    kept: tuple[_Block, ...]


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


def _budget_note(
    result: Sequence[ChatMessage],
    *,
    budget: int,
    estimator: TokenEstimator,
    tool_schemas: Sequence[Mapping[str, Any]],
) -> str | None:
    cost = estimator.estimate_messages(result) + estimator.estimate_tools(tool_schemas)
    if cost > budget:
        return "prompt_may_exceed_budget"
    return None


def _peel_previous(dropped: Sequence[_Block]) -> tuple[str | None, list[ChatMessage]]:
    previous: str | None = None
    rest: list[ChatMessage] = []
    for block in dropped:
        for message in block.messages:
            if (
                message.role is Role.USER
                and message.content
                and message.content.startswith(_COMPACT_MARK)
            ):
                previous = message.content
            else:
                rest.append(message)
    return previous, rest


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

    def window(
        self,
        messages: Sequence[ChatMessage],
        *,
        budget: int,
        estimator: TokenEstimator,
        tool_schemas: Sequence[Mapping[str, Any]],
    ) -> _Window:
        system, rest = messages[0], [self._truncate_message(m) for m in messages[1:]]
        blocks = _split_blocks(rest)
        message_budget = budget - estimator.estimate_tools(tool_schemas)
        kept: list[_Block] = []
        used = estimator.estimate_message(system)
        dropped: list[_Block] = []
        for index, block in enumerate(reversed(blocks)):
            cost = sum(estimator.estimate_message(m) for m in block.messages)
            if index == 0 or used + cost <= message_budget:
                kept.append(block)
                used += cost
            else:
                dropped = blocks[: len(blocks) - index]
                break
        kept.reverse()
        return _Window(system=system, dropped=tuple(dropped), kept=tuple(kept))

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
        win = self.window(messages, budget=budget, estimator=estimator, tool_schemas=tool_schemas)
        result: list[ChatMessage] = [win.system]
        notes: list[str] = []
        if win.dropped:
            result.append(self._omission_summary(win.dropped))
            notes.append(f"dropped {len(win.dropped)} old block(s)")
        for block in win.kept:
            result.extend(block.messages)
        if extra := _budget_note(
            result, budget=budget, estimator=estimator, tool_schemas=tool_schemas
        ):
            notes.append(extra)
        return result, "; ".join(notes) or "truncated oversized messages"

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
            if message.role is Role.USER
            and message.content
            and not message.content.startswith(_COMPACT_MARK)
        ]
        lines = [OMITTED_HEADER]
        lines.extend(f"- {task}" for task in tasks)
        lines.append(OMITTED_FOOTER)
        return ChatMessage(role=Role.USER, content="\n".join(lines))


class SummarizingContextPolicy(ContextPolicy):
    """Window via TruncatingContextPolicy, then LLM memo for dropped blocks."""

    def __init__(self, inner: TruncatingContextPolicy, summarizer: ConversationSummarizer) -> None:
        self._inner = inner
        self._summarizer = summarizer

    def compact(
        self,
        messages: Sequence[ChatMessage],
        *,
        budget: int,
        estimator: TokenEstimator,
        tool_schemas: Sequence[Mapping[str, Any]],
    ) -> tuple[list[ChatMessage], str]:
        win = self._inner.window(
            messages, budget=budget, estimator=estimator, tool_schemas=tool_schemas
        )
        result: list[ChatMessage] = [win.system]
        notes: list[str] = []
        if win.dropped:
            result.append(self._summarize_or_fallback(win.dropped, notes))
        for block in win.kept:
            result.extend(block.messages)
        if extra := _budget_note(
            result, budget=budget, estimator=estimator, tool_schemas=tool_schemas
        ):
            notes.append(extra)
        return result, "; ".join(notes) or "truncated oversized messages"

    def _summarize_or_fallback(self, dropped: Sequence[_Block], notes: list[str]) -> ChatMessage:
        previous, rest = _peel_previous(dropped)
        try:
            memo = (
                self._summarizer.summarize(dropped=rest, previous_summary=previous) or ""
            ).strip()
            if not memo:
                raise ValueError("empty summary")
            notes.append(f"summarized {len(dropped)} block(s)")
            return ChatMessage(
                role=Role.USER,
                content=f"{SUMMARY_HEADER}\n{memo}\n{OMITTED_FOOTER}",
            )
        except CancelledError:
            raise
        except (LLMError, ValueError):
            notes.append(f"dropped {len(dropped)} old block(s)")
            notes.append("summary_fallback")
            return TruncatingContextPolicy._omission_summary(dropped)
