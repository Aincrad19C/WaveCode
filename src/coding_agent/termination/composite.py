"""AnyOfTermination: first stop=True wins, order fixed by bootstrap (docs/07 §1)."""

from __future__ import annotations

from collections.abc import Sequence

from coding_agent.termination.base import LoopView, TerminationCondition, TerminationDecision


class AnyOfTermination(TerminationCondition):
    def __init__(self, conditions: Sequence[TerminationCondition]) -> None:
        self._conditions = list(conditions)

    def evaluate(self, view: LoopView) -> TerminationDecision:
        for condition in self._conditions:
            decision = condition.evaluate(view)
            if decision.stop:
                return decision
        return TerminationDecision.go()
