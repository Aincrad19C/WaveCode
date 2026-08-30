"""Fullscreen alternate-screen chat UI (same idea as ``top``: occupy the tty)."""

from __future__ import annotations

import os
import select
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from rich import box
from rich.align import Align
from rich.cells import cell_len
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from coding_agent import __version__
from coding_agent.agent.session import AgentSession
from coding_agent.cli.boot import (
    BOOT_DURATION_S,
    INTRO_DURATION_S,
    REVEAL_DURATION_S,
    boot_panel,
    reveal_from_left,
)
from coding_agent.cli.branding import GLYPH_FLOW, GLYPH_WAVE, PRODUCT_NAME, PROMPT
from coding_agent.cli.chrome import (
    WorkspaceChrome,
    cute_title,
    detect_git_branch,
    foam_rule,
    mascot_placeholder,
    ocean_panel,
    wave_strip,
    workspace_hud,
)
from coding_agent.cli.commands import SlashOutcome, apply_setting_items, dispatch_slash
from coding_agent.cli.editor import KeyAction, LineEditor, NavKeys, PickerKeys
from coding_agent.cli.handoff import file_open_argv
from coding_agent.cli.hub import TAB_LABELS, TABS, get_hub
from coding_agent.cli.picker import (
    mascot_picker,
    model_picker,
    render_picker,
    setting_picker,
    skill_picker,
)
from coding_agent.cli.sidebar import get_sidebar
from coding_agent.cli.sprites.bank import get_bank
from coding_agent.cli.sprites.pack import SPRITE_SIZE, ensure_user_packs
from coding_agent.cli.theme import (
    UI_CYAN,
    UI_DEEP,
    UI_ERR,
    UI_FOAM,
    UI_ICE,
    UI_OK,
    UI_PRIMARY,
)
from coding_agent.cli.view import ChatItem, ChatView, ViewSnapshot
from coding_agent.config.settings import Settings
from coding_agent.llm.catalog import apply_model, discover_models, supports_thinking
from coding_agent.skills.bank import get_skills
from coding_agent.skills.pack import ensure_user_skills

_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_MASCOT_WIDTH = 34
_SPRITE_ROWS = SPRITE_SIZE // 2  # half-block rows
_SPRITE_PANEL_ROWS = _SPRITE_ROWS + 2  # rounded borders; portrait only
_SPLIT_MIN_WIDTH = 76
_HUD_ROWS = 7
_GUTTER = 1
_INPUT_MAX_BODY = 6
_INPUT_BAR_CELLS = 8
_INPUT_CHROME = 4  # panel borders + horizontal padding


def _session_cwd(session: AgentSession, settings: Settings) -> Path:
    executor = getattr(session.loop, "executor", None)
    if executor is not None:
        return Path(executor.workspace.cwd).resolve()
    return settings.workdir.resolve()


class OceanFrame:
    """Live renderable: mascot | workspace / conversation / prompt, filling the tty."""

    def __init__(
        self,
        view: ChatView,
        *,
        chrome: WorkspaceChrome | None = None,
        session: AgentSession | None = None,
        settings: Settings | None = None,
        git_branch: str = "",
        boot_started: float | None = None,
    ) -> None:
        self.view = view
        self._chrome = chrome
        self.session = session
        self.settings = settings
        self.git_branch = git_branch
        self.boot_started = boot_started

    def skip_boot(self) -> None:
        self.boot_started = None

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        width = options.max_width
        height = options.height or console.size.height
        h = max(8, height)
        state = self._intro_state()
        if state is None:
            yield render_frame(
                self.view, chrome=self._live_chrome(), width=width
            )
            return
        kind, t = state
        if kind == "boot":
            yield boot_panel(width, h, t)
            return
        yield reveal_from_left(
            render_frame(self.view, chrome=self._live_chrome(), width=width),
            boot_panel(width, h, 1.0, tide=t * 3.0),
            t,
        )

    def _intro_state(self) -> tuple[str, float] | None:
        if self.boot_started is None:
            return None
        elapsed = time.monotonic() - self.boot_started
        if elapsed < BOOT_DURATION_S:
            return ("boot", max(0.0, min(1.0, elapsed / BOOT_DURATION_S)))
        later = elapsed - BOOT_DURATION_S
        if later < REVEAL_DURATION_S:
            return ("reveal", max(0.0, min(1.0, later / REVEAL_DURATION_S)))
        return None

    def _live_chrome(self) -> WorkspaceChrome:
        if self.session is not None and self.settings is not None:
            state = self.session.loop.state
            cwd = _session_cwd(self.session, self.settings)
            root = self.settings.workdir.resolve()
            executor = getattr(self.session.loop, "executor", None)
            if executor is not None:
                root = Path(executor.workspace.root).resolve()
            return WorkspaceChrome(
                workdir=str(cwd),
                model=self.settings.deepseek_model,
                thinking=self.settings.thinking,
                show_thinking=supports_thinking(self.settings.deepseek_model),
                stream=self.settings.stream,
                turn=state.turn,
                max_turns=self.settings.max_turns,
                tokens=state.estimated_prompt_tokens,
                max_tokens=self.settings.max_context_tokens,
                git_branch=detect_git_branch(cwd),
                version=__version__,
                root=str(root),
            )
        return self._chrome or WorkspaceChrome(version=__version__)


