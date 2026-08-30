from __future__ import annotations

from pathlib import Path

import pytest

import coding_agent.agent.loop as loop_module
from coding_agent.agent.loop import AgentLoop
from coding_agent.agent.mode import allowed_tool_names
from coding_agent.agent.session import AgentSession
from coding_agent.agent.state import LoopState
from coding_agent.app.system_prompt import build_system_prompt
from coding_agent.config.settings import Settings
from coding_agent.context.estimator import HeuristicTokenEstimator
from coding_agent.context.manager import ContextManager
from coding_agent.context.policy import SummarizingContextPolicy, TruncatingContextPolicy
from coding_agent.context.store import ConversationStore
from coding_agent.domain.events import FinalAnswer, SessionEnded, ToolExecutionFinished
from coding_agent.domain.messages import ChatMessage, Role
from coding_agent.errors import LLMAuthError, LLMUnavailableError
from coding_agent.llm.client import LLMClient
from coding_agent.llm.summarize import LlmConversationSummarizer
from coding_agent.llm.types import FinishReason
from coding_agent.parsing.fallback import ContentFallbackParser
from coding_agent.parsing.native import NativeToolCallParser
from coding_agent.parsing.pipeline import ParserPipeline
from coding_agent.termination.composite import AnyOfTermination
from coding_agent.termination.conditions import (
    CancelledCondition,
    ConsecutiveFailureCondition,
    ContextOverflowCondition,
    MaxTurnsCondition,
    NaturalCompletionCondition,
    WallClockCondition,
)
from coding_agent.tools.builtin import all_builtin_tools
from coding_agent.tools.executor import ToolExecutor
from coding_agent.tools.registry import ToolRegistry
from coding_agent.tools.workspace import Workspace
from fakes.llm import RaisingLLM, ScriptedLLM, assistant_text, assistant_tools
from fakes.settings import make_settings
from fakes.sink import RecordingSink


def build_loop(
    llm: LLMClient,
    tmp_path: Path,
    sink: RecordingSink,
    settings: Settings | None = None,
    *,
    summarize: bool = False,
    compact_budget: int | None = None,
) -> AgentLoop:
    settings = settings or make_settings(workdir=tmp_path)
    workspace = Workspace(tmp_path)
    registry = ToolRegistry()
    for tool in all_builtin_tools():
        registry.register(tool)
    executor = ToolExecutor(
        registry, workspace,
        timeout_s=settings.bash_timeout_s, output_limit=settings.tool_output_max_chars,
        mode=settings.mode,
    )
    estimator = HeuristicTokenEstimator()
    send_budget = compact_budget
    if send_budget is None:
        send_budget = settings.max_context_tokens - settings.completion_reserve_tokens
    system = ChatMessage(
        role=Role.SYSTEM,
        content=build_system_prompt(
            workspace_root=str(workspace.root),
            tool_names=registry.names(allowed_tool_names(settings.mode)),
            mode=settings.mode,
        ),
    )
    truncating = TruncatingContextPolicy(
        send_budget=send_budget,
        tool_output_max_chars=settings.tool_output_max_chars,
        estimator=estimator,
    )
    policy = truncating
    if summarize:
        policy = SummarizingContextPolicy(
            truncating, LlmConversationSummarizer(llm, model=settings.deepseek_model)
        )
    context = ContextManager(
        store=ConversationStore(system),
        policy=policy,
        estimator=estimator,
        send_budget=send_budget,
    )
    termination = AnyOfTermination([
        CancelledCondition(),
        ConsecutiveFailureCondition(settings.max_consecutive_failures),
        WallClockCondition(settings.max_wallclock_s),
        ContextOverflowCondition(settings.max_context_tokens),
        MaxTurnsCondition(settings.max_turns),
        NaturalCompletionCondition(),
    ])
    return AgentLoop(
        llm=llm,
        context=context,
        executor=executor,
        registry=registry,
        parser=ParserPipeline([NativeToolCallParser(), ContentFallbackParser()]),
        termination=termination,
        settings=settings,
        sink=sink,
    )


def test_scenario_a_direct_answer(tmp_path: Path) -> None:
    llm = ScriptedLLM([assistant_text("done")])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    result = loop.run("say done")
    assert result == "done"
    assert len(llm.calls) == 1
    assert sink.of_type(ToolExecutionFinished) == []
    final = sink.of_type(FinalAnswer)
    assert len(final) == 1 and final[0].reason == "natural"
    assert loop.last_end_reason == "natural"


