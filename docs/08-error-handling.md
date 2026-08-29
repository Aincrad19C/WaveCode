# 08 · 错误处理

## 1. 分层策略

```
配置错误     → 启动失败，exit 2，不进循环
认证错误     → 循环立即结束，告诉用户检查 DEEPSEEK_API_KEY
可恢复 LLM   → Client 内退避重试；耗尽则 consecutive_failures
解析错误     → 回灌纠错 user 消息；三次后停
工具错误     → Observation（失败文本），循环继续
摘要 LLM     → 回退原文摘录，主循环继续；不计 consecutive_llm_failures
用户取消     → 干净收尾动画，exit 0（REPL 回到提示符）
编程错误     → 让它崩溃并打印 traceback（不要吞掉 Bug）
```

「工具失败不是 Agent 失败。」这是答辩金句。

## 2. DeepSeek HTTP 映射

| HTTP / 异常 | 类型 | 重试 |
|-------------|------|------|
| 401, 403 | LLMAuthError | 否 |
| 429 | LLMRateLimitError | 是，尊重 `Retry-After` 若可解析，否则 backoff |
| 408, httpx.TimeoutException | LLMTimeoutError | 是 |
| 500, 502, 503, 529 | LLMUnavailableError | 是 |
| 连接错误 | LLMUnavailableError | 是 |
| 200 非 JSON / 缺 choices | LLMBadResponseError | 否（空 body 可特判再试 1 次） |
| 400 含 tool 消息格式 | LLMBadResponseError | 否；Loop 记 warn。若信息像配对错误，这是我们的 bug，应在测试锁不变量 |

响应体错误消息截到 500 字放进 `str(exc)`，**扫描脱敏**：替换 `sk-[a-zA-Z0-9]+`。

## 3. 退避

`ExponentialBackoffRetry`：`sleep = min(cap, base * 2**attempt) + jitter[0, 0.3)`。  
`attempt` 从 0 起。`max_attempts=4` 表示最多 4 次 HTTP（1 次原始 + 3 次重试）。

Sleep 期间 UI 显示「网络重试中」动画，不要假死。

## 4. 工具层

`Tool.run`：

```python
try:
    args = self.validate_args(call.arguments_json)
    text = self.execute(args, ctx)
    return ToolResult(..., ok=True, content=clip(text))
except SchemaValidationError as e:
    return ToolResult(..., ok=False, content=f"argument error: {e}")
except ToolError as e:
    return ToolResult(..., ok=False, content=str(e))
except Exception as e:
    return ToolResult(..., ok=False, content=f"internal tool error: {type(e).__name__}: {e}")
```

最后这个分支要记 logger.exception，便于我们发现 bug，但仍然回灌模型。

`clip` 与上下文截断格式一致（头 70% 尾 20%）。

## 5. 文件系统

- 权限错误：`EACCES: path`
- 只读覆盖失败：同上
- 磁盘满：把 OSError 转字符串，不要 traceback 给模型（太长）；完整 traceback 只打日志

## 6. CLI 退出码

| 码 | 含义 |
|----|------|
| 0 | 正常（含任务未完成但干净退出、用户取消） |
| 2 | 配置 / 缺 API key |
| 3 | 认证失败 |
| 1 | 未捕获异常 |

one-shot 在 `natural` 完成时 0；`max_turns` 也 0（算「有输出的停止」）。只有崩溃才 1。

## 7. 日志

- 使用 `logging`，默认 WARNING 到 stderr（Rich 可接管）。
- `--verbose` → DEBUG。
- 禁止 logger 打印 headers、api_key、完整 `.env`。
- Jsonl 事件里不要有 key。

## 8. 断言与防御

循环开头 `assert` 不变量仅在 `WAVEMIO_DEBUG=1` 时启用，避免生产 assert 被 `-O` 去掉后行为变化。推荐显式 `if settings.debug: self._assert_invariants()`。

V1 Settings 加 `debug: bool = False`。
