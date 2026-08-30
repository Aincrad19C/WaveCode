# 04 · 对话历史与上下文管理

## 1. 目标

在 **不丢 system 指令、不破坏 tool_call 配对、控制费用与延迟** 的前提下，为每一轮 LLM 调用构造合法的 `messages`。

即使 DeepSeek V4 宣称超长窗口，V1 仍做压缩，因为：

- 工具输出（日志、大文件）可轻易撑爆费用与延迟；
- 这是题目明确要求的子系统；
- 面试需要你能讲清楚「窗口策略」。

## 2. 三层存储

| 层 | 类 | 内容 |
|----|----|------|
| 完整日志 | `JsonlLogSink` | 所有事件，不做截断，落盘 `.wavemio/logs/` |
| 完整对话 | `ConversationStore` | 本 Session 全部 `ChatMessage`，压缩 **可以写回 store 的可发送视图**，但 Jsonl 仍保留未压缩事件 |
| 发送视图 | `ContextPolicy.compact` 的输出 | 真正 POST 的 messages |

V1 采取 **写回策略**：compact 后用 `replace_tail_view` 更新 store，避免下轮再次处理已经截断的巨型 tool 输出。  
完整原文只存在于 jsonl。这是有意取舍：进程内不保留无限大字符串。

实现注意：`replace_tail_view` 必须仍满足 tool 配对不变量。若某次截断会拆开 assistant/tool 块，则 **整块一起保留或一起折叠**。

## 3. Token 预算

```
send_budget = settings.max_context_tokens - settings.completion_reserve_tokens
```

`max_tokens`（completion）不得大于 `completion_reserve_tokens`。

每次 `build_request_messages`：

```
cost = estimate_tools(schemas) + estimate_messages(messages)
if cost <= send_budget: return messages
else: 从最旧块起丢掉约 80% 的 rest（按 token 估计），交给模型收成备忘，只留最近约 20%
# 最近一块始终保留。摘要加上保留区后若仍超 send_budget，再从保留区最旧块剥到能发为止。
```

若压完仍超预算：`ContextOverflowCondition` 会在下一轮 evaluate 时停（见 07）。本轮仍尝试发送最后 compact 结果，避免「刚好超 1 token」就死；但 `state.estimated_prompt_tokens` 如实上报。

## 4. `TruncatingContextPolicy` 算法（V1 必须实现）

输入：`messages = [system, ...rest]`

**阶段 0 — 保护块**

从 rest 里识别「不可拆块」：

- 单独的 user / assistant（无 tool_calls）各算一块；
- `assistant(tool_calls)` + 紧随其后的 N 条 `tool` 合成一块（N 必须等于 tool_calls 数量；若数据损坏，从损坏处起全部当作普通消息并打日志）。

**阶段 1 — 截断单条过大 tool/assistant 文本**

对每一块内 `role=tool` 或超长 assistant content：

- 若 `len(content) > tool_output_max_chars`，替换为：

```
[truncated by agent, original_chars=NNNN]
...保留头 70% 字符与尾 20% 字符...
... middle omitted ...
```

头尾比例：70% / 10% 省略标记 / 20% 尾。保证 JSON 代码块被截断时尾部仍可能有错误栈。

**阶段 2 — 最旧约 80% 交模型压缩**

触发 compact 的条件仍是估计值超过 `send_budget`。一旦触发：按 token 估计，从 **最旧块** 起丢掉约 80% 的 rest，只留最近约 20%。块很少或最近一块已经很大时，丢掉的比例会低于 80%，因为最近一块始终保留。丢掉的块 **整块** 交给 §4.2 的无工具 LLM 收成一条备忘。摘要失败时回退原文摘录（`TruncatingContextPolicy._omission_summary`）：

```
[context compacted] Older turns were omitted. Summary of omitted user tasks:
- <每条被省略的 user 原文截到 200 字>
Files already edited in omitted turns may exist on disk; use list_dir/grep rather than assuming memory.
```

**阶段 3 — 保底**

始终保留：

1. system
2. 最近 1 个完整块（即使它单独超预算，也只做阶段 1 截断，绝不删当前未完成的 tool 块）

若最近一块截断后仍大于 budget：照样发送，并 set note=`"prompt_may_exceed_budget"`。

## 4.2 `SummarizingContextPolicy`（默认接线）

超预算时不只列用户原句，而用 **一次额外的、无工具的 LLM 调用** 把丢掉的旧轮次收成一段备忘，行为接近 Cursor 的 conversation summary：后面的模型仍看得见目标、改过的文件、坑和未完成项，却不必重放整段 tool 日志。

