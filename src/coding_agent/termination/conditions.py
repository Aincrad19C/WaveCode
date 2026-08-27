"""Concrete termination conditions (docs/07 §2).

Reason strings are stable identifiers the tests (and UI copy) rely on.
"""

from __future__ import annotations

import time

from coding_agent.llm.types import FinishReason
from coding_agent.termination.base import LoopView, TerminationCondition, TerminationDecision


class CancelledCondition(TerminationCondition):
    def evaluate(self, view: LoopView) -> TerminationDecision:
        if view.cancelled:
            return TerminationDecision(stop=True, reason="cancelled", message="已取消。")
        return TerminationDecision.go()


class ConsecutiveFailureCondition(TerminationCondition):
    def __init__(self, max_failures: int) -> None:
        self._max = max_failures

    def evaluate(self, view: LoopView) -> TerminationDecision:
        if view.consecutive_llm_failures >= self._max:
            return TerminationDecision(
                stop=True, reason="llm_failures", message="模型连续失败，停止。"
            )
        return TerminationDecision.go()


class WallClockCondition(TerminationCondition):
    """Checked before each LLM call so we never fire a large request after
    the deadline (docs/07 §2.3)."""

    def __init__(self, max_seconds: float) -> None:
        self._max = max_seconds

    def evaluate(self, view: LoopView) -> TerminationDecision:
        if time.time() - view.started_at >= self._max:
            return TerminationDecision(
                stop=True, reason="wallclock", message=f"超过最大运行时间（{self._max:g}s），停止。"
            )
        return TerminationDecision.go()


class ContextOverflowCondition(TerminationCondition):
    """Stop only after two consecutive over-budget turns, i.e. compaction
    already ran and the prompt still does not fit (docs/07 §2.4)."""

    def __init__(self, max_context_tokens: int) -> None:
        self._max = max_context_tokens

    def evaluate(self, view: LoopView) -> TerminationDecision:
        if view.estimated_prompt_tokens > self._max and view.overflow_hits >= 2:
            return TerminationDecision(
                stop=True,
                reason="context_overflow",
                message="上下文仍超出预算，请 /reset 或缩小任务。",
            )
        return TerminationDecision.go()


class MaxTurnsCondition(TerminationCondition):
    """turn starts at 0 and is incremented after evaluation, so exactly
    max_turns LLM calls are allowed (docs/07 §2.5)."""

    def __init__(self, max_turns: int) -> None:
        self._max = max_turns

    def evaluate(self, view: LoopView) -> TerminationDecision:
        if view.turn >= self._max:
            return TerminationDecision(
                stop=True,
                reason="max_turns",
                message=(
                    f"达到最大推理轮次（{self._max}）。最后一次工具已执行，但模型未给出总结。"
                    "请查看工作区改动，或提高 max_turns。"
                ),
            )
        return TerminationDecision.go()


class NaturalCompletionCondition(TerminationCondition):
    """Safety net: the loop normally breaks on its own for natural completion
    (docs/07 §2.6); this catches future refactors that forget to."""

    def evaluate(self, view: LoopView) -> TerminationDecision:
        response = view.last_response
        if (
            response is not None
            and not view.last_parsed_had_tools
            and view.last_assistant_text.strip()
            and response.finish_reason in (FinishReason.STOP, FinishReason.LENGTH)
        ):
            return TerminationDecision(
                stop=True, reason="natural", message=view.last_assistant_text
            )
        return TerminationDecision.go()
