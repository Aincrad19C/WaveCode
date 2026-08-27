# 设计文档目录（第一版）

本目录是 **Wavemio**（CLI 编程智能体）第一版的设计与实现规格。  
当前版本：**[v0.2.0](./CHANGELOG.md)**。每次改仓库必须先按 Changelog 规则升版本再落笔。  
实现者（含后续一键落地模型）必须按下列顺序阅读，并 **严格按 `10-implementation-spec.md` 落盘**，不得改用任何 Agent 框架。

| 顺序 | 文档 | 用途 |
|------|------|------|
| — | [CHANGELOG.md](./CHANGELOG.md) | 三位版本号与每次修改记录 |
| 0 | [00-overview.md](./00-overview.md) | 产品范围、硬约束、术语、非目标 |
| 1 | [01-architecture.md](./01-architecture.md) | 分层、包结构、依赖方向、设计模式 |
| 2 | [02-class-design.md](./02-class-design.md) | 全部抽象、继承、数据类、方法签名 |
| 3 | [03-agent-loop.md](./03-agent-loop.md) | Agent 循环状态机（核心，必须手写） |
| 4 | [04-context-management.md](./04-context-management.md) | 对话历史与上下文窗口 |
| 5 | [05-tools.md](./05-tools.md) | 工具定义、注册、本地执行、工作区沙箱 |
| 6 | [06-parsing.md](./06-parsing.md) | 模型输出解析与参数校验 |
| 7 | [07-termination.md](./07-termination.md) | 循环终止条件 |
| 8 | [08-error-handling.md](./08-error-handling.md) | 错误分类、重试、不崩溃策略 |
| 9 | [09-cli-ui.md](./09-cli-ui.md) | 蓝色主题 CLI（v1.1 起暂不绘制像素立绘） |
| 10 | [10-implementation-spec.md](./10-implementation-spec.md) | **一键实现圣经**：目录、文件职责、接线、验收 |
| 11 | [11-wire-format.md](./11-wire-format.md) | DeepSeek messages JSON 契约（防 400） |
| 12 | [12-whalechan-pixel.md](./12-whalechan-pixel.md) | 终端半块像素渲染：可行性与精灵规格 |

题目原文：[推免考核题目学生版.pdf](./推免考核题目学生版.pdf)

## 给实现者的硬规则（先读）

1. **禁止** LangChain / LlamaIndex / OpenAI Agents SDK / Claude Agent SDK / AutoGen / CrewAI / DeepSeek Harness / 任何现成 agent 产品套壳。
2. **禁止** 使用 Code Interpreter、Files API 等服务端托管执行。
3. **禁止** 将 API Key 写入源代码、文档、测试、README、提交信息。只允许环境变量或未入库的 `.env`。
4. 循环、工具执行、解析、上下文、终止、错误处理必须是本仓库自己的类，而不是 SDK 内部 agent 循环。
5. 允许：`httpx`、`pydantic`、`rich`、`python-dotenv`，以及 DeepSeek 官方 HTTP Chat Completions + 原生 `tools` 字段。
6. 语言：Python 3.11+。布局：`src/coding_agent/`。
7. 类设计以 `02-class-design.md` 为准；循环以 `03-agent-loop.md` 为准；文件清单以 `10-implementation-spec.md` 为准。三者冲突时，以循环不变量 + 题目硬约束为准，并在代码注释中写明取舍。
