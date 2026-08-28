"""Fullscreen alternate-screen chat UI (same idea as ``top``: occupy the tty)."""

from __future__ import annotations

import os
import select
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
from coding_agent.cli.branding import CLI_NAME, GLYPH_FLOW, GLYPH_WAVE, PRODUCT_NAME
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
from coding_agent.cli.commands import SlashOutcome, dispatch_slash
from coding_agent.cli.editor import KeyAction, LineEditor
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

PROMPT = f"{GLYPH_WAVE} {CLI_NAME} › "
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_MASCOT_WIDTH = 26
_SPLIT_MIN_WIDTH = 76
_HUD_ROWS = 5
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
            return WorkspaceChrome(
                workdir=str(cwd),
                model=self.settings.deepseek_model,
                thinking=self.settings.thinking,
                stream=self.settings.stream,
                turn=state.turn,
                max_turns=self.settings.max_turns,
                tokens=state.estimated_prompt_tokens,
                max_tokens=self.settings.max_context_tokens,
                git_branch=detect_git_branch(cwd),
                version=__version__,
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
        layout["mascot"].update(_MascotRail(chrome.workdir))
        layout["gutter"].update(_VRule())
        main = layout["main"]
    else:
        main = layout["body"]
    main.split_column(
        Layout(name="hud", size=_HUD_ROWS),
        Layout(name="gap_hud", size=1),
        Layout(name="chat", ratio=1),
        Layout(name="status", size=1),
        Layout(name="input", size=2 + max(1, len(lines))),
    )
    main["hud"].update(_Hud(chrome, snap))
    main["gap_hud"].update(_HRule())
    main["chat"].update(_ChatPane(view))
    main["status"].update(_StatusBar(view))
    main["input"].update(_InputBar(lines, hint))
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
            Align.center(mascot_placeholder(workdir=self.workdir), vertical="middle"),
            box=box.ROUNDED,
            border_style=UI_ICE,
            padding=(0, 0),
            expand=True,
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
                width=options.max_width,
            ),
            title=cute_title(f"工作区  ·  v{ver}"),
            title_align="left",
            box=box.SQUARE,
            border_style=UI_CYAN,
            padding=(0, 1),
            expand=True,
        )


class _ChatPane:
    def __init__(self, view: ChatView) -> None:
        self.view = view

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        snap = self.view.snapshot()
        width = options.max_width
        height = options.height or 8
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
        right = Text(
            "Enter 发送  ·  Ctrl+C 离开  ·  /help  ·  PgUp 对话  ·  ← → 输入",
            style="muted",
        )
        row.add_row(left, right)
        return row


class _InputBar:
    def __init__(self, lines: tuple[str, ...], hint: str) -> None:
        self.lines = lines
        self.hint = hint

    def __rich_console__(self, console: Console, options) -> Iterator[RenderableType]:
        body = Text(style="prompt", no_wrap=True, overflow="crop")
        for i, line in enumerate(self.lines):
            if i:
                body.append("\n")
            body.append(line)
        yield Panel(
            body,
            box=box.DOUBLE,
            border_style=UI_FOAM,
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
    if snap.busy:
        return (f"{GLYPH_WAVE} 思考中，Ctrl+C 取消",), ""
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
        welcome.append("在下方输入任务。\n", style=UI_ICE)
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


@contextmanager
def stdin_cbreak(fd: int) -> Iterator[None]:
    try:
        import termios
        import tty
    except ImportError:  # pragma: no cover - Windows
        yield
        return
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()
        yield
    finally:
        sys.stdout.write("\x1b[?2004l")
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

    def run(self) -> int:
        if self.console.size.width < 40:
            self.console.width = 80
        if self.console.size.height < 12:
            self.console.height = 24
        editor = LineEditor()
        self.view.set_input(editor.display())
        fd = sys.stdin.fileno()
        branch = detect_git_branch(self.settings.workdir)
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
            ):
                with stdin_cbreak(fd):
                    self._await_boot(fd, frame)
                    self._loop(fd, editor)
        finally:
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
                ready, _, _ = select.select([sys.stdin], [], [], 0.08)
            except (InterruptedError, KeyboardInterrupt):
                if self._on_interrupt(editor):
                    return
                continue
            if not ready:
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
                if self._apply(editor.feed(data), editor) == "quit":
                    return
            except KeyboardInterrupt:
                if self._on_interrupt(editor):
                    return
            self.view.set_input(editor.display())

    def _apply(self, actions: list[KeyAction], editor: LineEditor) -> str | None:
        busy = self.view.snapshot().busy
        for action in actions:
            if action.kind == "interrupt":
                if self._on_interrupt(editor):
                    return "quit"
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
            elif action.kind == "submit":
                if self._submit(action.text):
                    return "quit"
        return None

    def _on_interrupt(self, editor: LineEditor) -> bool:
        """True when the TUI should exit."""
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
        self._worker = threading.Thread(target=self._run_task, args=(text,), daemon=True)
        self._worker.start()
        return False

    def _run_task(self, text: str) -> None:
        try:
            self.session.ask(text)
        except Exception as exc:
            self.view.append("error", str(exc))
        finally:
            self.view.set_busy(False)
            self.view.set_status("")

    def _slash(self, command: str) -> bool:
        outcome = dispatch_slash(command, self.session, self.settings)
        if outcome.quit:
            return True
        if command.split()[0] == "/reset":
            self.view.clear()
        self._show_outcome(outcome)
        return False

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
