"""Ocean chrome: wave strip, workspace HUD, and rounded panels.

The left rail shows a 32x32 half-block sprite from the current pack/pose. GIF poses loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich import box
from rich.cells import cell_len
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from coding_agent import __version__
from coding_agent.cli.branding import (
    GLYPH_FLOW,
    GLYPH_WAVE,
    PRODUCT_NAME,
    TAGLINE,
)
from coding_agent.cli.sprites.bank import get_bank
from coding_agent.cli.theme import (
    UI_CYAN,
    UI_DEEP,
    UI_FOAM,
    UI_ICE,
    UI_PRIMARY,
    UI_WARN,
    UI_WHITE,
)

_WAVE_UNITS = "▁▂▃▄▅▆▇▆▅▄▃▂"
_WAVE_COLORS = (
    UI_DEEP,
    UI_PRIMARY,
    UI_CYAN,
    UI_PRIMARY,
    UI_ICE,
    UI_DEEP,
)


@dataclass(frozen=True, slots=True)
class WorkspaceChrome:
    """Persistent session facts for the workspace pane (Claude Code-style)."""

    workdir: str = "."
    model: str = ""
    thinking: bool = False
    show_thinking: bool = True
    stream: bool = True
    turn: int = 0
    max_turns: int = 30
    tokens: int = 0
    max_tokens: int = 32000
    git_branch: str = ""
    version: str = ""
    root: str = ""  # workspace root for the file tree; empty → workdir
    mode: str = "agent"


def short_home_path(path: Path | str) -> str:
    """Render a path with ``~`` when it sits under the user home."""
    resolved = Path(path).expanduser()
    try:
        resolved = resolved.resolve()
    except OSError:
        resolved = Path(path)
    try:
        home = Path.home().resolve()
        rel = resolved.relative_to(home)
        return "~" if str(rel) == "." else "~/" + str(rel)
    except (ValueError, OSError):
        return str(resolved)


def ellipsize_left(text: str, width: int) -> str:
    if width <= 1:
        return "…"
    if cell_len(text) <= width:
        return text
    out = text
    while cell_len("…" + out) > width and out:
        out = out[1:]
    return "…" + out


def detect_git_branch(workdir: Path) -> str:
    """Read ``.git/HEAD`` without spawning git (safe to call every session)."""
    git = workdir / ".git"
    if git.is_file():
        try:
            raw = git.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return ""
        marker = "gitdir:"
        if raw.lower().startswith(marker):
            git = Path(raw.split(":", 1)[1].strip())
            if not git.is_absolute():
                git = workdir / git
        else:
            return ""
    head = git / "HEAD"
    if not head.is_file():
        return ""
    try:
        text = head.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    prefix = "ref: refs/heads/"
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text[:7] if text else ""


def usage_bar(used: int, total: int, width: int = 12) -> str:
    width = max(4, width)
    if total <= 0:
        return "░" * width
    filled = int(width * min(1.0, max(0, used) / total))
    if used > 0 and filled == 0:
        filled = 1
    return "█" * filled + "░" * (width - filled)


def cute_title(label: str) -> str:
    return f"{GLYPH_WAVE} {label}"


def foam_rule(width: int) -> Text:
    return Text("─" * max(1, width), style=f"dim {UI_CYAN}")


def mascot_placeholder(*, phase: int = 0, workdir: Path | str | None = None) -> Text:
    """Current pack/pose for the left rail. ``phase`` is ignored (no idle motion)."""
    _ = phase
    bank = get_bank()
    if workdir is not None:
        bank.set_workdir(workdir)
    return bank.render()


def workspace_hud(
    chrome: WorkspaceChrome,
    *,
    busy: bool = False,
    width: int = 80,
) -> Table:
    """HUD with original field names: 目录 / 模型 / thinking / 流式 / git / 轮次."""
    path = ellipsize_left(short_home_path(chrome.workdir), max(8, min(28, width - 16)))
    state = "思考中" if busy else "已就绪"
    state_style = UI_WARN if busy else UI_CYAN
    stream = "on" if chrome.stream else "off"
    git = chrome.git_branch or "—"

    top = Text()
    top.append(PRODUCT_NAME, style=f"bold {UI_FOAM}")
    top.append("  ", style="")
    top.append(TAGLINE, style=UI_ICE)
    top.append("  ·  ", style="muted")
    top.append(state, style=f"bold {state_style}")

    mid = Text()
    mid.append("目录 ", style=UI_ICE)
    mid.append(path, style=f"bold {UI_FOAM}")
    mid.append("  模型 ", style=UI_ICE)
    mid.append(ellipsize_left(chrome.model or "—", 20), style=UI_FOAM)
    mid.append("  git ", style=UI_ICE)
    mid.append(git, style=UI_CYAN if chrome.git_branch else "muted")

    bottom = Text()
    if chrome.show_thinking:
        think = "on" if chrome.thinking else "off"
        bottom.append("thinking ", style=UI_ICE)
        bottom.append(think, style=UI_CYAN if chrome.thinking else "muted")
        bottom.append("  流式 ", style=UI_ICE)
    else:
        bottom.append("流式 ", style=UI_ICE)
    bottom.append(stream, style=UI_ICE)
    bottom.append("  轮次 ", style=UI_ICE)
    bottom.append(f"{chrome.turn}/{chrome.max_turns}  ", style=UI_FOAM)
    bottom.append(f"{usage_bar(chrome.tokens, chrome.max_tokens, 8)} ", style=UI_CYAN)
    bottom.append(f"{chrome.tokens}/{chrome.max_tokens}", style=UI_ICE)

    grid = Table.grid(expand=True)
    grid.add_row(top)
    grid.add_row(mid)
    grid.add_row(bottom)
    return grid


def content_width(console: Console, cap: int = 76) -> int:
    return max(36, min(console.width - 2, cap))


def wave_strip(width: int, *, phase: int = 0) -> Text:
    """A short rolling swell; width is the number of cells. Waves only."""
    width = max(1, width)
    strip = Text()
    n = len(_WAVE_UNITS)
    for i in range(width):
        tick = i + phase
        style = _WAVE_COLORS[i % len(_WAVE_COLORS)]
        if (i * 13 + phase * 7 + 3) % 19 == 0:
            style = UI_WHITE
        strip.append(_WAVE_UNITS[tick % n], style=style)
    return strip


def ocean_banner(console: Console, *, version: str | None = None) -> None:
    width = content_width(console)
    ver = version or __version__
    body = Text()
    body.append(f"  {GLYPH_WAVE}  ", style=f"bold {UI_CYAN}")
    body.append(PRODUCT_NAME, style=f"bold {UI_FOAM}")
    body.append("   ", style="")
    body.append(TAGLINE, style=UI_ICE)
    body.append(f"\n     v{ver}", style=UI_ICE)
    body.append("  ·  已就绪", style=UI_CYAN)
    console.print(wave_strip(width))
    console.print(
        Panel(
            body,
            box=box.ROUNDED,
            border_style=UI_CYAN,
            padding=(0, 1),
            width=width,
        )
    )
    console.print(wave_strip(width))
    console.print()


def ocean_panel(
    renderable: RenderableType,
    *,
    title: str,
    border: str,
    width: int | None = None,
) -> Panel:
    return Panel(
        renderable,
        title=f"{GLYPH_WAVE} {title}",
        title_align="left",
        box=box.ROUNDED,
        border_style=border,
        padding=(0, 1),
        expand=False,
        width=width,
    )


def activity_line(*, ok: bool, label: str) -> Text:
    mark = GLYPH_FLOW
    style = "success" if ok else "error"
    return Text(f"  {mark} {label}", style=style)
