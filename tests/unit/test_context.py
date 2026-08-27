from __future__ import annotations

from coding_agent.context.estimator import HeuristicTokenEstimator
from coding_agent.context.manager import ContextManager
from coding_agent.context.policy import OMITTED_HEADER, TruncatingContextPolicy
from coding_agent.context.store import ConversationStore
from coding_agent.domain.messages import ChatMessage, Role, ToolCallRequest
from coding_agent.llm.types import TokenUsage


def system() -> ChatMessage:
    return ChatMessage(role=Role.SYSTEM, content="You are Wavemio.")


def tool_block(call_id: str, big: bool = False) -> list[ChatMessage]:
    content = "x" * 5000 if big else "ok"
    return [
        ChatMessage(
            role=Role.ASSISTANT,
            tool_calls=(ToolCallRequest(call_id, "read_file", '{"path": "a"}'),),
        ),
        ChatMessage(role=Role.TOOL, content=content, tool_call_id=call_id),
    ]


def make_policy(estimator: HeuristicTokenEstimator, budget: int = 500,
                max_chars: int = 1000) -> TruncatingContextPolicy:
    return TruncatingContextPolicy(
        send_budget=budget, tool_output_max_chars=max_chars, estimator=estimator
    )


def test_oversized_tool_output_truncated() -> None:
    estimator = HeuristicTokenEstimator()
    policy = make_policy(estimator, budget=10_000, max_chars=1000)
    messages = [system(), ChatMessage(role=Role.USER, content="task"), *tool_block("c1", big=True)]
    compacted, _ = policy.compact(messages, budget=10_000, estimator=estimator, tool_schemas=[])
    tool_msg = [m for m in compacted if m.role is Role.TOOL][0]
    assert "truncated by agent" in (tool_msg.content or "")
    assert len(tool_msg.content or "") < 5000


def test_assistant_tool_block_never_split() -> None:
    estimator = HeuristicTokenEstimator()
    policy = make_policy(estimator, budget=200)
    messages = [system()]
    for i in range(10):
        messages.append(ChatMessage(role=Role.USER, content=f"task {i} " + "pad " * 30))
        messages.extend(tool_block(f"c{i}"))
    compacted, _ = policy.compact(messages, budget=200, estimator=estimator, tool_schemas=[])
    tool_ids = {m.tool_call_id for m in compacted if m.role is Role.TOOL}
    for message in compacted:
        if message.role is Role.ASSISTANT and message.tool_calls:
            for call in message.tool_calls:
                assert call.id in tool_ids
    for tid in tool_ids:
        assert any(
            m.role is Role.ASSISTANT and any(c.id == tid for c in m.tool_calls)
            for m in compacted
        )


def test_system_always_first_and_summary_second() -> None:
    estimator = HeuristicTokenEstimator()
    policy = make_policy(estimator, budget=150)
    messages = [system()]
    for i in range(8):
        messages.append(ChatMessage(role=Role.USER, content=f"old task {i} " + "词" * 50))
        messages.append(ChatMessage(role=Role.ASSISTANT, content="done " + "词" * 50))
    compacted, note = policy.compact(messages, budget=150, estimator=estimator, tool_schemas=[])
    assert compacted[0].role is Role.SYSTEM
    assert OMITTED_HEADER in (compacted[1].content or "")
    assert "old task 0" in (compacted[1].content or "")
    assert "dropped" in note


def test_newest_block_kept_even_over_budget() -> None:
    estimator = HeuristicTokenEstimator()
    policy = make_policy(estimator, budget=50, max_chars=100_000)
    messages = [system(), ChatMessage(role=Role.USER, content="big " * 500)]
    compacted, note = policy.compact(messages, budget=50, estimator=estimator, tool_schemas=[])
    assert any(m.role is Role.USER and "big" in (m.content or "") for m in compacted)
    assert "prompt_may_exceed_budget" in note


def test_manager_returns_unchanged_when_within_budget() -> None:
    estimator = HeuristicTokenEstimator()
    store = ConversationStore(system())
    manager = ContextManager(
        store=store,
        policy=make_policy(estimator, budget=100_000),
        estimator=estimator,
        send_budget=100_000,
    )
    manager.append(ChatMessage(role=Role.USER, content="hi"))
    messages, estimate, note = manager.build_request_messages([])
    assert note is None
    assert len(messages) == 2
    assert estimate > 0


def test_manager_compacts_and_writes_back() -> None:
    estimator = HeuristicTokenEstimator()
    store = ConversationStore(system())
    manager = ContextManager(
        store=store,
        policy=make_policy(estimator, budget=200, max_chars=200),
        estimator=estimator,
        send_budget=200,
    )
    for i in range(6):
        manager.append(ChatMessage(role=Role.USER, content=f"task {i} " + "pad " * 100))
    messages, _, note = manager.build_request_messages([])
    assert note is not None
    assert store.all() == tuple(messages)  # write-back happened
    assert store.all()[0].role is Role.SYSTEM


def test_estimator_calibration_clamped() -> None:
    estimator = HeuristicTokenEstimator()
    store = ConversationStore(system())
    manager = ContextManager(
        store=store,
        policy=make_policy(estimator),
        estimator=estimator,
        send_budget=100_000,
    )
    manager.append(ChatMessage(role=Role.USER, content="hello world"))
    manager.build_request_messages([])
    manager.observe_usage(TokenUsage(prompt_tokens=10**6, completion_tokens=0, total_tokens=10**6))
    assert estimator.ratio == 1.8  # clamped upper bound
    manager.build_request_messages([])
    manager.observe_usage(TokenUsage(prompt_tokens=1, completion_tokens=0, total_tokens=1))
    assert estimator.ratio >= 0.6


def test_reset_keeping_system() -> None:
    store = ConversationStore(system())
    store.append(ChatMessage(role=Role.USER, content="x"))
    store.reset_keeping_system()
    assert len(store.all()) == 1
    assert store.all()[0].role is Role.SYSTEM


def test_cjk_estimation_denser_than_ascii() -> None:
    estimator = HeuristicTokenEstimator()
    ascii_msg = ChatMessage(role=Role.USER, content="a" * 100)
    cjk_msg = ChatMessage(role=Role.USER, content="字" * 100)
    assert estimator.estimate_message(cjk_msg) > estimator.estimate_message(ascii_msg)