**组合方式：** 先跑与 §4 完全相同的阶段 0–1，再按最旧约 80% 切出 `dropped` / `kept`。有 `dropped` 时再摘要；没有丢掉的块则只截断大文本，不打模型。

**插入位置：** 仍是 `system` 之后、保留区之前 **一条** `role=user` 消息。新头：

```
[context compacted] Summary of omitted turns:
<模型写出的备忘>
Files already edited in omitted turns may exist on disk; use list_dir/grep rather than assuming memory.
```

若 `dropped` 里已有上一次带 `[context compacted]` 头的 user 消息，把它整段当作 `previous_summary` 交给摘要器，**不要**再当普通 user 任务摘 200 字。滚动摘要：旧备忘 + 新丢掉的轮次 → 一条新备忘。

**`ConversationSummarizer` 端口**（`context/summarizer.py`，domain 不 import `DeepSeekClient`）：

```python
class ConversationSummarizer(Protocol):
    def summarize(
        self,
        *,
        dropped: Sequence[ChatMessage],
        previous_summary: str | None,
    ) -> str:
        """纯文本备忘。失败抛 LLMError / ValueError，由 policy 回退原文摘录。"""
```

`LlmConversationSummarizer`（`llm/summarize.py` 或 `app/`）：`LLMClient.complete`，**禁止** `tools`、**禁止** stream、**禁止** thinking。`max_tokens` 512。用独立的短 system（不是 agent 那条）：

```
You compress dropped coding-agent turns into a brief memo for a later model call.
Include: user goals, files touched, key decisions, errors, remaining work.
Do not invent files or commands. Plain text, at most 400 words. No markdown tables.
```

送给摘要模型的 user 正文：每条 dropped 消息先截到 1500 字，合计最多 24000 字；带上 `previous_summary`（若有）。

**不是一轮。** 这次 complete **不**增加 `LoopState.turn`、**不**走 Parser、**不**执行工具、**不**记 `consecutive_llm_failures`。用户取消则与主循环一样变成 `CancelledError`。

**失败回退（必须）：** 摘要调用抛错、空串、或超时 → 用 §4 的 `_omission_summary`，`ContextCompacted.note` 含 `summary_fallback`。成功则 note 含 `summarized N block(s)`。主任务不得因为摘要失败而停。

**开关：** `Settings.summarize_context`（环境变量 `WAVEMIO_SUMMARIZE_CONTEXT`，默认 `true`）。`false` 时 bootstrap 只接 `TruncatingContextPolicy`（行为与改前一致，便于离线演示）。

**单测：** Fake summarizer 的固定全文出现在 `compacted[1]`；summarizer 抛错则出现 `OMITTED_HEADER`；第二次 compact 把第一次备忘折进 `previous_summary`；`test_loop` 断言摘要 complete 次数不计入 `max_turns`。

## 5. 校准

`ContextManager.observe_usage(usage)`：

```
ratio = usage.prompt_tokens / max(last_estimate, 1)
self.estimator.ratio = clamp(0.6 * old + 0.4 * ratio, 0.6, 1.8)  # 若 estimator 支持
```

没有 usage 的响应（某些流式中间态）跳过。

## 6. 系统提示词位置

system **只存一条**，在 `ConversationStore` 构造时写入，来自 `app/system_prompt.py` 的 `build_system_prompt(..., mode=..., plan_document=...)`。模式切换时 `replace_system`。  
不要每轮改写 system 塞进「当前文件列表」（费 token 且易过期）。让模型用 `list_dir`。

可以在 system 里放 **静态** 信息：工作区绝对路径、工具名单、行为准则。

## 7. `/reset` 与新任务

- `/reset`：`store.reset_keeping_system()`，UI 播放重置动画。已装载的 skill 仍在 system 里（13）。工作区文件与 `/undo` 窗口都不清。
- `/undo`：只还原本任务 `write_file` / `edit_file` 的磁盘改动，不清对话（见 05 §1.1）。
- one-shot：进程级一个 Session，结束即退出。
- REPL 连续提问：不 reset。用户说「新任务」时模型仍看得见旧文件——这是 coding agent 的正确行为。

## 8. 单测要点

- 超长 tool 结果被截断且含 `truncated by agent`。
- assistant+tools 块不会在中间切断（断言 compact 后若存在某 tool_call_id，其 assistant 也在）。
- system 永远 index 0。
- 超预算时从最旧起约 80% 的块进摘要，最近约 20% 留下。
- `SummarizingContextPolicy`：Fake summarizer 的文本在 `compacted[1]`；抛错则 `OMITTED_HEADER`；滚动摘要折入 `previous_summary`。
