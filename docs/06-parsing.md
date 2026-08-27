# 06 · 模型输出解析

## 1. 职责边界

| 组件 | 负责 | 不负责 |
|------|------|--------|
| `DeepSeekClient` | HTTP → `ModelResponse`（字段级映射） | 语义、兜底协议 |
| `StreamAssembler` | SSE delta 拼接成与非流式同构的 `ModelResponse` | 执行工具 |
| `ParserPipeline` | 规范化、修补、从 content 提取工具 | 调用工具 |

循环只依赖 `parser.parse(response) -> ModelResponse`。

## 2. HTTP 非流式映射

从 `choices[0]` 读取：

- `message.role` → 恒视为 assistant
- `message.content` → `str | None`（JSON `null` 转 None，不要变成 `"None"`）
- `message.reasoning_content` → 可选
- `message.tool_calls[]`：
  - `id`, `function.name`, `function.arguments`（**arguments 保持字符串**）
- `finish_reason` 映射到 `FinishReason`，未知值 → `UNKNOWN` 并 `AgentWarned`
- `usage` 可缺省

`choices` 缺失或空 → `LLMBadResponseError`（这是传输层，不进 Parser）。

## 3. 流式拼接算法（必须正确）

DeepSeek/OpenAI 风格增量：

```
delta.tool_calls = [{ "index": 0, "id": "call_...", "function": {"name": "read_file", "arguments": ""} }]
后续 chunk: { "index": 0, "function": {"arguments": "{\"path\"" } }
```

`StreamAssembler` 用 `dict[int, Acc]`：

```
Acc: id: str, name: str, arguments: list[str]  # 用 list 再 join，避免 O(n^2)
```

`finish_reason` 出现在某 chunk 的 `choices[0].finish_reason`。  
`usage` 常在最后一个 chunk。

忽略无法 JSON 解析的 SSE 行（打 debug 即可），但若整个流结束仍无任何 choice，则 `LLMBadResponseError`。

## 4. `NativeToolCallParser`

若 `message.tool_calls` 非空：

对每个 call：

1. `name` 剥离空白；空 name → 丢弃该 call 并 warn。
2. `arguments_json` 若为空，视为 `{}`。
3. 尝试 `json.loads`；失败则 `repair_json_object` 再 loads；仍失败：保留原字符串，让 Tool.validate 去失败（不要在这里丢弃整个响应）。
4. 若 loads 成功但结果不是 dict：视为非法，该 call 的 arguments 改写为 `{"_error": "arguments must be object"}` 仍交给执行器失败。

若原生 tool_calls 全部被丢弃（names 空），当作无工具，进入 Fallback。

`finish_reason` 若为 `stop` 但存在合法 tool_calls：**以工具为准**（有些模型会标错 finish_reason）。规范化为 `TOOL_CALLS`。

## 5. `ContentFallbackParser`

仅当 **没有合法原生 tool_calls** 且 `content` 非空时尝试。

按顺序匹配（命中即止）：

### 5.1 XML 块

```xml
<tool_call>
<name>read_file</name>
<arguments>{"path": "a.py"}</arguments>
</tool_call>
```

允许多个。`arguments` 内可以是 JSON 或未转义文本。

### 5.2 围栏 JSON

```json
{"tool": "read_file", "arguments": {"path": "a.py"}}
```
或
```json
{"name": "read_file", "arguments": {...}}
```

### 5.3 伪函数行

```
CALL read_file path="a.py"
```

V1 **只实现 5.1 和 5.2**。5.3 不做，避免误伤普通代码。

若提取到工具：

- 生成 id：`call_fb_{8 hex}`
- 从 content 中 **删除** 已识别的工具块，剩下的作为旁白 `content`
- `finish_reason` 改为 `TOOL_CALLS`
- `tool_calls` 填上

若 content 同时像最终答案又像工具，**工具优先**（coding agent 宁可多跑一步）。

## 6. `repair_json_object`

仅用于 arguments 字符串，步骤：

1. strip
2. 去掉 markdown 围栏 ` ```json ` / ` ``` `
3. 若存在第一个 `{` 和最后一个 `}`，切片
4. 替换 `'` 为 `"` **仅当** 整段看起来像单引号 JSON（非常保守：仅当没有双引号且有单引号）
5. 去掉 `,\s*}` 与 `,\s*]` 尾逗号
6. `json.loads`

失败抛 `ToolCallParseError`。不要用 `eval` / `ast.literal_eval` 执行任意表达式（`True`/`None` 可用正则替换为 `true`/`null`）。

## 7. `ParserPipeline`

```python
def parse(self, response: ModelResponse) -> ModelResponse:
    r = self.native.parse(response)
    if r.message.tool_calls:
        return r
    return self.fallback.parse(r)
```

Fallback 不抛：识别不到就原样返回。循环对「无工具无文本」另有 empty 处理。

仅当 **原生 tool_calls 存在但全部 name 非法且 fallback 也失败** 时，Native 可抛 `ParseError`。更稳：不抛，当空响应处理。V1 选择 **不抛，当空**，由 empty_streak 接管。例外：调用方 `parse()` 仍可在极端情况下抛——循环已有 ParseError 分支，用于 `LLM` 返回了完全非 UTF8 等。保持 ParseError 为「不可恢复的结构」。

## 8. 单测用例表

| 输入 | 期望 |
|------|------|
| 标准 tool_calls + arguments JSON | 1 个 ToolCallRequest |
| arguments 尾逗号 | 修复后执行器能 validate |
| finish_reason=stop 但有 tool_calls | 视为有工具 |
| content 含 `<tool_call>` | fallback 抽出 |
| 普通 markdown 代码块无 tool 字段 | 不误抽 |
| arguments 为数组 | 执行器失败 Result，不崩循环 |
