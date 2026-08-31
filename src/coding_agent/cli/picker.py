"""Fullscreen checkbox / radio list for /skill, /mascot, /model, /mode, and /setting."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from coding_agent.agent.mode import MODE_DETAILS, MODES, PlanInterview, parse_mode
from coding_agent.cli.sprites.bank import MascotBank
from coding_agent.cli.theme import UI_CYAN, UI_FOAM, UI_ICE, UI_PRIMARY, UI_WARN
from coding_agent.config.settings import Settings
from coding_agent.llm.catalog import ModelInfo, supports_thinking
from coding_agent.skills.bank import MAX_ACTIVE, SkillBank

_SETTING_LABELS = {
    "thinking": "thinking",
    "stream": "流式",
    "turns": "轮次",
    "context": "上下文",
}
TURNS_MIN = 1
TURNS_MAX = 999
CONTEXT_MAX = 200_000
CONTEXT_STEP = 1024


def context_min(reserve: int) -> int:
    return max(8192, reserve + 1024)


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class PickItem:
    name: str
    detail: str
    origin: str
    checked: bool


@dataclass(frozen=True, slots=True)
class PickState:
    kind: str
    title: str
    hint: str
    items: tuple[PickItem, ...]
    cursor: int = 0
    warn: str = ""
    multi: bool = True
    max_checked: int = MAX_ACTIVE
    context_low: int = 8192

    def moved(self, delta: int) -> PickState:
        n = len(self.items)
        if n <= 0:
            return self
        cursor = max(0, min(n - 1, self.cursor + delta))
        return replace(self, cursor=cursor, warn="")

    def toggled(self) -> PickState:
        if not self.items:
            return self
        idx = self.cursor
        current = self.items[idx]
        if self.kind == "setting":
            if current.name not in {"thinking", "stream"}:
                return self
            on = not current.checked
            items = tuple(
                replace(item, checked=on, detail="on" if on else "off") if i == idx else item
                for i, item in enumerate(self.items)
            )
            return replace(self, items=items, warn="")
        if self.multi:
            if not current.checked:
                n_on = sum(1 for item in self.items if item.checked)
                if n_on >= self.max_checked:
                    return replace(self, warn=f"最多同时装载 {self.max_checked} 个")
            items = tuple(
                replace(item, checked=not item.checked) if i == idx else item
                for i, item in enumerate(self.items)
            )
            return replace(self, items=items, warn="")
        if current.checked:
            return self
        items = tuple(
            replace(item, checked=(i == idx)) for i, item in enumerate(self.items)
        )
        return replace(self, items=items, warn="")

    def nudged(self, delta: int) -> PickState:
        if self.kind != "setting" or not self.items or not delta:
            return self
        idx = self.cursor
        current = self.items[idx]
        if current.name in {"thinking", "stream"}:
            on = delta > 0
            items = tuple(
                replace(item, checked=on, detail="on" if on else "off") if i == idx else item
                for i, item in enumerate(self.items)
            )
            return replace(self, items=items, warn="")
        if current.name == "turns":
            n = _clamp_int(int(current.detail) + delta, TURNS_MIN, TURNS_MAX)
            items = tuple(
                replace(item, detail=str(n)) if i == idx else item
                for i, item in enumerate(self.items)
            )
            return replace(self, items=items, warn="")
        if current.name == "context":
            n = _clamp_int(
                int(current.detail) + delta * CONTEXT_STEP, self.context_low, CONTEXT_MAX
            )
            items = tuple(
                replace(item, detail=str(n)) if i == idx else item
                for i, item in enumerate(self.items)
            )
            return replace(self, items=items, warn="")
        return self

    def checked_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.items if item.checked)


def skill_picker(bank: SkillBank) -> PickState:
    items = tuple(
        PickItem(name=name, detail=detail, origin="", checked=checked)
        for name, detail, checked in bank.rows()
    )
    return PickState(
        kind="skill",
        title="Skill",
        hint="空格勾选  Enter 确认  Esc 取消",
        items=items,
        multi=True,
        max_checked=MAX_ACTIVE,
    )


def model_picker(models: Sequence[ModelInfo], *, current: str) -> PickState:
    current_id = current.strip()
    items = tuple(
        PickItem(name=info.id, detail="", origin="", checked=info.id == current_id)
        for info in models
    )
    cursor = next((i for i, item in enumerate(items) if item.checked), 0)
    return PickState(
        kind="model",
        title="模型",
        hint="空格勾选  Enter 确认  Esc 取消",
        items=items,
        cursor=cursor,
        multi=False,
        max_checked=1,
    )


def mascot_picker(bank: MascotBank) -> PickState:
    items = tuple(
        PickItem(name=name, detail="", origin="", checked=checked)
        for name, checked in bank.rows()
    )
    cursor = next((i for i, item in enumerate(items) if item.checked), 0)
    return PickState(
        kind="mascot",
        title="立绘包",
        hint="空格勾选  Enter 确认  Esc 取消",
        items=items,
        cursor=cursor,
        multi=False,
        max_checked=1,
    )


def mode_picker(*, current: str) -> PickState:
    current_id = parse_mode(current) or "agent"
    items = tuple(
        PickItem(name=name, detail=MODE_DETAILS[name], origin="", checked=name == current_id)
        for name in MODES
    )
    cursor = next((i for i, item in enumerate(items) if item.checked), 0)
    return PickState(
        kind="mode",
        title="模式",
        hint="空格勾选  Enter 确认  Esc 取消",
        items=items,
        cursor=cursor,
        multi=False,
        max_checked=1,
    )


def plan_picker(interview: PlanInterview) -> PickState:
    items = tuple(
        PickItem(name=str(i), detail=choice, origin="", checked=i == 1)
        for i, choice in enumerate(interview.choices, 1)
    )
    title = interview.question
    if len(title) > 36:
        title = title[:35] + "…"
    return PickState(
        kind="plan",
        title=title,
        hint="↑↓ 选择  Enter 确认  Esc 自己写",
        items=items,
        cursor=0,
        multi=False,
        max_checked=1,
    )


def setting_picker(settings: Settings) -> PickState:
    items: list[PickItem] = []
    if supports_thinking(settings.deepseek_model):
        items.append(
            PickItem(
                name="thinking",
                detail="on" if settings.thinking else "off",
                origin="",
                checked=settings.thinking,
            )
        )
    items.append(
        PickItem(
            name="stream",
            detail="on" if settings.stream else "off",
            origin="",
            checked=settings.stream,
        )
    )
    items.append(PickItem(name="turns", detail=str(settings.max_turns), origin="", checked=False))
    items.append(
        PickItem(name="context", detail=str(settings.max_context_tokens), origin="", checked=False)
    )
    return PickState(
        kind="setting",
        title="设置",
        hint="空格切换  ← → 调节  Enter 确认  Esc 取消",
        items=tuple(items),
        multi=True,
        max_checked=len(items),
        context_low=context_min(settings.completion_reserve_tokens),
    )


def render_picker(state: PickState, width: int, height: int) -> RenderableType:
    inner_h = max(1, height - 2)
    inner_w = max(12, width - 4)
    header = Text(state.hint, style="muted")
    if state.warn:
        header.append("\n")
        header.append(state.warn, style=UI_WARN)
    rows = len(state.items)
    body_h = max(1, inner_h - (3 if state.warn else 2))
    start = 0
    if rows > body_h:
        start = min(max(0, state.cursor - body_h // 2), rows - body_h)
    visible = state.items[start : start + body_h]
    lines = Text()
    if not visible:
        lines.append("（没有可选项）", style="muted")
    for i, item in enumerate(visible):
        idx = start + i
        if i:
            lines.append("\n")
        pointer = "▸ " if idx == state.cursor else "  "
        style = UI_FOAM if idx == state.cursor else ""
        if state.kind == "setting":
            label = _SETTING_LABELS.get(item.name, item.name)
            lines.append(f"{pointer}{label}  {item.detail}", style=style or UI_CYAN)
            continue
        if state.kind == "plan":
            label = f"{item.name}. {item.detail}"
            if len(label) > inner_w - 2:
                label = label[: max(4, inner_w - 3)] + "…"
            lines.append(f"{pointer}{label}", style=style or UI_CYAN)
            continue
        mark = "✓" if item.checked else " "
        name = item.name[: max(4, inner_w - 18)]
        extra = ""
        if item.origin:
            extra += f"  {item.origin}"
        if item.detail:
            extra += f"  {item.detail}"
        if len(pointer) + 4 + len(name) + len(extra) > inner_w:
            extra = extra[: max(0, inner_w - 4 - len(name) - len(pointer))]
        lines.append(f"{pointer}[{mark}] {name}", style=style or UI_CYAN)
        lines.append(extra, style="muted")
    return Panel(
        Group(header, Text(), lines),
        title=state.title,
        title_align="left",
        box=box.HEAVY,
        border_style=UI_PRIMARY if not state.warn else UI_ICE,
        padding=(0, 1),
        expand=True,
    )