def render_frame(
    view: ChatView, chrome: WorkspaceChrome | None = None, *, width: int = 80
) -> Layout:
    chrome = chrome or WorkspaceChrome(version=__version__)
    inner_w = max(24, width - 2)
    snap = view.snapshot()
    split = inner_w >= _SPLIT_MIN_WIDTH
    rail = (_MASCOT_WIDTH + _GUTTER) if split else 0
    main_w = max(24, inner_w - rail)
    input_inner = max(8, main_w - _INPUT_CHROME)
    lines, hint = _input_viewport(snap, input_inner)
    layout = Layout()
    layout.split_column(
        Layout(name="wave", size=1),
        Layout(name="body", ratio=1),
    )
    layout["wave"].update(_WaveRule())
    if split:
        layout["body"].split_row(
            Layout(name="mascot", size=_MASCOT_WIDTH),
            Layout(name="gutter", size=_GUTTER),
            Layout(name="main", ratio=1),
        )
        layout["mascot"].split_column(
            Layout(name="sprite", size=_SPRITE_PANEL_ROWS),
            Layout(name="rail", ratio=1),
        )
        layout["sprite"].update(_MascotRail(chrome.workdir))
        root = chrome.root or chrome.workdir
        layout["rail"].update(
            _FileChangeRail(
                root, files_focus=snap.focus == "files", changes_focus=snap.focus == "changes"
            )
        )
        layout["gutter"].update(_VRule())
        main = layout["main"]
    else:
        main = layout["body"]
    main.split_column(
        Layout(name="hud", size=_HUD_ROWS),
        Layout(name="gap_hud", size=1),
        Layout(name="tabs", size=1),
        Layout(name="content", ratio=1),
        Layout(name="status", size=1),
        Layout(name="input", size=2 + max(1, len(lines))),
    )
    main["hud"].update(_Hud(chrome, snap))
    main["gap_hud"].update(_HRule())
    main["tabs"].update(_TabBar())
    hub = get_hub()
    if hub.tab == "text":
        main["content"].update(_TextPane())
    else:
        main["content"].update(_ChatPane(view))
    main["status"].update(_StatusBar(view))
    main["input"].update(_InputBar(lines, hint, focused=snap.focus == "input"))
    frame = Layout()
    frame.split_column(
        Layout(name="north", size=1),
        Layout(name="mid", ratio=1),
        Layout(name="south", size=1),
    )
    frame["mid"].split_row(
        Layout(name="west", size=1),
        Layout(name="core", ratio=1),
        Layout(name="east", size=1),
    )
    frame["north"].update(_FrameCap("top"))
    frame["south"].update(_FrameCap("bottom"))
    frame["west"].update(_FrameSide())
    frame["east"].update(_FrameSide())
    frame["core"].update(layout)
    return frame


class _FrameCap:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        width = max(2, options.max_width)
        if self.kind == "top":
            line = "┏" + "━" * (width - 2) + "┓"
        else:
            line = "┗" + "━" * (width - 2) + "┛"
        yield Text(line, style=UI_PRIMARY)


class _FrameSide:
    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        height = max(1, options.height or 1)
        yield Text("\n".join(["┃"] * height), style=UI_PRIMARY)


class _HRule:
    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        yield foam_rule(options.max_width)


class _VRule:
    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        height = max(1, options.height or 1)
        yield Text("\n".join(["│"] * height), style=f"dim {UI_CYAN}")


class _WaveRule:
    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        yield wave_strip(options.max_width, phase=int(time.monotonic() * 5))


class _MascotRail:
    def __init__(self, workdir: str = ".") -> None:
        self.workdir = workdir

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        yield Panel(
            mascot_placeholder(workdir=self.workdir),
            box=box.ROUNDED,
            border_style=UI_ICE,
            padding=(0, 0),
            expand=True,
        )


def file_change_heights(total: int) -> tuple[int, int]:
    """Split remaining rail height 1:1 (files, changes). Odd leftover goes to files."""
    total = max(2, total)
    changes_h = total // 2
    return total - changes_h, changes_h


