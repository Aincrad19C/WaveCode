"""AgentLoop — the heart of the project (docs/03).

Three sentences: each turn sends the compacted history to the model and, when
it proposes native tool calls, executes them locally and feeds every result
(success or failure) back as tool messages; a turn with plain non-empty
content and no tools is the final answer; the loop itself decides when to
stop via composable termination conditions, never the model vendor's runtime.
"""

from __future__ import annotations

from coding_agent.agent.state import LoopState
from coding_agent.config.settings import Settings
from coding_agent.context.manager import ContextManager
from coding_agent.domain.events import (
    AgentFailed,
    AgentWarned,
    ContextCompacted,
    FinalAnswer,
    LLMRequestFinished,
    LLMRequestStarted,
    SessionEnded,
    ToolCallScheduled,
    TurnFinished,
    TurnStarted,
    UserMessageAccepted,
)
from coding_agent.domain.messages import ChatMessage, Role
from coding_agent.domain.ports import EventSink
from coding_agent.errors import CancelledError, LLMAuthError, LLMError, ParseError
from coding_agent.llm.catalog import supports_thinking
from coding_agent.llm.client import LLMClient
from coding_agent.llm.types import FinishReason, ModelRequest, ModelResponse
from coding_agent.parsing.base import OutputParser
from coding_agent.termination.base import TerminationCondition
from coding_agent.termination.conditions import ContextOverflowCondition, MaxTurnsCondition
from coding_agent.tools.executor import ToolExecutor
from coding_agent.tools.registry import ToolRegistry

MAX_PARSE_FAILURES = 3
MAX_EMPTY_STREAK = 2


