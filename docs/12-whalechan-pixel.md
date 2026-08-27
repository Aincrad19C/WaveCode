# 12 · 终端像素风鲸鱼娘：可行性与实现规格

## 1. 结论（先看这里）

**支持。** 在现代终端里用 **24-bit 真彩色 + 半块字符 `▀`（U+2580）** 可以把精灵图按「每个字符单元格 = 上下两个正方形像素」画出来，再用 Rich `Live` 按 5–10 FPS 换帧，即可得到命令行像素风、会眨眼会挥手的鲸鱼娘。

这不是把 GitHub 上的插画 PNG 直接丢进终端（那是 Kitty/Sixel 位图协议，依赖特殊终端，也不是像素风）。我们要的是：**低分辨率点阵 + 蓝色调色板 + 帧动画**，观感接近 GB/SFC 像素角色，识别特征对齐鲸鱼娘。

| 方案 | 像素风？ | 动态？ | 终端兼容 | V1 |
|------|----------|--------|----------|----|
| 半块 `▀` + truecolor | 是 | Live 换帧 | 2026 年主流终端（GNOME/Konsole/iTerm2/Windows Terminal/Cursor/VS Code） | **采用** |
| 全块 `█` 一格一像素 | 是但格子被拉高 | 同左 | 同左 | 仅作退路 |
| Braille `⣿` | 更像抖动照片 | 同左 | 同左 | 不用（脏，不像像素角色） |
| Kitty / iTerm / Sixel 贴图 | 否（原画像素） | 可以 | 碎片化 | **不用** |
| 纯 ASCII 猫/字画 | 不像鲸鱼娘 | 可以 | 最好 | 仅 `NO_COLOR` 降级 |

技术栈不需要新的 agent 框架：`rich` + 可选 `pillow` + 我们自己写的 `HalfBlockRenderer`。

## 2. 半块映射（必须按此实现）

终端单元格近似 **宽:高 = 1:2**。把精灵的第 `2y` 行与 `2y+1` 行叠进同一单元格：

- 字符：`▀`（上半块）
- 前景色：上像素 RGB
- 背景色：下像素 RGB
- 若上像素 alpha=0 且下像素 alpha=0：输出空格，不设色
- 若仅一侧透明：透明侧用终端默认背景（不画底），不透明侧用 fg 或 `▄` 下半块

ANSI：

```text
\x1b[38;2;R;G;Bm\x1b[48;2;R;G;Bm▀
```

一行结束 `\x1b[0m\n`。相同颜色的连续格子要合并 SGR，避免每像素都打转义（否则 24×32 精灵每帧几十 KB，Live 会闪）。

`HalfBlockRenderer.render(pixels: PixelGrid) -> rich.Text`：

- `PixelGrid`：`height × width` 的 `tuple[RGBA, ...]`，`RGBA=(r,g,b,a)`，`a=0` 透明。
- `height` 必须为偶数；奇数则底边补一行全透明。
- 输出行数 = `height // 2`，列数 = `width`。

**禁止**用 `rich-pixels` / `chafa` / `timg` 作为运行时依赖（多一个黑盒，面试不好讲）。20～40 行代码必须能讲清。

## 3. 分辨率预算

| 档 | 像素 (W×H) | 单元格 (列×行) | 用途 |
|----|------------|----------------|------|
| `chibi` | 32×40 | 32×20 | 仅 boot 闪屏 |
| `sd` | 24×32 | 24×16 | think / tool / success Live |
| `mini` | 12×14 | 12×7 | 流式输出时挂在面板左侧、提示符旁 |

`sd` 在 80×24 终端里约占左三分之一，右侧仍能打工具日志。若 `console.width < 48`，强制 `mini`。

不要做 64×64 全屏立绘：会把编程过程挤出屏幕，评委看不到 tool call。

## 4. 角色调色板（锁死，便于像素手绘）

索引 0 必须是透明。其余为鲸鱼娘身份色，实现时写成 `cli/sprites/palette.py` 常量。

| Index | Hex | 用途 |
|------|-----|------|
| 0 | `00000000` | 透明 |
| 1 | `#0B1220` | 描边 / 瞳孔 |
| 2 | `#1E3A8A` | 女仆裙、深发影 |
| 3 | `#1D4ED8` | 发中层 |
| 4 | `#3B82F6` | 主发色、瞳、围裙小鲸 |
| 5 | `#60A5FA` | 发高光、呆毛/喷水 |
| 6 | `#93C5FD` | 鳍耳阴影、冰色高光 |
| 7 | `#F8FAFC` | 围裙、鳍耳主体、眼白 |
| 8 | `#FFD9C9` | 肤 |
| 9 | `#F87171` | 口、害羞、错误汗 |
| 10 | `#FBBF24` | 米饭、星光 |
| 11 | `#FFFFFF` | 最亮高光（眼点、饭粒） |

