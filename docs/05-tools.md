# 05 · 工具：定义、注册、本地执行

## 1. 原则

- 模型 **只提议** 调用；执行 100% 在本地。
- 所有文件路径相对 `Workspace.root`，禁止 `..` 逃逸。
- 工具对模型的接口是 JSON Schema；对 Python 的接口是 `execute(args, ctx) -> str`。
- 失败返回字符串错误，不抛到 CLI。
- 输出超长由 `Tool.run` 按 `settings.tool_output_max_chars` 截断（与上下文策略双保险）。

## 2. 通用 JSON Schema 约定

顶层必须是 `type: object`。未列进 `properties` 的参数忽略（`validate_args` 丢掉 extras，不要 500）。缺 `required` 字段 → `SchemaValidationError` → 失败 ToolResult。

字符串路径统一字段名：`path`。目录列表用 `path`，默认 `"."`。

## 3. 内置工具规格

实现放在 `tools/builtin/`。`tools/builtin/__init__.py` 提供 `all_builtin_tools() -> list[Tool]`。

### 3.1 `read_file`

描述：Read a UTF-8 text file from the workspace. Use offset/limit for large files.

参数：

| 名 | 类型 | 必填 | 说明 |
|----|------|------|------|
| path | string | 是 | 相对工作区 |
| offset | integer | 否 | 从第几行开始（1-based），默认 1 |
| limit | integer | 否 | 最多读多少行，默认 400，最大 2000 |

行为：

- 不存在 → 错误字符串 `ENOENT: ...`
- 超过 2MB 的文件必须用 offset/limit；若未指定且文件 > 2MB → 错误，提示用 offset
- 二进制（NUL 或 decode 失败）→ 错误 `binary file`
- 返回带行号：`{n:04d}|{line}` 形式，便于模型 edit

### 3.2 `write_file`

描述：Create or overwrite a UTF-8 file. Always overwrite. Parent dirs are created.

参数：`path` (req), `content` (req string)

行为：写完返回 `wrote {relpath} ({n} bytes, {lines} lines)`。

### 3.3 `edit_file`

描述：Replace **exactly one** occurrence of `old_text` with `new_text` in a file. `old_text` must uniquely identify the span.

参数：`path`, `old_text`, `new_text` 全必填。

行为：

- 0 次匹配 → 错误，附上附近模糊建议（可选：列出包含 old_text 前 40 字的行号）
- \>1 次 → 错误 `old_text matched N times; make it unique`
- 1 次 → 替换并返回 `edited {path}` + 一个 3 行上下文 diff（unified，短）

**不要**做正则替换。这是字面量替换。

### 3.4 `list_dir`

参数：`path` 默认 `"."`，`max_entries` 默认 200。

返回：每行 `d name` 或 `f name`（目录/文件），先目录后文件，按名排序。超过 max 时最后一行 `... and N more`。

忽略：`.git`、`.wavemio`、`.coding_agent`、`__pycache__`、`node_modules`、`.venv` 的**递归展示**；`list_dir` 只列一层，但不要进入上述目录名的展示？仍应列出这些名字（让模型知道存在），只是不强制递归——本工具本就不递归。

### 3.5 `glob_search`

参数：`pattern` 必填（glob，相对 root，如 `**/*.py`），`max_results` 默认 200。

用 `pathlib.Path.rglob` 或 `glob.glob(..., recursive=True)`。过滤逃逸。跳过 `.git/` `.venv/` `node_modules/` `__pycache__/`。

返回相对路径，每行一个。

### 3.6 `grep`

参数：`pattern`（必填，Python `re` 文本，默认不是正则？**V1 用正则**，`flags` 可选 `i`）。`path` 默认 `"."`（文件或目录）。`max_matches` 默认 50。

对每个文本文件搜索。跳过二进制与忽略目录。行格式：`relpath:line_no:line_text`。

正则编译失败 → 错误。

### 3.7 `bash`

参数：`command` 必填 string。`timeout_s` 可选，默认 `settings.bash_timeout_s`，上限 120。

行为：

```python
subprocess.run(
    command,
    shell=True,
    cwd=str(workspace.root),
    env=sanitized_env(),   # 去掉 API_KEY 等
    capture_output=True,
    text=True,
    timeout=timeout,
    start_new_session=True,  # 便于超时 kill 进程组
)
```

超时：`os.killpg` + 错误 `TIMEOUT after Ns`。

返回：

```
exit_code: N
stdout:
...
stderr:
...
```

stdout+stderr 合计超 `tool_output_max_chars` 则截断。

**安全边界（V1 务实，不为了「完美沙箱」阻塞作业）：**

- 不实现完整 seccomp。
- 依赖 Workspace cwd：相对路径默认落在项目内。
- 模型仍可能 `bash` 出工作区（`cd /`）。文档化这一限制；在 system prompt 要求「不要离开工作区」。
- 拒绝空命令。
- 不拦截 `rm -rf`（面试可讨论；V1 靠工作区与用户本地责任）。可选：若 command strip 后等于 `rm -rf /` 或 `rm -rf ~` 则拒绝。实现 **黑名单极小集**：`rm -rf /`、`rm -rf /*`、`mkfs`、`dd if=`。不必追求完备。

## 4. 执行器细节

`execute_all`：

1. 空列表直接返回。
2. 每个 call 先 `ToolCallScheduled`（循环里也会发一次；**执行器内再发 Started/Finished 即可**，循环不要重复 Started）。以 03 伪代码为准：循环发 Scheduled，执行器发 Started/Finished。
3. `validate` 失败：`ToolResult(ok=False, content="invalid arguments: ...")`。
4. 墙钟：单个工具超过 `ctx.timeout_s`（bash 用自己的 timeout）→ `ToolTimeoutError` 转 Result。

`sanitized_env()`：从 `os.environ` copy，删除键名正则：

```
r"(?i)(key|token|secret|password|passwd|authorization)$"
```

以及精确 `DEEPSEEK_API_KEY`。保留 `PATH`、`HOME`、`LANG`、`TERM`。

## 5. 注册

`build_default_registry()` 按下列 **稳定顺序** 注册（schema 顺序影响模型偏好，保持确定）：

1. read_file  
2. write_file  
3. edit_file  
4. list_dir  
5. glob_search  
6. grep  
7. bash  

## 6. 给模型的工具使用策略（写入 system prompt，不是代码分支）

- 先 `list_dir` / `glob_search` 再改文件。
- 改已有文件优先 `edit_file`，不要整文件 `write_file`，除非新建。
- 跑测试用 `bash`。
- 不要编造没读过的文件内容。
- 完成任务后用自然语言总结，**不要**再调用工具。

## 7. 单测

- `Workspace.resolve("../etc/passwd")` 抛 `ToolPathError`。
- `edit_file` 0/1/2 次匹配。
- `bash` 环境中无 `DEEPSEEK_API_KEY`（测试里 monkeypatch 进去再断言子进程 env）。可用 `command='python -c "import os;print(os.environ.get(\'DEEPSEEK_API_KEY\'))"'` 期望打印 `None`。
