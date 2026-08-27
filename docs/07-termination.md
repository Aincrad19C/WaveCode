# 07 · 循环终止条件

## 1. 组合方式

`AnyOfTermination(conditions)` 按 **构造列表顺序** 求值，返回第一个 `stop=True`。  
后面的条件即使也会停，本轮不看（reason 要稳定，便于测试）。

V1 注册顺序（不可改，测试依赖 reason 字符串）：

1. `CancelledCondition`          → `cancelled`
2. `ConsecutiveFailureCondition` → `llm_failures`
3. `WallClockCondition`          → `wallclock`
4. `ContextOverflowCondition`    → `context_overflow`
5. `MaxTurnsCondition`           → `max_turns`
6. `NaturalCompletionCondition`  → `natural`  （注意：自然完成主要由 Loop 分支 `break`，本条件作双保险）

`empty` / `content_filter` / `parse_failures` / `auth` 由 Loop 显式 break，不必再做 Condition（避免双重 reason）。但 `LoopView` 仍暴露相关字段以便将来扩展。

## 2. 各条件语义

### 2.1 CancelledCondition

`view.cancelled is True` → stop。  
message：`已取消。`

CLI 在 `KeyboardInterrupt` 和斜杠 `/q` `/quit` `/exit` 时调用 `loop.state.cancel()`。若中断发生在 `run()` 外部（REPL 读输入），不要进循环。

### 2.2 ConsecutiveFailureCondition

`view.consecutive_llm_failures >= settings.max_consecutive_failures`。  
message：`模型连续失败，停止。`

### 2.3 WallClockCondition

`time.time() - view.started_at >= settings.max_wallclock_s`。  
在 **LLM 调用前** 检查，避免超时后还发一个大请求。工具执行中超时由 bash timeout 负责，不在这里 kill 文件写入（写入应尽快结束）。

### 2.4 ContextOverflowCondition

仅当 `view.estimated_prompt_tokens > settings.max_context_tokens` **并且** 上一轮已经 compact 过仍超（`view.overflow_sticky`）。

实现：`LoopState.overflow_hits`，连续两轮 `est > max_context_tokens` 才停，避免误杀。  
message：`上下文仍超出预算，请 /reset 或缩小任务。`

### 2.5 MaxTurnsCondition

`view.turn >= settings.max_turns` 在 **即将开始的这一轮** 触发。  
注意 `Loop` 伪代码是 `evaluate` 在 `turn += 1` **之前**。因此条件应为：

```
if view.turn >= settings.max_turns: stop
```

初始 `turn=0`，允许恰好 `max_turns` 次 LLM 调用。第 `max_turns` 次结束后 `turn==max_turns`，下一轮 evaluate 停止。

若最后一轮产生了 tool_calls：会先执行工具（本轮已开始），然后 `continue` 到循环顶，evaluate 发现 max_turns → stop。  
此时 **没有最终模型总结**。Loop 在因 max_turns 停下且 `final_text` 空时，应合成：

```
达到最大推理轮次（N）。最后一次工具已执行，但模型未给出总结。请查看工作区改动，或提高 max_turns。
```

把这段既当 `FinalAnswer` 也当返回值。`reason=max_turns`。

### 2.6 NaturalCompletionCondition

双保险：`last_response` 存在且无 tools 且 `last_assistant_text.strip()` 非空且 `finish_reason in {stop, length}`。  
若 Loop 已 break，本条件不会被问到。若将来重构漏了 break，本条件可在 **下一轮开始前** 拦住。  
**不要**在「刚 append user、还没有 last_response」时误判。

## 3. 不要用模型说的 stop 当唯一真理

模型可能在 content 里写「我已经完成」却同时再调工具——以 tool_calls 为准。  
模型可能不说完成但已经给出完整答案——以「无工具 + 非空 content」为准。

不实现 `finish` 工具，避免和自然语言结束双通道打架。

## 4. 单测

- max_turns=2：FakeLLM 永远返回 tool_calls，断言恰好 2 次 LLM，随后 reason=max_turns。
- cancelled 在 turn 0 即停，0 次 LLM。
- 自然完成不触发 max_turns。