class _FileChangeRail:
    """File tree and Changes as two flush panels, split 1:1."""

    def __init__(
        self, root: str = ".", *, files_focus: bool = False, changes_focus: bool = False
    ) -> None:
        self.root = root
        self.files_focus = files_focus
        self.changes_focus = changes_focus

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        pane = get_sidebar()
        pane.set_root(self.root)
        files_h, changes_h = file_change_heights(options.height or 12)
        inner = Layout()
        inner.split_column(
            Layout(name="files", size=files_h),
            Layout(name="changes", size=changes_h),
        )
        inner["files"].update(_FilesPane(self.root, focused=self.files_focus))
        inner["changes"].update(_ChangesPane(self.root, focused=self.changes_focus))
        yield inner


class _FilesPane:
    """Workspace tree. Lives under the portrait, not inside it."""

    def __init__(self, root: str = ".", *, focused: bool = False) -> None:
        self.root = root
        self.focused = focused

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        pane = get_sidebar()
        pane.set_root(self.root)
        inner_w = max(4, options.max_width - 4)
        inner_h = max(1, (options.height or 8) - 2)
        yield Panel(
            pane.render_files(width=inner_w, height=inner_h, focused=self.focused),
            title=cute_title("文件" + ("  ·  选择" if self.focused else "")),
            title_align="left",
            box=box.SQUARE,
            border_style=UI_FOAM if self.focused else UI_CYAN,
            padding=(0, 1),
            expand=True,
            subtitle=pane.file_hint or None,
            subtitle_align="right",
        )


class _ChangesPane:
    """Per-turn git / tool Changes. Separate box from the file tree."""

    def __init__(self, root: str = ".", *, focused: bool = False) -> None:
        self.root = root
        self.focused = focused

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        pane = get_sidebar()
        pane.set_root(self.root)
        inner_w = max(4, options.max_width - 4)
        inner_h = max(1, (options.height or 4) - 2)
        yield Panel(
            pane.render_changes(width=inner_w, height=inner_h, focused=self.focused),
            title=cute_title("Changes" + ("  ·  选择" if self.focused else "")),
            title_align="left",
            box=box.SQUARE,
            border_style=UI_FOAM if self.focused else UI_CYAN,
            padding=(0, 1),
            expand=True,
            subtitle=pane.change_hint or None,
            subtitle_align="right",
        )


class _Hud:
    def __init__(self, chrome: WorkspaceChrome, snap: ViewSnapshot) -> None:
        self.chrome = chrome
        self.snap = snap

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        ver = self.chrome.version or __version__
        yield Panel(
            workspace_hud(
                self.chrome,
                busy=self.snap.busy,
                width=max(12, options.max_width - 4),
            ),
            title=cute_title(f"工作区  ·  v{ver}"),
            title_align="left",
            box=box.SQUARE,
            border_style=UI_CYAN,
            padding=(0, 1),
            expand=True,
        )


class _TabBar:
    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        hub = get_hub()
        line = Text()
        for name in TABS:
            label = _tab_label(name)
            active = hub.tab == name
            style = f"reverse bold {UI_FOAM}" if active else f"dim {UI_ICE}"
            line.append(f" {label} ", style=style)
            line.append(" ")
        yield line


def _tab_label(name: str) -> str:
    return TAB_LABELS[name]


class _ChatPane:
    def __init__(self, view: ChatView) -> None:
        self.view = view

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        snap = self.view.snapshot()
        width = options.max_width
        height = options.height or 8
        if snap.picker is not None:
            yield render_picker(snap.picker, width, height)
            return
        inner_h = max(1, height - 2)
        inner_w = max(8, width - 4)
        body = _fit_chat(snap, inner_w, inner_h)
        yield Panel(
            body,
            title=cute_title("对话"),
            title_align="left",
            box=box.HEAVY,
            border_style=UI_PRIMARY,
            padding=(0, 1),
            expand=True,
        )


class _TextPane:
    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        hub = get_hub()
        width = max(8, options.max_width - 4)
        height = max(1, (options.height or 8) - 2)
        lines = hub.visible_styled(height)
        body = Text()
        start = hub.file_scroll
        gutter = 0 if hub.file_mode == "diff" else 5
        limit = max(1, width - gutter)
        for i, line in enumerate(lines):
            if i:
                body.append("\n")
            if hub.file_mode != "diff":
                body.append(f"{start + i + 1:>4} ", style="muted")
            clipped = line.copy()
            clipped.overflow = "crop"
            clipped.no_wrap = True
            if cell_len(clipped.plain) > limit:
                clipped.truncate(limit)
            body.append_text(clipped)
        title = hub.file_title or "文本"
        if hub.file_mode == "diff":
            title = f"改动  {title}"
        yield Panel(
            body,
            title=cute_title(title),
            title_align="left",
            box=box.HEAVY,
            border_style=UI_ICE,
            padding=(0, 1),
            expand=True,
        )


