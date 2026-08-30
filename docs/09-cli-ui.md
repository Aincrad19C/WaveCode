# 09 · CLI 用户界面（蓝色主色 + 像素风鲸鱼娘）

产品显示名 **Wavemio**（读作 WAVE-mee-oh：wave + mio／澪）。界面常量只出自 `cli/branding.py`。

| 项 | V1 取值 | 说明 |
|----|---------|------|
| 显示名 | `Wavemio` | `PRODUCT_NAME` |
| 吉祥物 | **鲸鱼娘 / Whale-chan** | 社区二创角色，像素风终端绘制，**禁止机器猫 ASCII** |
| 可执行文件 | `wavemio` | 可另注册别名 `coding-agent` |
| 模块 | `python -m coding_agent` | Python 包名保持技术标识 |
| 提示符 | `wavemio ❯ ` | `CLI_NAME` + 样式 `prompt` |

角色视觉与设定对齐 [Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan)（非官方社区项目）。**不要**把该仓库的 Skill 套件、WebP 插画或生成流水线拷进本仓库。我们只做：**原创像素精灵 + 终端半块渲染 + 动态换帧**。著作权与署名见 §10。

像素渲染的算法、分辨率、调色板、类设计见 **[12-whalechan-pixel.md](./12-whalechan-pixel.md)**。本文只规定何时播哪一组动画、版面如何摆。

## 1. 调色（必须遵守）

在 `cli/theme.py` 定义。Token 前缀用 `ui.`，不要用已废弃的品牌词。

| Token | Hex | 用途 |
|-------|-----|------|
| `ui.bg` | `#0B1220` | 面板底 |
| `ui.primary` | `#3B82F6` | 标题、边框、提示符 |
| `ui.deep` | `#1D4ED8` | 次级标题 |
| `ui.cyan` | `#22D3EE` | 高亮 |
| `ui.ice` | `#93C5FD` | 次要文本、reasoning |
| `ui.text` | `#E2E8F0` | 正文 |
| `ui.ok` | `#34D399` | 成功 |
| `ui.warn` | `#FBBF24` | 警告 |
| `ui.err` | `#F87171` | 错误 |
| `ui.tool` | `#60A5FA` | 工具卡片边框 |

鲸鱼娘精灵另有独立 **角色调色板**（发色、鳍耳、围裙），见 12，不要把角色色并进 Theme 键里混用。

Rich Theme 键：`prompt, title, thinking, reasoning, assistant, tool, success, error, muted, mascot`。

禁止默认彩虹乱色。代码块 `Syntax(..., theme="ansi_dark")`，外边框仍用蓝色 Panel。助手最终回复用 Rich Markdown（标题、列表、粗体、围栏代码块同样 `ansi_dark`）；用户输入与斜杠输出仍为纯文本。

## 2. 吉祥物：像素鲸鱼娘（动态）

### 2.1 必须能认出来的特征

每一帧（含 `mini`）都要能看出：

1. 蓝色大波浪发  
2. 头部两侧 **白色三角鲸鳍耳**  
3. 头顶 **喷水/呆毛**（一小缕上翘）  
4. 蓝瞳高光  
5. 深蓝女仆装 + 白围裙（围裙上可有 2×3 像素小鲸标）  
6. `sd` / `chibi` 还要有鲸尾；`mini` 可省略身体只保留头+鳍耳  

形态用社区规范的 **`super-deformed`（约 2.1 头身）** 做状态栏精灵，**`chibi`（约 2.5）** 做启动闪屏。不要画成写实插画，也不要退回纯 ASCII 猫。

### 2.2 动画组（组名稳定，测试与 Sink 依赖这些名字）

| 组 | 帧数 | FPS | 循环 | 表演 |
|----|------|-----|------|------|
| `boot` | 6 | 10 | 一次 | 从右侧滑入，鳍耳晃一下，挥手 |
| `idle` | 4 | 5 | 是 | 呼吸起伏 + 眨眼 + 鲸尾轻摆 |
| `think` | 6 | 8 | 是 | 闭眼皱眉，呆毛转圈，可选一小碗白米饭冒热气 |
| `tool` | 4 | 8 | 是 | 围裙前伸出小手敲击；按工具换道具（见下表） |
| `success` | 5 | 8 | 一次 | 举起米饭碗吃一口，眼睛弯成月牙 |
| `error` | 3 | 6 | 是 | 鼓脸 / 汗滴 / 鳍耳耷拉，仍然可爱 |
| `retry` | 4 | 4 | 是 | 待机打盹（Zzz），对应「马上就开始」梗 |
| `compact` | 2 | 4 | 一次 | 把过大的纸揉成一团（上下文压缩时闪一下） |