手绘精灵只用这些索引，不要每像素随意 RGB，否则换帧时闪色、也难保持「同一只角色」。

## 5. 精灵数据怎么存放

两级，缺一不可：

1. **内嵌 Python（必选，零依赖可跑）**  
   `cli/sprites/whalechan_sd.py` 等：用多行字符串画调色板索引（`0-9a-b` 各代表一像素），解析成 `PixelGrid`。Fable 5 / 实现者必须真的画出能辨认的鲸鱼娘，不能用方块糊弄。

2. **PNG sprite sheet（可选增强）**  
   `src/coding_agent/cli/sprites/*.png`，Pillow 读取。没有 Pillow 时忽略 PNG，走内嵌数据。

字符串格式示例（示意，不是最终美术）：

```text
# 一行 = 一行像素，字符映射见 PALETTE_CHARS = "0123456789ab"
# 下面只是格式，真正的 24×32 帧要画全
000055500000
000547450000
...
```

`SpriteBank`：

```python
class SpriteBank:
    def frame(self, group: str, index: int, *, size: str = "sd", prop: str | None = None) -> PixelGrid: ...
    def count(self, group: str) -> int: ...
```

道具是覆盖在基础帧上的小层（书、笔、碗），先 blit 身体再 blit 道具，透明处不盖。

## 6. 动态播放

```python
class FramePlayer:
    def __init__(self, bank: SpriteBank, renderer: HalfBlockRenderer): ...
    def precompute(self) -> None:
        """启动时把 (group, size, prop, index) 全部 render 成 Text 缓存。"""
    def text(self, group: str, tick: int, **kw) -> Text: ...
```

`RichEventSink` 在 `think` 时：

```python
with Live(console=console, refresh_per_second=8, transient=True) as live:
    t = 0
    while waiting_llm:
        live.update(player.text("think", t))
        t += 1
        # 真正的等待点是 LLM 流式回调，不要 blind sleep 卡死读取
```

流式 token 到达后 **必须 stop Live**，改为静态 `mini` + 文本；否则 Rich Live 会清掉已经打出来的 delta。这是实现时最容易踩的坑。

线程：V1 循环是同步的。`stream()` 在读到第一个 delta 前可以在主线程用 `Live`；一开始出 token 就拆掉。工具执行是阻塞的，适合全程 `tool` Live。

## 7. 颜色降级

```python
def quantize(rgb: RGB, mode: ColorMode) -> RGB: ...
```

- `truecolor`：原样  
- `ansi256`：映射到 6×6×6 立方 + 灰阶  
- `none`：不调用渲染器  

检测：`rich.console.Console().color_system` → `"truecolor" | "256" | "standard" | None`。

## 8. 类放哪

相对 `src/coding_agent/cli/`：

```
branding.py          # PRODUCT_NAME="Wavemio" / CLI_NAME="wavemio"
theme.py
sprites/
  palette.py
  parse.py           # 字符串/PNG → PixelGrid
  whalechan_sd.py    # 内嵌 sd 帧
  whalechan_chibi.py
  whalechan_mini.py
pixel.py             # PixelGrid, HalfBlockRenderer
animator.py          # SpriteBank, FramePlayer, WhalechanAnimator
mascot.py            # 删除「猫帧」；本文件若保留则只做 WhalechanAnimator 的门面
renderer.py          # RichEventSink
```

`09` 里旧的 `MascotFrames` ASCII 猫 **删除**，不要双吉祥物。

单测：

- 偶数高网格 → 行数减半  
- 全透明网格 → 输出仅为空格  
- `think` 组 `count >= 4`  
- 渲染结果含 `▀` 或空格，不含 `^_^` 猫脸  
- `NO_COLOR` 路径不抛异常  

## 9. 明确不做什么

- 运行时调用生图 API 做鲸鱼娘（慢、费、不稳定、还把作业绑死在 ImageGen）。  
- git submodule 整个 `deepseek-whalechan`。  
- 把别人的 WebP 插画缩小当「像素风」（那是缩略图，不是像素画）。  
- 用 emoji 🐋 代替角色（只能当 PNG 缺失时的最后标签，不能当 V1 主视觉）。

## 10. 给实现者的验收标准（视觉）

在 24-bit 终端执行一个 2 秒的 `think` 循环，截图应能让没看过文档的人说出「蓝头发、白鳍耳、女仆、像 DeepSeek 鲸鱼娘」。如果只能看出「一坨蓝色方块」，视为未完成，回去改精灵而不是改循环。