class _StatusBar:
    def __init__(self, view: ChatView) -> None:
        self.view = view

    def __rich__(self) -> Table:
        snap = self.view.snapshot()
        row = Table.grid(expand=True)
        row.add_column()
        row.add_column(justify="right")
        if snap.status:
            spin = _SPIN[int(time.monotonic() * 10) % len(_SPIN)]
            left = Text(f" {spin}  {snap.status}", style=UI_ICE)
        else:
            left = Text(f" {GLYPH_WAVE} 就绪", style=UI_ICE)
        if snap.picker is not None:
            right = Text("j/k 移动  ·  空格勾选  ·  Enter 确认  ·  Esc 取消", style="muted")
        elif snap.focus == "files":
            right = Text(
                "j/k 滚轮  ·  Enter 展开/打开  ·  d 改动  ·  Tab Changes",
                style="muted",
            )
        elif snap.focus == "changes":
            right = Text("j/k 滚轮  ·  Enter 改动  ·  Tab 对话  ·  Esc 输入", style="muted")
        elif snap.focus == "text":
            right = Text("j/k 滚动  ·  F1 对话  ·  Tab 文件", style="muted")
        else:
            right = Text(
                "Tab 文件  ·  Ctrl+T 标签  ·  Enter 发送  ·  /help",
                style="muted",
            )
        row.add_row(left, right)
        return row


class _InputBar:
    def __init__(self, lines: tuple[str, ...], hint: str, *, focused: bool = True) -> None:
        self.lines = lines
        self.hint = hint
        self.focused = focused

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        body = Text(style="prompt", no_wrap=True, overflow="crop")
        for i, line in enumerate(self.lines):
            if i:
                body.append("\n")
            body.append(line)
        yield Panel(
            body,
            box=box.DOUBLE,
            border_style=UI_FOAM if self.focused else f"dim {UI_CYAN}",
            padding=(0, 1),
            expand=True,
            title=cute_title("输入"),
            title_align="left",
            subtitle=self.hint or None,
            subtitle_align="right",
        )


def _wrap_cells(text: str, width: int) -> list[str]:
    """Hard-wrap ``text`` to ``width`` terminal cells, keeping ``\\n``."""
    width = max(1, width)
    rows: list[str] = []
    for para in text.split("\n"):
        if not para:
            rows.append("")
            continue
        buf = ""
        for ch in para:
            candidate = buf + ch
            if cell_len(candidate) <= width:
                buf = candidate
                continue
            if buf:
                rows.append(buf)
            buf = ch
            if cell_len(buf) > width:
                rows.append(buf)
                buf = ""
        rows.append(buf)
    return rows or [""]


