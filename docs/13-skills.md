# 13 · 可装载 Skill（`/skill`）

Skill 是一段 **Markdown 说明书**，教本会话里的模型怎么做某一类事：测试习惯、提交格式、项目约定。不是工具、不是 MCP、不跑脚本。用户输入 **`/skill`**，在勾选列表中启用，全文写入当前会话的 system。

立绘包只换表情；skill 进模型上下文。

## 1. 设计决策

1. **说明书，不是新工具。** 不增加 `read_skill` 之类 tool。模型仍只用现有 7 个工具。加载完全由斜杠命令完成（模型不能自己 `/skill`）。
2. **目录里永远只有短目录，全文按需装载。** system 里列 `name — description`，各 description 截到 160 字。在 `/skill` 勾选列表中确认后，才把对应 `SKILL.md` 正文拼进 system。避免把用户目录里所有 skill 一次塞满窗口。
3. **只注入 `SKILL.md`。** 同目录的 `reference.md` / `scripts/` **不执行、不自动附带**。工作区外的 `~/.wavecode/skills/` 也进不了 `read_file` 沙箱，所以全文必须靠注入。
4. **信任边界。** skill 是用户放进 prompt 的文本，和 Cursor 一样有注入风险。只装自己写的或已审过的包；单份正文最多 8000 字；同时最多 8 个已装载。
5. **`/reset` 不清 skill。** 与立绘包一样，属于会话配置，不是对话轮次。

## 2. 投放目录

后出现的同名覆盖前者（与立绘包相同）：

| 顺序 | 路径 | 用途 |
|------|------|------|
| 0 | 安装包内 `coding_agent/skills/packs/<名>/` | 随包装的默认 skill |
| 1 | `~/.wavemio/skills/<名>/` | 旧目录，只读扫描 |
| 2 | `~/.wavecode/skills/<名>/` | 用户目录（启动时创建） |
| 3 | `<工作区>/.wavemio/skills/<名>/` | 旧工作区，只读 |
| 4 | `<工作区>/.wavecode/skills/<名>/` | 项目约定，可进仓库 |

识别条件：目录内有 `SKILL.md`（大小写敏感）。没有则忽略。

启动全屏 / REPL 时 `ensure_user_skills()`：创建 `~/.wavecode/skills/`，不写入说明文件。不要在文档或 README 里写「吉祥物」「鲸鱼娘」。

安装包内默认 skill 可被用户或工作区同名覆盖：`frontend-design`（仿 Anthropic 官方前端设计 skill）、`tdd`（仿 Matt Pocock 的红绿循环）。

`.wavecode/` 仍在 `IGNORED_DIRS` 里：文件树和 grep 默认不扫 skill 目录，避免把说明书当源码搜。

## 3. `SKILL.md` 格式

与常见 Agent Skill 一致，便于从 Cursor 等处拷贝文件夹：

```markdown
---
name: frontend-design
description: 写或改网页、组件、仪表盘、落地页时用。先定视觉方向再写代码。
---

# Frontend design
- ...
```

| 字段 | 规则 |
|------|------|
| `name` | 可选。展示名；缺省用目录名。目录名是列表标识，须匹配 `[a-z0-9][a-z0-9_-]{0,62}` |
| `description` | 可选但应写。进目录；缺省为 `no description` |
| 其它 YAML 键 | 忽略（含 `disable-model-invocation`：我们不做自动触发） |
| 正文 | frontmatter 之后的 Markdown，装载时注入 |

解析失败（YAML 不是 mapping、文件不可读）：该包跳过，`/skill` 列表里不出现，打日志，不崩启动。

## 4. 斜杠命令

| 输入 | 行为 |
|------|------|
| `/skill` | 全屏：列出全部包并勾选。空格切换、Enter 确认、Esc 取消。REPL：打印带 `[✓]` 的列表 |
| `/skill` 带参数 | warn，提示使用勾选列表，不发给模型 |

`/help` 必须出现 `/skill`。未知 `/xxx` 仍不送模型。装载与卸下只通过勾选列表确认。

## 5. 与 system prompt

`ConversationStore` **仍只有一条** system。装载/卸下时 `replace_system(...)`，后面的 user/assistant/tool **不动**。

`build_system_prompt` 增加可选参数（缺省空，旧调用可用）：

```python
def build_system_prompt(
    *,
    workspace_root: str,
    tool_names: Sequence[str],
    skill_catalog: Sequence[tuple[str, str]] = (),
    active_skills: Sequence[tuple[str, str]] = (),
) -> str:
```

在原有 Rules 之后追加（无目录则整段省略）：

```
Available skills, distinct from tools. The user enables them with the /skill picker:
- frontend-design: 写或改网页、组件、仪表盘、落地页时用。先定视觉方向再写代码。
- tdd: 写功能或修 bug 时先写失败测试再补实现。
```

已装载则再追加：

```
## Active skills
### frontend-design
<SKILL.md body, clipped>
```

模板仍是英文规则 + 这段英文小标题；description / body 保持用户文件原文（可中文）。

## 6. 类（`coding_agent/skills/`）

与立绘包对称，**不要**放进 `tools/`（那会变成模型可调工具）。

```python
@dataclass(frozen=True, slots=True)
class SkillPack:
    name: str            # 目录名，列表标识
    title: str           # frontmatter name 或目录名
    description: str
    body: str            # 已按 8000 字截断
    root: Path

class SkillBank:
    workdir: Path | None
    active: tuple[str, ...]   # 最多 8 个，顺序 = 注入顺序
    def discover(self) -> dict[str, SkillPack]: ...
    def list_text(self) -> str: ...
    def apply(self, token: str) -> tuple[str, str]:
        """slash 分发：无参数返回 pick；带参数 warn。"""
    def replace_active(self, names: list[str]) -> tuple[str, str]: ...
    def catalog(self) -> list[tuple[str, str]]: ...
    def active_bodies(self) -> list[tuple[str, str]]: ...
```

`dispatch_slash("/skill …")` 调 `get_bank().apply` 同类的 `get_skills().apply`，成功后 `session.rebuild_system()`：用当前 workspace、工具名、catalog、active bodies 重建 system 并 `store.replace_system`。

`ensure_user_skills()` 与 `ensure_user_packs()` 一样在 TUI/REPL 启动时调用。

## 7. 单测要点

- 无 `SKILL.md` 的目录不出现在 discover。
- 工作区同名覆盖用户目录。
- `/skill` 无参数：全屏打开勾选；REPL 列表只含包名与说明，不写来源标签或路径。
- `/skill` 带参数：warn，不装载。
- 勾选确认后 `store.all()[0]` 含正文；历史条数除 system 内容外不变。
- 取消勾选后正文消失，目录还在。
- `/reset` 后 active 仍在，对话清空。
- 超长 body 被截到 8000；第 9 个装载被拒绝并 warn。
- 解析失败的包不出现、不抛到 CLI。
- 画面与 `/skill` 文案不出现「吉祥物」「鲸鱼娘」。
