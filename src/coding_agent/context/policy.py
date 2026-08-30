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
# When over budget, send the oldest ~80% of rest (by token estimate) to the
# summarizer and keep the newest ~20%. The newest block is never dropped.
_DROP_OLDEST_RATIO = 0.8


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


def _partition_oldest(
    blocks: Sequence[_Block], estimator: TokenEstimator
) -> tuple[tuple[_Block, ...], tuple[_Block, ...]]:
    """Drop oldest blocks until ~80% of rest tokens are dropped; keep the rest.

    Always keep at least the newest block so a live tool pair is never split.
    """
    if not blocks:
        return (), ()
    costs = [sum(estimator.estimate_message(m) for m in block.messages) for block in blocks]
    total = sum(costs)
    if total <= 0:
        return (), tuple(blocks)
    drop_target = int(total * _DROP_OLDEST_RATIO)
    dropped_cost = 0
    index = 0
    while index < len(blocks) - 1 and dropped_cost < drop_target:
        dropped_cost += costs[index]
        index += 1
    return tuple(blocks[:index]), tuple(blocks[index:])


def _fit_kept(
    system: ChatMessage,
    memo: ChatMessage | None,
    kept: Sequence[_Block],
    *,
    target: int,
    estimator: TokenEstimator,
    tool_schemas: Sequence[Mapping[str, Any]],
) -> list[ChatMessage]:
    """Drop oldest kept blocks (never the newest) if the memo still exceeds budget."""
    blocks = list(kept)
    prefix = [system] if memo is None else [system, memo]

    def assemble() -> list[ChatMessage]:
        out = list(prefix)
        for block in blocks:
            out.extend(block.messages)
        return out

    result = assemble()
    while len(blocks) > 1:
        cost = estimator.estimate_messages(result) + estimator.estimate_tools(tool_schemas)
        if cost <= target:
            break
        blocks.pop(0)
        result = assemble()
    return result


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
        estimator: TokenEstimator,
    ) -> _Window:
        system, rest = messages[0], [self._truncate_message(m) for m in messages[1:]]
        dropped, kept = _partition_oldest(_split_blocks(rest), estimator)
        return _Window(system=system, dropped=dropped, kept=kept)

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
        win = self.window(messages, estimator=estimator)
        notes: list[str] = []
        memo = None
        if win.dropped:
            memo = self._omission_summary(win.dropped)
            notes.append(f"dropped {len(win.dropped)} old block(s)")
        result = _fit_kept(
            win.system,
            memo,
            win.kept,
            target=budget,
            estimator=estimator,
            tool_schemas=tool_schemas,
        )
        if extra := _budget_note(
            result, budget=budget, estimator=estimator, tool_schemas=tool_schemas
        ):
            notes.append(extra)
        return result, "; ".join(notes)

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
        win = self._inner.window(messages, estimator=estimator)
        notes: list[str] = []
        memo = None
        if win.dropped:
            memo = self._summarize_or_fallback(win.dropped, notes)
        result = _fit_kept(
            win.system,
            memo,
            win.kept,
            target=budget,
            estimator=estimator,
            tool_schemas=tool_schemas,
        )
        if extra := _budget_note(
            result, budget=budget, estimator=estimator, tool_schemas=tool_schemas
        ):
            notes.append(extra)
        return result, "; ".join(notes)

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
