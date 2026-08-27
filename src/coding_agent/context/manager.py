"""ContextManager (docs/02 §5.4, docs/04 §3).

Builds the sendable message list for each turn, compacts when the estimate
exceeds ``send_budget``, writes the compacted view back into the store, and
calibrates the estimator from real API usage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from coding_agent.context.estimator import HeuristicTokenEstimator, TokenEstimator
from coding_agent.context.policy import ContextPolicy
from coding_agent.context.store import ConversationStore
from coding_agent.domain.messages import ChatMessage
from coding_agent.llm.types import TokenUsage


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class ContextManager:
    def __init__(
        self,
        *,
        store: ConversationStore,
        policy: ContextPolicy,
        estimator: TokenEstimator,
        send_budget: int,
    ) -> None:
        self._store = store
        self._policy = policy
        self._estimator = estimator
        self._send_budget = send_budget
        self._last_estimate = 0

    def append(self, message: ChatMessage) -> None:
        self._store.append(message)

    def build_request_messages(
        self, tool_schemas: Sequence[Mapping[str, Any]]
    ) -> tuple[list[ChatMessage], int, str | None]:
        messages = list(self._store.all())
        tools_cost = self._estimator.estimate_tools(tool_schemas)
        estimate = tools_cost + self._estimator.estimate_messages(messages)
        if estimate <= self._send_budget:
            self._last_estimate = estimate
            return messages, estimate, None

        compacted, note = self._policy.compact(
            messages,
            budget=self._send_budget,
            estimator=self._estimator,
            tool_schemas=tool_schemas,
        )
        # Write-back (docs/04 §2): never re-process the same giant tool output.
        self._store.replace_tail_view(compacted)
        estimate = tools_cost + self._estimator.estimate_messages(compacted)
        self._last_estimate = estimate
        return compacted, estimate, note

    def observe_usage(self, usage: TokenUsage) -> None:
        if usage.prompt_tokens <= 0 or self._last_estimate <= 0:
            return
        if isinstance(self._estimator, HeuristicTokenEstimator):
            measured = usage.prompt_tokens / max(self._last_estimate, 1)
            self._estimator.ratio = _clamp(
                0.6 * self._estimator.ratio + 0.4 * measured, 0.6, 1.8
            )

    def store(self) -> ConversationStore:
        return self._store