def test_scenario_b_read_then_answer(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print('hi')\n")
    llm = ScriptedLLM([
        assistant_tools([("read_file", {"path": "a.py"})]),
        assistant_text("it prints hi"),
    ])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    result = loop.run("what does a.py do?")
    assert result == "it prints hi"
    assert len(llm.calls) == 2
    executions = sink.of_type(ToolExecutionFinished)
    assert len(executions) == 1 and executions[0].result.ok
    # history must contain the tool observation, correctly paired
    history = loop.context.store().all()
    tool_messages = [m for m in history if m.role is Role.TOOL]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call_0"
    assert "print" in (tool_messages[0].content or "")


def test_scenario_c_tool_failure_feeds_back_and_continues(tmp_path: Path) -> None:
    llm = ScriptedLLM([
        assistant_tools([("read_file", {"path": "missing.py"})]),
        assistant_text("the file does not exist"),
    ])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    result = loop.run("read missing.py")
    assert result == "the file does not exist"
    assert len(llm.calls) == 2
    executions = sink.of_type(ToolExecutionFinished)
    assert not executions[0].result.ok
    # the second request must let the model see the error text
    second_request = llm.calls[1]
    tool_msgs = [m for m in second_request.messages if m.role is Role.TOOL]
    assert any("ENOENT" in (m.content or "") for m in tool_msgs)


def test_max_turns_does_not_count_summary_complete(tmp_path: Path) -> None:
    class _SplitLLM(ScriptedLLM):
        summary_calls = 0

        def complete(self, request):  # noqa: ANN001
            if not request.tools:
                type(self).summary_calls += 1
                return assistant_text("memo of old turns")
            return super().complete(request)

    _SplitLLM.summary_calls = 0
    llm = _SplitLLM(
        [assistant_tools([("list_dir", {})]), assistant_tools([("list_dir", {})])]
    )
    sink = RecordingSink()
    settings = make_settings(workdir=tmp_path, max_turns=2)
    loop = build_loop(llm, tmp_path, sink, settings, summarize=True, compact_budget=200)
    loop.run("pad " + "词" * 80)
    assert len(llm.calls) >= 2
    task_calls = [c for c in llm.calls if c.tools]
    assert len(task_calls) == 2
    assert _SplitLLM.summary_calls >= 1
    assert loop.last_end_reason == "max_turns"


def test_scenario_d_max_turns_stops_after_tools(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    llm = ScriptedLLM([
        assistant_tools([("read_file", {"path": "a.py"})]),
        assistant_tools([("read_file", {"path": "a.py"})]),  # would be turn 2
    ])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink, make_settings(workdir=tmp_path, max_turns=1))
    result = loop.run("loop forever")
    assert len(llm.calls) == 1  # exactly max_turns LLM calls
    assert loop.last_end_reason == "max_turns"
    assert "达到最大推理轮次" in result
    final = sink.of_type(FinalAnswer)
    assert len(final) == 1 and final[0].reason == "max_turns"


def test_cancelled_before_first_llm_call(tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    state = LoopState()
    state.cancel()
    monkeypatch.setattr(loop_module, "LoopState", lambda: state)
    llm = ScriptedLLM([assistant_text("never")])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    result = loop.run("task")
    assert len(llm.calls) == 0
    assert loop.last_end_reason == "cancelled"
    assert result == "已取消。"


def test_auth_error_ends_immediately(tmp_path: Path) -> None:
    llm = RaisingLLM(LLMAuthError("HTTP 401"))
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    result = loop.run("task")
    assert loop.last_end_reason == "auth"
    assert "401" in result
    assert llm.calls == 1  # no retry loop at this layer


def test_llm_failures_accumulate_then_stop(tmp_path: Path) -> None:
    llm = RaisingLLM(LLMUnavailableError("HTTP 503"))
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink, make_settings(
        workdir=tmp_path, max_consecutive_failures=2))
    result = loop.run("task")
    assert loop.last_end_reason == "llm_failures"
    assert llm.calls == 2
    assert "503" in result


def test_empty_replies_stop_after_two(tmp_path: Path) -> None:
    llm = ScriptedLLM([assistant_text(""), assistant_text("")])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    result = loop.run("task")
    assert loop.last_end_reason == "empty"
    assert "空回复" in result
    assert len(llm.calls) == 2


def test_length_continuation_used_once(tmp_path: Path) -> None:
    llm = ScriptedLLM([
        assistant_text("part one", finish=FinishReason.LENGTH),
        assistant_text("part two"),
    ])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    result = loop.run("long story")
    assert result == "part two"
    # continuation nudge was appended between the calls
    second = llm.calls[1]
    user_msgs = [m.content for m in second.messages if m.role is Role.USER]
    assert any("Continue from where you left off" in (c or "") for c in user_msgs)


def test_tool_history_pairing_invariant(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\n")
    llm = ScriptedLLM([
        assistant_tools([("read_file", {"path": "a.py"}), ("list_dir", {})]),
        assistant_text("ok"),
    ])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    loop.run("task")
    # before every LLM call each assistant.tool_calls has matching tool msgs
    for request in llm.calls:
        messages = list(request.messages)
        for i, message in enumerate(messages):
            if message.role is Role.ASSISTANT and message.tool_calls:
                following = messages[i + 1 : i + 1 + len(message.tool_calls)]
                assert [m.role for m in following] == [Role.TOOL] * len(message.tool_calls)
                assert [m.tool_call_id for m in following] == [
                    c.id for c in message.tool_calls
                ]


def test_session_ended_always_emitted(tmp_path: Path) -> None:
    llm = ScriptedLLM([assistant_text("done")])
    sink = RecordingSink()
    loop = build_loop(llm, tmp_path, sink)
    loop.run("task")
    ended = sink.of_type(SessionEnded)
    assert len(ended) == 1 and ended[0].reason == "natural"


def test_thinking_flag_omitted_when_model_has_no_toggle(tmp_path: Path) -> None:
    llm = ScriptedLLM([assistant_text("ok")])
    sink = RecordingSink()
    settings = make_settings(workdir=tmp_path, thinking=True, deepseek_model="other-chat")
    loop = build_loop(llm, tmp_path, sink, settings)
    loop.run("hi")
    assert llm.calls[0].thinking_enabled is False


def test_thinking_flag_honored_for_v4_flash(tmp_path: Path) -> None:
    llm = ScriptedLLM([assistant_text("ok")])
    sink = RecordingSink()
    settings = make_settings(workdir=tmp_path, thinking=True)
    loop = build_loop(llm, tmp_path, sink, settings)
    loop.run("hi")
    assert llm.calls[0].thinking_enabled is True


def test_sync_runtime_settings_updates_budget_and_caps(tmp_path: Path) -> None:
    llm = ScriptedLLM([assistant_text("ok")])
    sink = RecordingSink()
    settings = make_settings(workdir=tmp_path, max_turns=30, max_context_tokens=32000)
    loop = build_loop(llm, tmp_path, sink, settings)
    loop.settings.max_turns = 12
    loop.settings.max_context_tokens = 20000
    loop.sync_runtime_settings()
    reserve = loop.settings.completion_reserve_tokens
    assert loop.context._send_budget == 20000 - reserve
    assert loop.context._policy._send_budget == 20000 - reserve
    turns = next(c for c in loop.termination._conditions if isinstance(c, MaxTurnsCondition))
    overflow = next(
        c for c in loop.termination._conditions if isinstance(c, ContextOverflowCondition)
    )
    assert turns._max == 12
    assert overflow._max == 20000


def test_plan_mode_omits_write_tools_from_request(tmp_path: Path) -> None:
    llm = ScriptedLLM([assistant_text("ok")])
    sink = RecordingSink()
    settings = make_settings(workdir=tmp_path, mode="plan")
    loop = build_loop(llm, tmp_path, sink, settings)
    loop.run("add auth")
    names = [schema["function"]["name"] for schema in llm.calls[0].tools]
    assert "write_file" not in names
    assert "edit_file" not in names
    assert "bash" not in names
    assert "read_file" in names


def test_plan_mode_captures_document_and_ignores_questions(tmp_path: Path) -> None:
    llm = ScriptedLLM([assistant_text("用哪个框架？\n1. Flask\n2. FastAPI")])
    sink = RecordingSink()
    settings = make_settings(workdir=tmp_path, mode="plan")
    loop = build_loop(llm, tmp_path, sink, settings)
    session = AgentSession(loop, loop.context, sink)
    session.ask("做登录")
    assert session.plan_document == ""
    llm.script.append(assistant_text("# 计划\n改 a.py"))
    session.ask("2")
    assert session.plan_document.startswith("# 计划")
