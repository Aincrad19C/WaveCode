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
else: compact until cost <= send_budget or 不能再压
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

**阶段 2 — 滑动窗口**

从 **最新块向前** 累积，直到加入下一块会超过 `send_budget - estimate_tools`。

被丢掉的旧块用 **一条** 合成 user 消息替换（插在 system 之后、保留区之前）：

```
[context compacted] Older turns were omitted. Summary of omitted user tasks:
- <每条被省略的 user 原文截到 200 字>
Files already edited in omitted turns may exist on disk; use list_dir/grep rather than assuming memory.
```

不要用模型摘要（V1 无 SummarizingPolicy）。

**阶段 3 — 保底**

始终保留：

1. system
2. 最近 1 个完整块（即使它单独超预算，也只做阶段 1 截断，绝不删当前未完成的 tool 块）

若最近一块截断后仍大于 budget：照样发送，并 set note=`"prompt_may_exceed_budget"`。

## 5. 校准

`ContextManager.observe_usage(usage)`：

```
ratio = usage.prompt_tokens / max(last_estimate, 1)
self.estimator.ratio = clamp(0.6 * old + 0.4 * ratio, 0.6, 1.8)  # 若 estimator 支持
```

没有 usage 的响应（某些流式中间态）跳过。

## 6. 系统提示词位置

system **只存一条**，在 `ConversationStore` 构造时写入，来自 `app/system_prompt.py` 的 `build_system_prompt(workspace, tool_names)`。  
不要每轮改写 system 塞进「当前文件列表」（费 token 且易过期）。让模型用 `list_dir`。

可以在 system 里放 **静态** 信息：工作区绝对路径、工具名单、行为准则。

## 7. `/reset` 与新任务

- `/reset`：`store.reset_keeping_system()`，UI 播放重置动画。
- one-shot：进程级一个 Session，结束即退出。
- REPL 连续提问：不 reset。用户说「新任务」时模型仍看得见旧文件——这是 coding agent 的正确行为。

## 8. 单测要点

- 超长 tool 结果被截断且含 `truncated by agent`。
- assistant+tools 块不会在中间切断（断言 compact 后若存在某 tool_call_id，其 assistant 也在）。
- system 永远 index 0。
- 省略摘要出现在 system 之后。
