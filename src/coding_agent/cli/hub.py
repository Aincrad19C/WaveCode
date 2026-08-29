"""Main-area tabs: chat / text (Cursor-like)."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text

from coding_agent.cli.handoff import read_diff, resolve_under_root
from coding_agent.cli.prettydiff import visual_diff_lines
from coding_agent.cli.syntax import style_source

TABS = ("chat", "text")
TAB_LABELS = {"chat": "对话", "text": "文本"}
_MAX_BYTES = 256 * 1024


class WorkspaceHub:
    def __init__(self) -> None:
        self.tab = "chat"
        self.file_rel = ""
        self.file_title = ""
        self.file_mode = "code"  # code | diff
        self.file_lines: tuple[str, ...] = ()
        self.file_styled: tuple[Text, ...] = ()
        self.file_scroll = 0

    def set_tab(self, name: str) -> None:
        if name in TABS:
            self.tab = name

    def cycle_tab(self) -> str:
        i = TABS.index(self.tab) if self.tab in TABS else 0
        self.tab = TABS[(i + 1) % len(TABS)]
        return self.tab

    def open_file(self, root: Path | str, rel: str) -> str:
        path = resolve_under_root(root, rel)
        if path is None:
            return "路径超出工作区。"
        if path.is_dir():
            return ""
        if not path.is_file():
            return f"找不到 {rel}"
        try:
            size = path.stat().st_size
        except OSError as exc:
            return str(exc)
        if size > _MAX_BYTES:
            return f"{rel} 过大（>{_MAX_BYTES} 字节），请用 /vim 外部打开。"
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"{rel} 不是 UTF-8 文本。"
        except OSError as exc:
            return str(exc)
        self.file_rel = rel
        self.file_title = rel
        self.file_mode = "code"
        self.file_lines = tuple(text.splitlines() or [""])
        self.file_styled = style_source(rel, text)
        self.file_scroll = 0
        self.tab = "text"
        return ""

    def open_diff(self, root: Path | str, rel: str) -> str:
        diff = read_diff(root, rel)
        if not diff.strip():
            return self.open_file(root, rel)
        rows = visual_diff_lines(diff)
        self.file_rel = rel
        self.file_title = rel
        self.file_mode = "diff"
        self.file_styled = rows
        self.file_lines = tuple(row.plain for row in rows)
        self.file_scroll = 0
        self.tab = "text"
        return ""

    def scroll_text(self, delta: int, height: int) -> None:
        total = len(self.file_styled) or len(self.file_lines)
        if not total:
            return
        max_off = max(0, total - max(1, height))
        self.file_scroll = max(0, min(max_off, self.file_scroll + delta))

    def visible_text(self, height: int) -> tuple[str, ...]:
        rows = self.visible_styled(height)
        return tuple(row.plain for row in rows)

    def visible_styled(self, height: int) -> tuple[Text, ...]:
        height = max(1, height)
        rows = self.file_styled
        if not rows:
            return (Text("（未打开文件。在左轨选中后 Enter。）", style="muted"),)
        start = min(self.file_scroll, max(0, len(rows) - 1))
        return rows[start : start + height]


_hub: WorkspaceHub | None = None


def get_hub() -> WorkspaceHub:
    global _hub
    if _hub is None:
        _hub = WorkspaceHub()
    return _hub


def reset_hub() -> WorkspaceHub:
    global _hub
    _hub = WorkspaceHub()
    return _hub
