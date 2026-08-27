# 03 · Agent 循环（必须手写，禁止框架）

这是整个项目的心脏。实现者必须按本节状态机编码，并在 `AgentLoop` 模块文档字符串里用三句话概括。

## 1. 设计决策

1. **原生 function calling 循环**，不是 ReAct 文本伪协议为主。模型通过 API `tools` 选工具；我们本地执行。
2. **工具结果永远回灌**，即使失败。否则模型无法纠错。
3. **有 tool_calls 时本轮没有最终答案**。即使同时带了一段 `content`（旁白），也只展示给用户，然后继续循环。
4. **循环自己决定何时停**，不把控制权交给模型厂商的 agent runtime。
5. **一轮 = 一次 LLM 调用 + 0..N 次工具**。不要在没有新模型反馈时连续执行两批工具。

## 2. 状态机

```
START
  → APPEND_USER
  → CHECK_STOP_BEFORE_LLM
       ├─ stop? → END(reason)
       └─ continue
  → COMPACT_CONTEXT
  → CALL_LLM  (retry 在 Client 内)
       ├─ CancelledError → END(cancelled)
       ├─ LLMAuthError → END(auth)
       ├─ 其它 LLMError 耗尽重试 → consecutive_failures++ → CHECK_STOP → 或再进入 CALL_LLM 前检查
       └─ 得到 RawResponse
  → PARSE
       ├─ ParseError → 向历史追加一条 user/system 纠错消息（见下）→ 下一轮
       └─ ModelResponse
  → APPEND_ASSISTANT
  → BRANCH
       ├─ 有有效 tool_calls → EXECUTE_TOOLS → APPEND_TOOL_MSGS → CHECK_STOP_AFTER_TOOLS → 下一轮
       ├─ finish_reason=length 且无工具 → 追加一条 user「请从断开处继续，不要重复」最多 1 次，然后下一轮；若已续写过 → 当自然完成（截断警告）
       ├─ finish_reason=content_filter → END(filtered)
       ├─ 无工具且有非空 content → END(natural)
       └─ 无工具且空 content → empty_streak++；若 >=2 → END(empty)；否则下一轮带 user「请直接回答或调用工具」
  → END
```

## 3. 伪代码（与实现逐行对应）

```python
def run(self, user_text: str) -> str:
    text = user_text.strip()
    if not text:
        return ""
    self.sink.on_event(UserMessageAccepted(text=text))
    self.context.append(ChatMessage(role=Role.USER, content=text))
    state = LoopState(started_at=time.time())
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
                break

            state.turn += 1
            self.sink.on_event(TurnStarted(turn=state.turn))

            schemas = self.registry.schemas()
            messages, est, note = self.context.build_request_messages(schemas)
            state.estimated_prompt_tokens = est
            if note:
                self.sink.on_event(ContextCompacted(...))

            req = ModelRequest(messages=messages, tools=schemas, ... from settings)

            self.sink.on_event(LLMRequestStarted())
            try:
                raw = self.llm.stream(req, self.sink) if settings.stream else self.llm.complete(req)
                state.consecutive_llm_failures = 0
            except CancelledError:
                raise
            except LLMError as exc:
                state.consecutive_llm_failures += 1
                self.sink.on_event(AgentWarned(message=str(exc)))
                if state.consecutive_llm_failures >= settings.max_consecutive_failures:
                    end_reason = "llm_failures"
                    final_text = f"模型连续失败：{exc}"
                    break
                continue  # 下一轮再试（termination 也会拦）

            try:
                parsed = self.parser.parse(raw)
            except ParseError as exc:
                self.context.append(ChatMessage(
                    role=Role.USER,
                    content=(
                        "Your last reply could not be parsed "
                        f"({exc}). Call tools via the API tool_calls interface "
                        "or reply with a final answer in plain text."
                    ),
                ))
                state.parse_failures += 1
                if state.parse_failures >= 3:
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
            self.sink.on_event(LLMRequestFinished(finish_reason=parsed.finish_reason, usage=parsed.usage))

            calls = parsed.message.tool_calls
            if calls:
                empty_streak = 0
                for c in calls:
                    self.sink.on_event(ToolCallScheduled(call=c))
                results = self.executor.execute_all(calls, self.sink)
                for r in results:
                    self.context.append(ChatMessage(
                        role=Role.TOOL,
                        content=r.content,
                        tool_call_id=r.tool_call_id,
                    ))
                self.sink.on_event(TurnFinished(turn=state.turn))
                # 工具后立刻再检查终止（墙钟、取消、max_turns）
                continue

            # 无工具
            if parsed.finish_reason == FinishReason.CONTENT_FILTER:
                end_reason = "content_filter"
                final_text = "输出被安全策略过滤。"
                break

            if parsed.finish_reason == FinishReason.LENGTH and not continuation_used:
                continuation_used = True
                self.context.append(ChatMessage(
                    role=Role.USER,
                    content="Continue from where you left off. Do not repeat previous text.",
                ))
                continue

            content = (parsed.message.content or "").strip()
            if content:
                end_reason = "natural"
                final_text = content
                self.sink.on_event(FinalAnswer(text=final_text, reason=end_reason))
                break

            empty_streak += 1
            if empty_streak >= 2:
                end_reason = "empty"
                final_text = "模型连续返回空回复，已停止。"
                break
            self.context.append(ChatMessage(
                role=Role.USER,
                content="Please answer the user or call a tool. Empty replies are not allowed.",
            ))
            self.sink.on_event(TurnFinished(turn=state.turn))
    except CancelledError:
        end_reason = "cancelled"
        final_text = final_text or "已取消。"
    finally:
        self.sink.on_event(SessionEnded(reason=end_reason))

    return final_text
```

