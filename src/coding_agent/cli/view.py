"""Thread-safe chat view-model for the fullscreen TUI."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from coding_agent.cli.picker import PickState


@dataclass(frozen=True, slots=True)
class ChatItem:
    kind: str
    text: str
    ok: bool = True
    title: str = ""


@dataclass(frozen=True, slots=True)
class ViewSnapshot:
    items: tuple[ChatItem, ...]
    status: str
    busy: bool
    input_buffer: str
    scroll: int
    placeholder: str
    focus: str
    picker: PickState | None
    complete_index: int


class ChatView:
    """Mutable UI state. The Live refresh thread only ever reads snapshots."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[ChatItem] = []
        self._status = ""
        self._busy = False
        self._input = ""
        self._scroll = 0
        self._placeholder = "在下方输入任务。Enter 发送，Ctrl+C 离开，/help 查看命令。"
        self._focus = "input"
        self._picker: PickState | None = None
        self._complete_index = 0
        self._complete_prefix = ""

    def append(self, kind: str, text: str, *, ok: bool = True, title: str = "") -> None:
        with self._lock:
            self._items.append(ChatItem(kind=kind, text=text, ok=ok, title=title))
            self._scroll = 0

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._scroll = 0

    def set_status(self, text: str) -> None:
        with self._lock:
            self._status = text

    def set_busy(self, busy: bool) -> None:
        with self._lock:
            self._busy = busy

    def set_input(self, text: str) -> None:
        raw = (text or "").replace("█", "")
        prefix = raw if raw.startswith("/") and not any(ch.isspace() for ch in raw) else ""
        with self._lock:
            self._input = text
            if prefix != self._complete_prefix:
                self._complete_index = 0
                self._complete_prefix = prefix

    def set_placeholder(self, text: str) -> None:
        with self._lock:
            self._placeholder = text

    def scroll_up(self, steps: int = 3) -> None:
        with self._lock:
            cap = max(0, len(self._items) - 1)
            self._scroll = min(self._scroll + steps, cap)

    def scroll_down(self, steps: int = 3) -> None:
        with self._lock:
            self._scroll = max(0, self._scroll - steps)

    def scroll_bottom(self) -> None:
        with self._lock:
            self._scroll = 0

    def set_picker(self, picker: PickState | None) -> None:
        with self._lock:
            self._picker = picker

    def move_picker(self, delta: int) -> None:
        with self._lock:
            if self._picker is not None:
                self._picker = self._picker.moved(delta)

    def toggle_picker(self) -> None:
        with self._lock:
            if self._picker is not None:
                self._picker = self._picker.toggled()

    def nudge_picker(self, delta: int) -> None:
        with self._lock:
            if self._picker is not None:
                self._picker = self._picker.nudged(delta)

    def move_complete(self, delta: int, count: int) -> None:
        if count <= 0:
            return
        with self._lock:
            self._complete_index = (self._complete_index + delta) % count

    def set_focus(self, name: str) -> None:
        with self._lock:
            self._focus = name if name in {"input", "files", "changes", "text"} else "input"

    def snapshot(self) -> ViewSnapshot:
        with self._lock:
            return ViewSnapshot(
                items=tuple(self._items),
                status=self._status,
                busy=self._busy,
                input_buffer=self._input,
                scroll=self._scroll,
                placeholder=self._placeholder,
                focus=self._focus,
                picker=self._picker,
                complete_index=self._complete_index,
            )