工具道具（画在精灵前景 1 层，不要换整套衣服）：

| 工具 | 道具像素 |
|------|----------|
| `read_file` | 打开的小书 |
| `write_file` / `edit_file` | 羽毛笔或铅笔 |
| `list_dir` / `glob_search` | 望远镜 |
| `grep` | 放大镜 |
| `bash` | 小键盘 / 终端方块 |

### 2.3 何时播放

由 `RichEventSink` 驱动 `WhalechanAnimator`，Loop **不知道**帧。

| 事件 | 动画 |
|------|------|
| SessionStarted | `boot` 播完 → 定格 `idle` 闪屏标题 |
| LLMRequestStarted | `think` 循环 |
| ReasoningDelta / ContentDelta | **停掉大尺寸 Live**，左侧改挂 `mini` 静态或 2 帧慢眨眼，右侧流式文本（避免和 Live 抢行缓冲） |
| ToolCallScheduled | `tool` + 对应道具 |
| ContextCompacted | 闪 `compact` 再回当前状态 |
| FinalAnswer | `success` 一次 → `idle` |
| AgentWarned / 重试 | `retry` |
| AgentFailed | `error` |
| 回到 REPL 提示符 | `idle` mini 在提示符左侧 |

### 2.4 降级

| 条件 | 行为 |
|------|------|
| 非 TTY / `NO_COLOR=1` | 不画像素，一行 `[鲸鱼娘] thinking` 这类标签 |
| `WAVEMIO_ASCII=1` | 极简 ASCII 鲸（`<=(` 造型），仍禁止猫 |
| 终端宽 < 48 或高 < 24 | 只用 `mini`（约 12×7 单元格） |
| 无 truecolor | 角色调色板量化到 256 色，算法见 12 |
| 无 Pillow 且精灵是 PNG | 启动失败？**不允许。** 必须内嵌一份纯 Python 调色板精灵，PNG 只是增强 |

## 3. `WhalechanAnimator`

```python
class WhalechanAnimator:
    def play(self, group: str, *, prop: str | None = None) -> None: ...
    def live_group(self, group: str, *, prop: str | None = None) -> AbstractContextManager: ...
    def mini_text(self, group: str, tick: int) -> Text: ...
    def stop(self) -> None: ...
```

预渲染：进程启动时把所有帧变成 `rich.Text`（或纯 ANSI 字符串），动画热路径只换帧，不跑 Pillow。

## 4. 布局

```
[boot：chibi 像素鲸鱼娘 + 蓝框标题「Wavemio」]

┌─ 你 ─────────────────────────────────┐
│ 帮我写一个 hello.py                  │
└──────────────────────────────────────┘

  ┌ sprite sd ┐
  │ 像素鲸鱼娘 │   正在思考…
  │  think     │   （reasoning 灰色斜体，最多 6 行滚动）
  └────────────┘

┌─ 鲸鱼娘 ──────────────────────────────┐
│ （流式正文；左侧可附 mini 头像）      │
└───────────────────────────────────────┘

┌─ 工具 read_file ───────────────────────┐
│ path: hello.py                         │
│ 翻开文件 · 12ms · ok                   │
└───────────────────────────────────────┘

  （success 吃米饭动画）

wavemio ❯ 
```

用户气泡边框 `ui.deep`，助手 `ui.primary`，工具 `ui.tool`。助手 Panel 标题写 **鲸鱼娘**（角色），产品名只出现在 banner / `--version` / 提示符。

启动标题：

```
 ╔══════════════════════════════════════╗
 ║   Wavemio · DeepSeek                 ║
 ║   像素鲸鱼娘已就位 · 先吃饭后推理？   ║
 ╚══════════════════════════════════════╝
```

第二行是彩蛋口吻，不要在 system prompt 里让模型真的去找米饭。

## 5. argparse