class AgentLoop:
    def __init__(
        self,
        *,
        llm: LLMClient,
        context: ContextManager,
        executor: ToolExecutor,
        registry: ToolRegistry,
        parser: OutputParser,
        termination: TerminationCondition,
        settings: Settings,
        sink: EventSink,
    ) -> None:
        self.llm = llm
        self.context = context
        self.executor = executor
        self.registry = registry
        self.parser = parser
        self.termination = termination
        self.settings = settings
        self.sink = sink
        self.state = LoopState()
        self.last_end_reason: str = ""

    def sync_runtime_settings(self) -> None:
        """Copy live Settings into context budget and termination caps."""
        send = max(1, self.settings.max_context_tokens - self.settings.completion_reserve_tokens)
        setter = getattr(self.context, "set_send_budget", None)
        if callable(setter):
            setter(send)

        for condition in getattr(self.termination, "_conditions", ()):
            if isinstance(condition, MaxTurnsCondition):
                condition.set_max(self.settings.max_turns)
            elif isinstance(condition, ContextOverflowCondition):
                condition.set_max(self.settings.max_context_tokens)

    def run(self, user_text: str) -> str:
        text = user_text.strip()
        if not text:
            return ""
        self.executor.workspace.mark_new_task()
        self.sink.on_event(UserMessageAccepted(text=text))
        self.context.append(ChatMessage(role=Role.USER, content=text))
        state = self.state = LoopState()
        continuation_used = False
        empty_streak = 0
        final_text = ""
        end_reason = "unknown"

        try:
            while True:
                decision = self.termination.evaluate(state)
                if decision.stop:
                    end_reason = decision.reason
                    final_text = final_text or decision.message
                    if end_reason == "max_turns":
                        self.sink.on_event(FinalAnswer(text=final_text, reason=end_reason))
                    break

                state.turn += 1
                self.sink.on_event(TurnStarted(turn=state.turn))

                request = self._build_request(state)

                self.sink.on_event(LLMRequestStarted())
                try:
                    parsed = self._call_model(request)
                    state.consecutive_llm_failures = 0
                except CancelledError:
                    raise
                except LLMAuthError as exc:
                    end_reason = "auth"
                    final_text = f"认证失败：{exc}"
                    self.sink.on_event(AgentFailed(message=final_text, cause="auth"))
                    break
                except LLMError as exc:
                    state.consecutive_llm_failures += 1
                    self.sink.on_event(AgentWarned(message=str(exc)))
                    if state.consecutive_llm_failures >= self.settings.max_consecutive_failures:
                        end_reason = "llm_failures"
                        final_text = f"模型连续失败：{exc}"
                        break
                    continue

                if parsed is None:  # unparsable output; corrective message queued
                    state.parse_failures += 1
                    if state.parse_failures >= MAX_PARSE_FAILURES:
                        end_reason = "parse_failures"
                        final_text = "无法解析模型输出，已停止。"
                        break
                    continue

                self.context.append(parsed.message)
                if parsed.usage:
                    self.context.observe_usage(parsed.usage)
                state.last_response = parsed
                state.last_parsed_had_tools = bool(parsed.message.tool_calls)
                state.last_assistant_text = parsed.message.content or ""
                self.sink.on_event(
                    LLMRequestFinished(
                        finish_reason=parsed.finish_reason.value, usage=parsed.usage
                    )
                )

                calls = parsed.message.tool_calls
                if calls:
                    empty_streak = 0
                    for call in calls:
                        self.sink.on_event(ToolCallScheduled(call=call))
                    results = self.executor.execute_all(calls, self.sink)
                    for result in results:
                        self.context.append(
                            ChatMessage(
                                role=Role.TOOL,
                                content=result.content,
                                tool_call_id=result.tool_call_id,
                            )
                        )
                    self.sink.on_event(TurnFinished(turn=state.turn))
                    continue  # re-evaluate termination before the next LLM call

                # -- no tools ------------------------------------------------
                if parsed.finish_reason is FinishReason.CONTENT_FILTER:
                    end_reason = "content_filter"
                    final_text = "输出被安全策略过滤。"
                    break

                if parsed.finish_reason is FinishReason.LENGTH and not continuation_used:
                    continuation_used = True
                    # Not a final answer: keep the NaturalCompletion safety
                    # net quiet while the continuation nudge is pending.
                    state.last_assistant_text = ""
                    self.context.append(
                        ChatMessage(
                            role=Role.USER,
                            content=(
                                "Continue from where you left off. "
                                "Do not repeat previous text."
                            ),
                        )
                    )
                    continue

                content = (parsed.message.content or "").strip()
                if content:
                    end_reason = "natural"
                    final_text = content
                    self.sink.on_event(FinalAnswer(text=final_text, reason=end_reason))
                    break

                empty_streak += 1
                if empty_streak >= MAX_EMPTY_STREAK:
                    end_reason = "empty"
                    final_text = "模型连续返回空回复，已停止。"
                    break
                self.context.append(
                    ChatMessage(
                        role=Role.USER,
                        content="Please answer the user or call a tool. "
                        "Empty replies are not allowed.",
                    )
                )
                self.sink.on_event(TurnFinished(turn=state.turn))
        except (CancelledError, KeyboardInterrupt):
            # Sync loop: Ctrl+C lands here directly (docs/03 §4 point 6).
            state.cancel()
            end_reason = "cancelled"
            final_text = final_text or "已取消。"
            self._repair_tool_pairing()
        finally:
            self.last_end_reason = end_reason
            self.sink.on_event(SessionEnded(reason=end_reason))

        return final_text

    def _repair_tool_pairing(self) -> None:
        """After a mid-turn cancel, make sure every assistant.tool_calls has
        matching tool messages so the next request cannot 400 (docs/03 §4)."""
        store = self.context.store()
        messages = store.all()
        if not messages:
            return
        answered = {m.tool_call_id for m in messages if m.role is Role.TOOL and m.tool_call_id}
        for message in messages:
            if message.role is not Role.ASSISTANT or not message.tool_calls:
                continue
            for call in message.tool_calls:
                if call.id not in answered:
                    self.context.append(
                        ChatMessage(
                            role=Role.TOOL,
                            content="cancelled by user before execution",
                            tool_call_id=call.id,
                        )
                    )

    # -- private helpers (control flow identical to docs/03 §3) --------------

    def _build_request(self, state: LoopState) -> ModelRequest:
        schemas = self.registry.schemas()
        messages, estimate, note = self.context.build_request_messages(schemas)
        before = state.estimated_prompt_tokens
        state.estimated_prompt_tokens = estimate
        if estimate > self.settings.max_context_tokens:
            state.overflow_hits += 1
        else:
            state.overflow_hits = 0
        if note:
            self.sink.on_event(
                ContextCompacted(before_tokens=before, after_tokens=estimate, note=note)
            )
        return ModelRequest(
            messages=messages,
            tools=schemas,
            model=self.settings.deepseek_model,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
            stream=self.settings.stream,
            thinking_enabled=bool(
                self.settings.thinking and supports_thinking(self.settings.deepseek_model)
            ),
            reasoning_effort=self.settings.reasoning_effort,
        )

    def _call_model(self, request: ModelRequest) -> ModelResponse | None:
        """Call + parse. Returns None when output is unparsable (a corrective
        user message has been queued per docs/03 state machine)."""
        if self.settings.stream:
            raw = self.llm.stream(request, self.sink)
        else:
            raw = self.llm.complete(request)
        try:
            return self.parser.parse(raw)
        except ParseError as exc:
            self.context.append(
                ChatMessage(
                    role=Role.USER,
                    content=(
                        f"Your last reply could not be parsed ({exc}). "
                        "Call tools via the API tool_calls interface "
                        "or reply with a final answer in plain text."
                    ),
                )
            )
            return None
