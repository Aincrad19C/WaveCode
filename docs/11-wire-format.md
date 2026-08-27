# 11 · DeepSeek 报文契约（避免 400）

循环不直接造 dict；由 `DeepSeekClient._to_api_messages(messages: Sequence[ChatMessage])` 唯一转换。

## 1. system / user

```json
{"role": "system", "content": "..."}
{"role": "user", "content": "..."}
```

`content` 必须是 string，不能是 null。

## 2. assistant（纯文本结束）

```json
{"role": "assistant", "content": "已写好 hello.py。"}
```

若存在 `reasoning_content`（thinking 模式），**一并发送**：

```json
{
  "role": "assistant",
  "content": "已写好 hello.py。",
  "reasoning_content": "用户要一个脚本，我已经用 write_file..."
}
```

无推理时 **省略** 该键，不要发 `null`（若实测 400 再改为显式 null；默认省略）。

## 3. assistant（带工具，必须原样回放）

```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "write_file",
        "arguments": "{\"path\":\"hello.py\",\"content\":\"print('hi')\\n\"}"
      }
    }
  ]
}
```

规则：

- `arguments` 是 **字符串**，不是已解析对象。
- `id` 必须与随后 tool 消息的 `tool_call_id` 一致。
- 多个 tool_calls 则随后连续多条 `role=tool`，数量相等、顺序一致。
- `content` 有旁白时可以是字符串；没有时用 JSON `null`。

## 4. tool 结果

```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": "wrote hello.py (14 bytes, 1 lines)"
}
```

`content` 必须是 string。失败也同样是 role=tool，例如 `"ENOENT: foo.py"`。

## 5. 合法片段示例

```
system
user                # 用户任务
assistant+tool_calls
tool
tool                # 若上一 assistant 有 2 个 call
assistant           # 最终自然语言
```

禁止：

- tool 插在 user 后面却没有紧邻的 assistant.tool_calls
- 只回 tool 不回带 tool_calls 的 assistant
- 把 ToolResult 当成 user 消息

## 6. 单测

对 `_to_api_messages` 做快照测试：构造上述序列，断言 JSON 可被 `json.dumps` 且键齐全。