```
wavemio [--workdir PATH] [--model NAME] [--mode ask|plan|agent] [--think] [--no-stream]
        [--verbose] [--max-turns N] [--timeout S]
        {run,repl} ...

wavemio                 # 默认 repl
wavemio repl
wavemio run "task text"
wavemio run -           # 从 stdin 读任务
```

`--version` 打印 `wavemio 0.2.0`（数字读 `coding_agent.__version__`，与 `docs/CHANGELOG.md` 最新版本一致）。  
`cli/branding.py`：`PRODUCT_NAME = "Wavemio"`、`CLI_NAME = "wavemio"`。

斜杠命令：

| 命令 | 行为 |
|------|------|
| `/help` | 列出命令与工具名 |
| `/reset` | 清空对话 |
| `/undo` | 还原本任务 `write_file` / `edit_file`（见 05） |
| `/tools` | 列出 schema 名与一句话 |
| `/status` | 工作区、模型、turn、token 估计；无 thinking 的模型不写 thinking 行 |
| `/quit` `/exit` `/q` | 告别（短 `idle`/挥手）后退出 |
| `/model` | 打开模型勾选列表（只显示 id；不含视觉模型；带参数则 warn） |
| `/mode` | 切换 ask / plan / agent。全屏单选；也可 `/mode plan`。输入框最前用颜色标出当前模式 |
| `/setting` | 打开设置：thinking、流式、轮次、上下文长度。全屏空格切换、←→ 调节；也可 `/setting thinking on` 这类写法 |
| `/think on\|off` | 切换 thinking；当前模型不支持时 warn，且不出现在 `/help` |
| `/mascot` | 打开立绘包勾选列表 |
| `/skill` | 打开 skill 勾选列表 |

未知 `/xxx`：warn，不送进模型。

全屏输入 `/` 后，输入框上方列出匹配的命令。↑↓ 选择，Enter 补全（不立刻执行）；命令已完整时 Enter 才发送。`/mode` `/setting` `/think` `/vim` 补全后带一个空格。没有斜杠前缀时 ↑↓ 仍翻历史输入。

## 6. 提示符

`wavemio ❯ ` 样式 `prompt`。空输入忽略。V1 必须支持行末 `\` 续行。

## 7. `RichEventSink` 映射表

| 事件 | UI |
|------|----|
| SessionStarted | boot 像素动画 + banner |
| UserMessageAccepted | 用户 Panel |
| LLMRequestStarted | think 像素 Live |
| ReasoningDelta | ice 斜体追加 |
| ContentDelta | 助手 Panel 追加 + mini 头像 |
| ToolCallScheduled | 工具 Panel 头 + tool 动画/道具 |
| ToolExecutionFinished | 状态行 ok/err + 耗时 |
| ContextCompacted | muted 一行 + compact 闪帧 |
| FinalAnswer | success 吃米饭 + 正文 |
| AgentWarned | warn + retry 打盹 |
| AgentFailed | error 鼓脸 |
| SessionEnded | REPL 回提示符；one-shot 结束 |

## 8. 无障碍

- `NO_COLOR=1` 或非 TTY：纯文本事件，无像素、无动画。
- `WAVEMIO_ASCII=1`：ASCII 鲸标签。
- `sys.stdout.isatty()` 检测。

## 9. 演示友好（2 分钟视频）

- boot ≤ 1.2s，必须能看清鳍耳和蓝发。  
- think 循环必须明显（呆毛转或米饭热气）。  
- 工具卡片仍要出现 `read_file` / `bash` 字样，评委看的是 agent，不只是皮。  
- 不要用 Kitty/Sixel 贴原画：评委终端不一定支持，而且不是「命令行像素风」。

## 10. 署名与许可证（实现时写进 `/help` 与 README）

- 鲸鱼娘为社区二创角色，本项目为 **非商业** 学生作业。  
- 参考规范：[Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan)（声明非 DeepSeek 官方）。  
- 已知原画相关作者：B 站 ZipZipPipe、上善无形（见该仓库 README）。  
- 本仓库像素精灵为 **自行绘制的低分辨率再诠释**，不复制其 WebP 原图。  
- 禁止把鲸鱼娘立绘用于违法或侵权内容（他们的免责条款，我们同样遵守）。