def _cursor_row(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if "█" in line:
            return i
    return max(0, len(lines) - 1)


def _thumb_bar(offset: int, visible: int, total: int, width: int) -> str:
    if width <= 0:
        return ""
    if total <= visible:
        return "█" * width
    thumb = max(1, min(width, round(width * visible / total)))
    max_pos = width - thumb
    pos = round(offset / (total - visible) * max_pos) if max_pos else 0
    pos = max(0, min(max_pos, pos))
    return "░" * pos + "█" * thumb + "░" * (width - pos - thumb)


def _input_window(lines: list[str], max_rows: int) -> tuple[list[str], int]:
    total = len(lines)
    if total <= max_rows:
        return lines, 0
    cur = _cursor_row(lines)
    start = max(0, min(cur - max_rows + 1, total - max_rows))
    return lines[start : start + max_rows], start


def _input_scroll_hint(offset: int, visible: int, total: int) -> str:
    if total <= visible:
        return ""
    start = offset + 1
    end = offset + visible
    parts: list[str] = []
    if offset:
        parts.append("↑")
    parts.append(_thumb_bar(offset, visible, total, _INPUT_BAR_CELLS))
    if end < total:
        parts.append("↓")
    parts.append(f"{start}-{end}/{total}")
    return "  ".join(parts)


def _input_viewport(snap: ViewSnapshot, inner_width: int) -> tuple[tuple[str, ...], str]:
    hub = get_hub()
    if snap.picker is not None:
        title = "勾选 skill" if snap.picker.kind == "skill" else "勾选立绘包"
        return (f"{GLYPH_WAVE} {title}",), "空格勾选  Enter 确认  Esc 取消"
    if snap.busy:
        return (f"{GLYPH_WAVE} 思考中，Ctrl+C 取消",), ""
    if hub.tab == "text" and snap.focus not in {"files", "changes", "input"}:
        title = hub.file_title or "文本"
        total = len(hub.file_lines) or 1
        vis = 12
        return (f"{GLYPH_WAVE} {title}",), _input_scroll_hint(hub.file_scroll, vis, total)
    wrapped = _wrap_cells(PROMPT + snap.input_buffer, max(8, inner_width))
    visible, offset = _input_window(wrapped, _INPUT_MAX_BODY)
    return tuple(visible), _input_scroll_hint(offset, len(visible), len(wrapped))


def _fit_chat(snap: ViewSnapshot, width: int, height: int) -> RenderableType:
    items = list(snap.items)
    if snap.scroll and items:
        cut = min(snap.scroll, max(0, len(items) - 1))
        if cut:
            items = items[:-cut]
    if not items:
        welcome = Text(justify="center")
        welcome.append(f"{PRODUCT_NAME}\n", style=f"bold {UI_FOAM}")
        welcome.append(snap.placeholder, style="muted")
        return Align.center(welcome, vertical="middle")
    inner = max(8, width)
    chosen: list[ChatItem] = []
    used = 0
    for item in reversed(items):
        h = _item_height(item, inner)
        gap = 1 if chosen else 0
        if chosen and used + h + gap > height:
            break
        chosen.append(item)
        used += h + gap
        if used >= height:
            break
    chosen.reverse()
    parts: list[RenderableType] = []
    for i, item in enumerate(chosen):
        if i:
            parts.append(Text())
        parts.append(_render_item(item, width))
    return Group(*parts)


def _item_height(item: ChatItem, inner: int) -> int:
    text_w = max(8, inner - 4)
    lines = _wrapped_lines(item.text, text_w)
    if item.kind == "note":
        return 1
    if item.kind == "tool":
        return 4 if "\n" in item.text else 3
    if item.kind == "user":
        return 2 + lines
    if item.kind == "assistant":
        return 2 + lines
    return 2 + lines


def _wrapped_lines(text: str, width: int) -> int:
    width = max(1, width)
    total = 0
    for para in text.split("\n"):
        n = cell_len(para)
        total += max(1, (n + width - 1) // width) if n else 1
    return total or 1


def _render_item(item: ChatItem, width: int) -> RenderableType:
    if item.kind == "tool":
        first, _, rest = item.text.partition("\n")
        preview = rest.splitlines()[0][:80] if rest else ("ok" if item.ok else "失败")
        mark = "ok" if item.ok else "失败"
        return Panel(
            Text(preview, style="muted" if item.ok else "error"),
            title=f"{GLYPH_FLOW} {first}  ·  {mark}",
            title_align="left",
            box=box.SIMPLE,
            border_style=UI_OK if item.ok else UI_ERR,
            padding=(0, 1),
            expand=True,
        )
    if item.kind == "note":
        return Text(f"  {GLYPH_WAVE} {item.text}", style="muted")
    if item.kind == "error":
        return ocean_panel(item.text, title=item.title or "失败", border=UI_ERR, width=width)
    if item.kind == "user":
        return Panel(
            Text(item.text, style="user"),
            title=f"{GLYPH_WAVE} 你",
            title_align="left",
            box=box.SIMPLE,
            border_style=UI_DEEP,
            padding=(0, 1),
            expand=True,
        )
    if item.kind in ("help", "tools", "status"):
        return ocean_panel(
            item.text, title=item.title or item.kind, border=UI_ICE, width=width
        )
    return Panel(
        Text(item.text, style="assistant"),
        title=f"{GLYPH_WAVE} {PRODUCT_NAME}",
        title_align="left",
        box=box.SIMPLE,
        border_style=UI_ICE,
        padding=(0, 1),
        expand=True,
    )


def stdin_is_ready(ready: list[object], fd: int) -> bool:
    """``select`` returns the same objects we passed in (fds or file objects)."""
    if fd in ready:
        return True
    for item in ready:
        fileno = getattr(item, "fileno", None)
        if not callable(fileno):
            continue
        try:
            if fileno() == fd:
                return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


@contextmanager
def stdin_cbreak(fd: int) -> Iterator[object | None]:
    try:
        import termios
        import tty
    except ImportError:  # pragma: no cover - Windows
        yield None
        return
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?2004h\x1b[?1000h\x1b[?1006h")
        sys.stdout.flush()
        yield old
    finally:
        sys.stdout.write("\x1b[?2004l\x1b[?1000l\x1b[?1006l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


class OceanTui:
    def __init__(
        self,
        session: AgentSession,
        console: Console,
        settings: Settings,
        view: ChatView,
    ) -> None:
        self.session = session
        self.console = console
        self.settings = settings
        self.view = view
        self._worker: threading.Thread | None = None
        self._live: Live | None = None
        self._fd = 0
        self._term_old: object | None = None
        self._nav = NavKeys()
        self._pick = PickerKeys()

    def run(self) -> int:
        ensure_user_packs(workdir=self.settings.workdir)
        ensure_user_skills()
        if self.console.size.width < 40:
            self.console.width = 80
        if self.console.size.height < 12:
            self.console.height = 24
        editor = LineEditor()
        self.view.set_input(editor.display())
        fd = sys.stdin.fileno()
        self._fd = fd
        branch = detect_git_branch(self.settings.workdir)
        get_sidebar().set_root(self.settings.workdir)
        frame = OceanFrame(
            self.view,
            session=self.session,
            settings=self.settings,
            git_branch=branch,
            boot_started=time.monotonic(),
        )
        try:
            with Live(
                frame,
                console=self.console,
                screen=True,
                auto_refresh=True,
                refresh_per_second=16,
                transient=False,
                redirect_stdout=False,
                redirect_stderr=False,
                vertical_overflow="crop",
            ) as live:
                self._live = live
                with stdin_cbreak(fd) as saved:
                    self._term_old = saved
                    self._await_boot(fd, frame)
                    self._loop(fd, editor)
        finally:
            self._live = None
            if self.view.snapshot().busy:
                self.session.loop.state.cancel()
            if self._worker is not None:
                self._worker.join(timeout=2.0)
        self._farewell()
        return 0

    def _await_boot(self, fd: int, frame: OceanFrame) -> None:
        if frame.boot_started is None:
            return
        until = frame.boot_started + INTRO_DURATION_S
        while time.monotonic() < until:
            try:
                ready, _, _ = select.select([sys.stdin], [], [], 0.04)
            except (InterruptedError, KeyboardInterrupt):
                frame.skip_boot()
                return
            if not ready:
                continue
            try:
                data = os.read(fd, 64)
            except OSError:
                frame.skip_boot()
                return
            if data:
                frame.skip_boot()
                return

    def _loop(self, fd: int, editor: LineEditor) -> None:
        while True:
            try:
                ready, _, _ = select.select([fd], [], [], 0.08)
            except (InterruptedError, KeyboardInterrupt):
                if self._on_interrupt(editor):
                    return
                continue
            if not stdin_is_ready(ready, fd):
                continue
            try:
                data = os.read(fd, 64)
            except OSError:
                return
            if not data:
                return
            if self.view.snapshot().busy:
                if b"\x03" in data:
                    self._on_interrupt(editor)
                continue
            try:
                result = self._route_keys(data, editor)
                if result == "quit":
                    return
            except KeyboardInterrupt:
                if self._on_interrupt(editor):
                    return
            self.view.set_input(
                editor.display(active=self.view.snapshot().focus == "input")
            )

    def _route_keys(self, data: bytes, editor: LineEditor) -> str | None:
        if self.view.snapshot().picker is not None:
            return self._apply_picker(self._pick.feed(data), editor)
        focus = self.view.snapshot().focus
        if focus in {"files", "changes"}:
            return self._apply_nav(self._nav.feed(data), editor)
        if focus == "text":
            return self._apply_text(self._nav.feed(data), editor)
        return self._apply(editor.feed(data), editor)

    def _handle_global(self, action: KeyAction) -> bool:
        if action.kind == "main_tab":
            if action.text in TABS:
                get_hub().set_tab(action.text)
                self._focus_main()
            return True
        if action.kind == "cycle_tab":
            get_hub().cycle_tab()
            self._focus_main()
            return True
        if action.kind == "wheel":
            self._wheel(int(action.text or "0"))
            return True
        return False

    def _focus_main(self) -> None:
        if get_hub().tab == "text":
            self.view.set_focus("text")
        else:
            self.view.set_focus("input")

    def _wheel(self, delta: int) -> None:
        focus = self.view.snapshot().focus
        hub = get_hub()
        if focus in {"files", "changes"}:
            get_sidebar().move(delta, focus)
        elif focus == "text" or hub.tab == "text":
            hub.scroll_text(delta, 16)
        elif delta < 0:
            self.view.scroll_up(-delta)
        else:
            self.view.scroll_down(delta)

    def _apply_picker(self, actions: list[KeyAction], editor: LineEditor) -> str | None:
        for action in actions:
            if action.kind == "interrupt":
                self.view.set_picker(None)
                continue
            if action.kind == "wheel":
                self.view.move_picker(int(action.text or "0"))
                continue
            if action.kind in {"main_tab", "cycle_tab"}:
                continue
            if action.kind == "move":
                self.view.move_picker(int(action.text or "0"))
            elif action.kind == "toggle":
                self.view.toggle_picker()
            elif action.kind == "nudge":
                self.view.nudge_picker(int(action.text or "0"))
            elif action.kind == "confirm":
                self._confirm_picker()
            elif action.kind == "cancel":
                self.view.set_picker(None)
        editor.clear()
        return None

    def _open_picker(self, title: str) -> None:
        get_hub().set_tab("chat")
        self.view.set_focus("input")
        if title == "mascot":
            bank = get_bank()
            bank.set_workdir(self.settings.workdir)
            self.view.set_picker(mascot_picker(bank))
            return
        if title == "model":
            llm = getattr(getattr(self.session, "loop", None), "llm", None)
            models = discover_models(llm, current=self.settings.deepseek_model)
            self.view.set_picker(model_picker(models, current=self.settings.deepseek_model))
            return
        if title == "setting":
            self.view.set_picker(setting_picker(self.settings))
            return
        skills = get_skills()
        skills.set_workdir(self.settings.workdir)
        self.view.set_picker(skill_picker(skills))

    def _confirm_picker(self) -> None:
        picker = self.view.snapshot().picker
        if picker is None:
            return
        self.view.set_picker(None)
        if picker.kind == "mascot":
            names = picker.checked_names()
            if not names:
                return
            bank = get_bank()
            bank.set_workdir(self.settings.workdir)
            kind, body = bank.select(names[0])
            self.view.append("note" if kind != "warn" else "error", body)
            return
        if picker.kind == "model":
            names = picker.checked_names()
            if not names:
                self.view.append("error", "请输入 /model 打开勾选列表。")
                return
            kind, body = apply_model(self.session, self.settings, names[0])
            self.view.append("note" if kind != "warn" else "error", body)
            return
        if picker.kind == "setting":
            kind, body = apply_setting_items(self.session, self.settings, picker.items)
            self.view.append("note" if kind != "warn" else "error", body)
            return
        skills = get_skills()
        skills.set_workdir(self.settings.workdir)
        kind, body = skills.replace_active(list(picker.checked_names()))
        if kind == "note":
            self.session.rebuild_system()
        self.view.append("note" if kind != "warn" else "error", body)

    def _apply(self, actions: list[KeyAction], editor: LineEditor) -> str | None:
        busy = self.view.snapshot().busy
        for action in actions:
            if action.kind == "interrupt":
                if self._on_interrupt(editor):
                    return "quit"
                continue
            if self._handle_global(action):
                continue
            if busy:
                continue
            if action.kind == "eof":
                if not editor.buffer:
                    return "quit"
                continue
            if action.kind == "page_up":
                self.view.scroll_up()
            elif action.kind == "page_down":
                self.view.scroll_down()
            elif action.kind == "scroll_bottom":
                self.view.scroll_bottom()
            elif action.kind == "cycle_focus":
                self.view.set_focus("files")
            elif action.kind == "submit":
                if self._submit(action.text):
                    return "quit"
        return None

    def _apply_nav(self, actions: list[KeyAction], editor: LineEditor) -> str | None:
        for action in actions:
            if action.kind == "interrupt":
                if self._on_interrupt(editor):
                    return "quit"
                continue
            if self._handle_global(action):
                continue
            if action.kind == "cycle_focus":
                focus = self.view.snapshot().focus
                if focus == "files":
                    self.view.set_focus("changes")
                else:
                    self._focus_main()
            elif action.kind == "focus_input":
                self._focus_main()
            elif action.kind == "eof":
                return "quit"
            elif action.kind == "move":
                pane = self.view.snapshot().focus
                if pane in {"files", "changes"}:
                    get_sidebar().move(int(action.text or "0"), pane)
            elif action.kind == "jump_changes":
                self.view.set_focus("changes")
                get_sidebar().jump_changes()
            elif action.kind == "open":
                self._open_selected()
            elif action.kind == "diff":
                self._open_diff()
        return None

    def _apply_text(self, actions: list[KeyAction], editor: LineEditor) -> str | None:
        for action in actions:
            if action.kind == "interrupt":
                if self._on_interrupt(editor):
                    return "quit"
                continue
            if self._handle_global(action):
                continue
            if action.kind in {"cycle_focus", "focus_input"}:
                if action.kind == "cycle_focus":
                    self.view.set_focus("files")
                else:
                    get_hub().set_tab("chat")
                    self.view.set_focus("input")
            elif action.kind == "move":
                get_hub().scroll_text(int(action.text or "0"), 16)
            elif action.kind == "open":
                pass
        return None

    def _on_interrupt(self, editor: LineEditor) -> bool:
        """True when the TUI should exit."""
        if self.view.snapshot().picker is not None:
            self.view.set_picker(None)
            return False
        if self.view.snapshot().busy:
            self.session.loop.state.cancel()
            self.view.append("note", "已取消。")
            return False
        editor.clear()
        return True

    def _submit(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        if text.startswith("/"):
            return self._slash(text)
        self.view.set_busy(True)
        self.view.set_status(f"{GLYPH_WAVE} {PRODUCT_NAME} 思考中…")
        get_bank().set_pose("think")
        self._worker = threading.Thread(target=self._run_task, args=(text,), daemon=True)
        self._worker.start()
        return False

    def _run_task(self, text: str) -> None:
        try:
            self.session.ask(text)
        except Exception as exc:
            get_bank().set_pose("err")
            self.view.append("error", str(exc))
        finally:
            self.view.set_busy(False)
            self.view.set_status("")

    def _slash(self, command: str) -> bool:
        outcome = dispatch_slash(command, self.session, self.settings)
        if outcome.quit:
            return True
        if outcome.kind == "vim":
            self._open_vim(outcome.body or None)
            return False
        if outcome.kind == "pick":
            self._open_picker(outcome.title)
            return False
        if command.split()[0] == "/reset":
            self.view.clear()
            get_bank().set_pose("idle")
            get_sidebar().clear_session()
            self.view.set_focus("input")
        self._show_outcome(outcome)
        return False

    def _workspace_root(self) -> Path:
        executor = getattr(self.session.loop, "executor", None)
        if executor is not None:
            return Path(executor.workspace.root).resolve()
        return self.settings.workdir.resolve()

    def _open_selected(self) -> None:
        focus = self.view.snapshot().focus
        pane = "changes" if focus == "changes" else "files"
        item = get_sidebar().selected(pane)
        if item is None:
            self.view.append("note", "没有可打开的文件。")
            return
        if item.kind == "dir":
            get_sidebar().toggle_dir(item.rel)
            return
        if item.kind == "change":
            self._open_diff(item.rel)
            return
        self._open_text(item.rel)

    def _open_text(self, rel: str) -> None:
        err = get_hub().open_file(self._workspace_root(), rel)
        if err:
            self.view.append("note", err)
            return
        self.view.set_focus("text")

    def _open_vim(self, rel: str | None) -> None:
        root = self._workspace_root()
        path = (rel or "").strip()
        if not path:
            item = get_sidebar().selected("files")
            path = item.rel if item is not None and item.kind != "dir" else ""
        argv = file_open_argv(root, path) if path else None
        if argv is None:
            if path:
                self._open_text(path)
                return
            self.view.append("note", "请选中一个文件，或使用 /vim 路径")
            return
        self._run_outside(argv, cwd=root)

    def _open_diff(self, rel: str | None = None) -> None:
        root = self._workspace_root()
        path = (rel or "").strip()
        if not path:
            item = get_sidebar().selected(
                "changes" if self.view.snapshot().focus == "changes" else "files"
            )
            path = item.rel if item is not None else ""
        if not path:
            self.view.append("note", "没有可查看的 Changes。按 c 跳到 Changes。")
            return
        err = get_hub().open_diff(root, path)
        if err:
            self.view.append("note", err)
            return
        self.view.set_focus("text")

    def _run_outside(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdin_bytes: bytes | None = None,
        banner: bool = False,
    ) -> None:
        live = self._live
        if live is None:
            return
        live.stop()
        fd = self._fd
        old = self._term_old
        try:
            import termios
            import tty
        except ImportError:  # pragma: no cover - Windows
            termios = None  # type: ignore[assignment]
            tty = None  # type: ignore[assignment]
        try:
            if termios is not None and old is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            sys.stdout.write("\x1b[?25h")
            if banner:
                sys.stdout.write(f"\n{GLYPH_WAVE} 终端  ·  exit 返回 {PRODUCT_NAME}\n")
            sys.stdout.flush()
            if stdin_bytes is not None:
                subprocess.run(argv, cwd=cwd, input=stdin_bytes, check=False)
            else:
                subprocess.run(argv, cwd=cwd, check=False)
        except OSError as exc:
            self.view.append("error", str(exc))
        finally:
            if tty is not None:
                tty.setcbreak(fd)
                sys.stdout.write("\x1b[?2004h\x1b[?1000h\x1b[?1006h")
                sys.stdout.flush()
            live.start()
            get_sidebar().invalidate()

    def _show_outcome(self, outcome: SlashOutcome) -> None:
        if outcome.kind in ("help", "tools", "status"):
            self.view.append(outcome.kind, outcome.body, title=outcome.title)
            return
        if outcome.body:
            self.view.append("note", outcome.body)

    def _farewell(self) -> None:
        self.console.print()
        self.console.print(wave_strip(min(max(self.console.width - 2, 24), 76)))
        self.console.print(
            Text(f"  {GLYPH_WAVE} 已退出。再见，{PRODUCT_NAME}。", style=UI_CYAN)
        )
