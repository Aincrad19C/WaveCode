from __future__ import annotations

import time
from types import SimpleNamespace

from coding_agent.domain.messages import ChatMessage, Role
from coding_agent.llm.types import FinishReason, ModelResponse
from coding_agent.termination.composite import AnyOfTermination
from coding_agent.termination.conditions import (
    CancelledCondition,
    ConsecutiveFailureCondition,
    ContextOverflowCondition,
    MaxTurnsCondition,
    NaturalCompletionCondition,
    WallClockCondition,
)


def view(**overrides) -> SimpleNamespace:
    defaults = dict(
        turn=0,
        consecutive_llm_failures=0,
        last_response=None,
        last_parsed_had_tools=False,
        last_assistant_text="",
        started_at=time.time(),
        estimated_prompt_tokens=0,
        cancelled=False,
        overflow_hits=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_cancelled() -> None:
    assert CancelledCondition().evaluate(view(cancelled=True)).reason == "cancelled"
    assert not CancelledCondition().evaluate(view()).stop


def test_consecutive_failures() -> None:
    cond = ConsecutiveFailureCondition(3)
    assert not cond.evaluate(view(consecutive_llm_failures=2)).stop
    assert cond.evaluate(view(consecutive_llm_failures=3)).reason == "llm_failures"


def test_wallclock() -> None:
    cond = WallClockCondition(10)
    assert not cond.evaluate(view(started_at=time.time())).stop
    assert cond.evaluate(view(started_at=time.time() - 11)).reason == "wallclock"


def test_context_overflow_needs_two_hits() -> None:
    cond = ContextOverflowCondition(1000)
    assert not cond.evaluate(view(estimated_prompt_tokens=2000, overflow_hits=1)).stop
    decision = cond.evaluate(view(estimated_prompt_tokens=2000, overflow_hits=2))
    assert decision.reason == "context_overflow"


def test_max_turns_boundary() -> None:
    cond = MaxTurnsCondition(2)
    assert not cond.evaluate(view(turn=1)).stop
    assert cond.evaluate(view(turn=2)).reason == "max_turns"


def test_natural_completion_safety_net() -> None:
    cond = NaturalCompletionCondition()
    assert not cond.evaluate(view()).stop  # no last_response yet: never stop
    response = ModelResponse(
        message=ChatMessage(role=Role.ASSISTANT, content="done"),
        finish_reason=FinishReason.STOP,
    )
    decision = cond.evaluate(
        view(last_response=response, last_assistant_text="done")
    )
    assert decision.reason == "natural"
    assert not cond.evaluate(
        view(last_response=response, last_assistant_text="done", last_parsed_had_tools=True)
    ).stop


def test_any_of_order_first_stop_wins() -> None:
    composite = AnyOfTermination(
        [CancelledCondition(), MaxTurnsCondition(0)]  # both would stop
    )
    decision = composite.evaluate(view(cancelled=True, turn=5))
    assert decision.reason == "cancelled"


def test_any_of_all_pass() -> None:
    composite = AnyOfTermination([CancelledCondition(), MaxTurnsCondition(10)])
    assert not composite.evaluate(view()).stop