实现时允许拆私有方法：`_call_model`、`_handle_tools`、`_handle_no_tools`，但控制流不得改变。

## 4. 不变量（测试必须锁住）

1. 每次 LLM 调用前，历史里所有 `assistant.tool_calls` 都已有对应 `tool` 消息（id 一一匹配）。违反时 DeepSeek 会 400。
2. `tool` 消息条数 = 上一条 assistant 的 `tool_calls` 条数，顺序一致。
3. system 永远是 `ConversationStore` 第一条。
4. 用户原始任务只 `append` 一次；纠错/续写是额外 user 消息，不算新 Session。
5. `max_turns` 统计的是 LLM 调用次数，不是工具次数。
6. Ctrl+C：Rich 层捕获 `KeyboardInterrupt`，`state.cancel()`，循环在下一次 `evaluate` 或 LLM 调用前退出。正在跑的 `bash` 应 `kill` 进程组（见 05）。

## 5. 与 thinking 模式

`thinking_enabled=False`（默认）：请求带 `"thinking": {"type": "disabled"}`，避免默认 thinking 浪费延迟。

`thinking_enabled=True`：

- 请求 `"thinking": {"type": "enabled"}`，`reasoning_effort` 用 settings。
- 流式把 `reasoning_content` 增量发给 UI（灰色斜体），**不要**把推理过程再当 user 消息塞回。
- 回灌的 assistant 消息必须包含 API 返回的 `reasoning_content` 字段（若有），否则后续 tool 轮次可能 400。

## 6. 单测脚本示例（FakeLLM）

场景 A：无工具直接回答  
`responses = [assistant("done", finish=stop)]`  
断言：1 次 complete，无 executor 调用，返回 `"done"`。

场景 B：read 再回答  
1) tool_calls read_file  
2) stop + content  
断言：executor 1 次，历史含 tool 消息，FinalAnswer。

场景 C：工具失败仍继续  
read_file 返回 ok=False，下一轮模型仍被调用且能看见错误文本。

场景 D：max_turns=1 且模型还要工具  
执行工具后下一轮 CHECK_STOP 触发 max_turns，发 `FinalAnswer` 或 `AgentFailed` 说明达到上限（见 07：工具后若 stop，把「已达最大步数」给用户，并附上最后工具摘要，不要假装任务成功）。

## 7. 不要写成的几种错误形态

| 反模式 | 为什么错 |
|--------|----------|
| `while True: result = llm(); exec(result)` 无终止 | 题目要求终止条件 |
| 把整段模型文本 `eval` | 安全与解析都失败 |
| 用 LangGraph / 自己写个通用 agent SDK 再调用 | 违反「重要逻辑自行编写」的精神边界；本仓库循环必须可读、扁平 |
| 多线程边跑循环边改 store | 数据竞争；V1 单线程 |
