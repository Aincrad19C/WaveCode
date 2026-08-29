"""Left-rail workspace file tree and per-turn Changes."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from rich.cells import cell_len
from rich.text import Text

from coding_agent.cli.theme import UI_CYAN, UI_ERR, UI_FOAM, UI_ICE, UI_OK, UI_WARN
from coding_agent.tools.builtin import IGNORED_DIRS

_SKIP_DIRS = IGNORED_DIRS | {
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".tox",
    ".eggs",
}
_MAX_DEPTH = 3
_MAX_NODES = 96
_MAX_CHILDREN = 12
_CACHE_S = 0.45
_GIT_TIMEOUT_S = 0.35
_CODE_STYLE = {"A": UI_OK, "M": UI_WARN, "D": UI_ERR, "?": UI_OK}
_CHANGE_MARK = {"A": "+", "M": "~", "D": "−", "?": "+"}
_CODE_RANK = {"D": 3, "M": 2, "A": 1, "?": 0}


@dataclass(frozen=True, slots=True)
class TreeLine:
    depth: int
    name: str
    is_dir: bool
    rel: str


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    code: str  # A / M / D / ?


@dataclass(frozen=True, slots=True)
class NavItem:
    kind: str  # file | dir | change
    rel: str
    code: str = ""


def skip_name(name: str, is_dir: bool) -> bool:
    if name.startswith("."):
        return True
    if is_dir and (name in _SKIP_DIRS or name.endswith(".egg-info")):
        return True
    return False


def collect_tree(
    root: Path | str,
    *,
    max_depth: int = _MAX_DEPTH,
    max_nodes: int = _MAX_NODES,
    max_children: int = _MAX_CHILDREN,
) -> tuple[TreeLine, ...]:
    base = Path(root)
    if not base.is_dir():
        return ()
    lines: list[TreeLine] = []

    def walk(current: Path, depth: int, rel: str) -> None:
        if len(lines) >= max_nodes or depth > max_depth:
            return
        try:
            entries = list(current.iterdir())
        except OSError:
            return
        entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
        visible = [p for p in entries if not skip_name(p.name, p.is_dir())]
        extra = 0
        if len(visible) > max_children:
            extra = len(visible) - max_children
            visible = visible[:max_children]
        for path in visible:
            if len(lines) >= max_nodes:
                return
            child_rel = path.name if not rel else f"{rel}/{path.name}"
            is_dir = path.is_dir()
            lines.append(TreeLine(depth=depth, name=path.name, is_dir=is_dir, rel=child_rel))
            if is_dir and depth < max_depth:
                walk(path, depth + 1, child_rel)
        if extra and len(lines) < max_nodes:
            lines.append(TreeLine(depth=depth, name=f"… +{extra}", is_dir=False, rel=""))

    walk(base, 0, "")
    return tuple(lines)


def parse_porcelain(text: str) -> tuple[FileChange, ...]:
    found: list[FileChange] = []
    for raw in text.splitlines():
        if len(raw) < 4:
            continue
        xy, rest = raw[:2], raw[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        path = rest.strip().strip('"')
        if not path:
            continue
        found.append(FileChange(path=path, code=_xy_code(xy)))
    return tuple(found)


def read_git_status(root: Path | str) -> tuple[FileChange, ...]:
    base = Path(root)
    git = base / ".git"
    if not git.exists():
        return ()
    try:
        proc = subprocess.run(
            [
                "git",
                "-c",
                "color.status=false",
                "status",
                "--porcelain",
                "--untracked-files=normal",
            ],
            cwd=base,
            check=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if proc.returncode != 0:
        return ()
    return parse_porcelain(proc.stdout)


def merge_changes(*groups: tuple[FileChange, ...] | list[FileChange]) -> tuple[FileChange, ...]:
    best: dict[str, str] = {}
    order: list[str] = []
    for group in groups:
        for item in group:
            if not item.path:
                continue
            prev = best.get(item.path)
            if prev is None:
                order.append(item.path)
                best[item.path] = item.code
            elif _CODE_RANK.get(item.code, 0) >= _CODE_RANK.get(prev, 0):
                best[item.path] = item.code
    return tuple(FileChange(path=path, code=best[path]) for path in order)


def ellipsize_right(text: str, width: int) -> str:
    width = max(1, width)
    if cell_len(text) <= width:
        return text
    if width == 1:
        return "…"
    out = text
    while out and cell_len(out + "…") > width:
        out = out[:-1]
    return out + "…"


def visible_tree(
    tree: tuple[TreeLine, ...], expanded: set[str] | frozenset[str]
) -> tuple[TreeLine, ...]:
    """Keep children of a directory only when that directory is expanded."""
    out: list[TreeLine] = []
    skip_deeper_than: int | None = None
    for node in tree:
        if skip_deeper_than is not None:
            if node.depth > skip_deeper_than:
                continue
            skip_deeper_than = None
        out.append(node)
        if node.is_dir and node.rel and node.rel not in expanded:
            skip_deeper_than = node.depth
    return tuple(out)


def render_tree(
    tree: tuple[TreeLine, ...],
    *,
    dirty: set[str],
    width: int,
    height: int,
    selected: NavItem | None = None,
    focused: bool = False,
    offset: int = 0,
    expanded: set[str] | frozenset[str] | None = None,
) -> tuple[Text, int, str]:
    """Scrollable file tree. Cursor stays inside the window."""
    width = max(4, width)
    height = max(1, height)
    shown = visible_tree(tree, expanded or set())
    rows = _format_tree(
        shown, dirty, width, selected=selected, focused=focused, expanded=expanded or set()
    )
    if not rows:
        rows = [Text("（空）", style="muted")]
    cursor = 0
    if selected is not None:
        for i, node in enumerate(shown):
            if node.rel == selected.rel:
                cursor = i
                break
    offset = _follow_cursor(len(rows), height, cursor, offset)
    return _window(rows, offset, height)


def render_changes(
    changes: tuple[FileChange, ...],
    *,
    width: int,
    height: int,
    selected: NavItem | None = None,
    focused: bool = False,
    offset: int = 0,
) -> tuple[Text, int, str]:
    """Scrollable Changes list in its own pane."""
    width = max(4, width)
    height = max(1, height)
    rows = _format_changes(changes, width, selected=selected, focused=focused)
    cursor = 0
    if selected is not None and selected.kind == "change":
        for i, item in enumerate(changes):
            if item.path == selected.rel:
                cursor = i
                break
    offset = _follow_cursor(len(rows), height, cursor, offset)
    return _window(rows, offset, height)


def _window(rows: list[Text], offset: int, height: int) -> tuple[Text, int, str]:
    window = rows[offset : offset + height]
    body = Text()
    for i, row in enumerate(window):
        if i:
            body.append("\n")
        body.append_text(row)
    if not window:
        body.append("（空）", style="muted")
    hint = _scroll_hint(offset, height, len(rows))
    return body, offset, hint


def _follow_cursor(total: int, height: int, cursor: int, offset: int) -> int:
    height = max(1, height)
    if total <= height:
        return 0
    if cursor < offset:
        offset = cursor
    elif cursor >= offset + height:
        offset = cursor - height + 1
    return max(0, min(offset, total - height))


def _scroll_hint(offset: int, visible: int, total: int) -> str:
    if total <= visible or visible <= 0:
        return ""
    start = offset + 1
    end = min(total, offset + visible)
    parts: list[str] = []
    if offset:
        parts.append("↑")
    filled = max(1, round(8 * visible / total)) if total else 8
    pos = round(offset / (total - visible) * (8 - filled)) if total > visible else 0
    pos = max(0, min(8 - filled, pos))
    bar = "░" * pos + "█" * filled + "░" * (8 - pos - filled)
    parts.append(bar[:8] if len(bar) >= 8 else bar)
    if end < total:
        parts.append("↓")
    parts.append(f"{start}-{end}/{total}")
    return "  ".join(parts)


def _format_changes(
    changes: tuple[FileChange, ...],
    width: int,
    *,
    selected: NavItem | None,
    focused: bool,
) -> list[Text]:
    if not changes:
        return [Text("（无）", style="muted")]
    rows: list[Text] = []
    for item in changes:
        mark = _CHANGE_MARK.get(item.code, item.code)
        color = _CODE_STYLE.get(item.code, UI_ICE)
        label = ellipsize_right(item.path, width - 2)
        active = (
            focused
            and selected is not None
            and selected.kind == "change"
            and selected.rel == item.path
        )
        row = Text()
        if active:
            row.append(f"> {mark} {label}", style=f"reverse {color}")
        else:
            row.append(f"{mark} ", style=f"bold {color}")
            row.append(label, style=color)
        rows.append(row)
    return rows


def _format_tree(
    tree: tuple[TreeLine, ...],
    dirty: set[str],
    width: int,
    *,
    selected: NavItem | None = None,
    focused: bool = False,
    expanded: set[str] | frozenset[str] | None = None,
) -> list[Text]:
    open_dirs = expanded or set()
    rows: list[Text] = []
    for node in tree:
        indent = "  " * node.depth
        if node.is_dir:
            mark = "▾ " if node.rel in open_dirs else "▸ "
            label = f"{mark}{node.name}/"
        elif node.name.startswith("…"):
            label = node.name
        else:
            label = f"  {node.name}"
        active = (
            focused
            and selected is not None
            and selected.kind != "change"
            and selected.rel == node.rel
            and node.rel != ""
        )
        text = Text()
        shown = ellipsize_right(("> " if active else "") + indent + label, width)
        if active:
            text.append(shown, style=f"reverse {UI_FOAM}")
        else:
            text.append(shown, style=_tree_style(node, dirty))
        rows.append(text)
    return rows


def _tree_style(node: TreeLine, dirty: set[str]) -> str:
    if node.rel in dirty:
        return f"bold {UI_WARN}"
    if node.name.startswith("…"):
        return "muted"
    if node.is_dir:
        return UI_CYAN
    return UI_FOAM


def _xy_code(xy: str) -> str:
    if xy == "??":
        return "A"
    if "D" in xy:
        return "D"
    if "A" in xy:
        return "A"
    return "M"


class WorkspaceSidebar:
    """Cached tree + git status, plus this-turn tool writes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._root: Path | None = None
        self._session: dict[str, str] = {}
        self._baseline: tuple[FileChange, ...] = ()
        self._tree: tuple[TreeLine, ...] = ()
        self._git: tuple[FileChange, ...] = ()
        self._scanned_at = 0.0
        self._scan_key = ""
        self.file_cursor = 0
        self.file_offset = 0
        self.file_hint = ""
        self.change_cursor = 0
        self.change_offset = 0
        self.change_hint = ""
        self.expanded: set[str] = set()

    def set_root(self, path: Path | str | None) -> None:
        root = None if path is None else Path(path)
        with self._lock:
            if root != self._root:
                self._root = root
                self._scanned_at = 0.0
                self._scan_key = ""
                self.expanded.clear()
                self.file_cursor = 0
                self.file_offset = 0
                self.change_cursor = 0
                self.change_offset = 0

    def begin_turn(self) -> None:
        with self._lock:
            self._session.clear()
            root = self._root
        git = read_git_status(root) if root is not None else ()
        with self._lock:
            self._baseline = git
            self._git = git
            self._scanned_at = 0.0

    def clear_session(self) -> None:
        with self._lock:
            self._session.clear()
            self._baseline = ()
            self._scanned_at = 0.0

    def note(self, path: str, code: str) -> None:
        rel = path.replace("\\", "/").lstrip("./")
        if not rel:
            return
        with self._lock:
            prev = self._session.get(rel)
            if prev is None or _CODE_RANK.get(code, 0) >= _CODE_RANK.get(prev, 0):
                self._session[rel] = code
            self._scanned_at = 0.0

    def invalidate(self) -> None:
        with self._lock:
            self._scanned_at = 0.0

    def changes(self) -> tuple[FileChange, ...]:
        self._refresh()
        with self._lock:
            session = tuple(FileChange(path=p, code=c) for p, c in self._session.items())
            git = self._git
            baseline = {item.path: item.code for item in self._baseline}
        delta = tuple(
            item for item in git if baseline.get(item.path) != item.code
        )
        return merge_changes(delta, session)

    def tree(self) -> tuple[TreeLine, ...]:
        self._refresh()
        with self._lock:
            return self._tree

    def visible(self) -> tuple[TreeLine, ...]:
        return visible_tree(self.tree(), self.expanded)

    def file_items(self) -> tuple[NavItem, ...]:
        items: list[NavItem] = []
        for node in self.visible():
            if not node.rel:
                continue
            items.append(NavItem("dir" if node.is_dir else "file", node.rel))
        return tuple(items)

    def change_items(self) -> tuple[NavItem, ...]:
        return tuple(NavItem("change", item.path, item.code) for item in self.changes())

    def nav_items(self, pane: str = "files") -> tuple[NavItem, ...]:
        return self.change_items() if pane == "changes" else self.file_items()

    def selected(self, pane: str = "files") -> NavItem | None:
        items = self.nav_items(pane)
        if pane == "changes":
            if not items:
                self.change_cursor = 0
                return None
            self.change_cursor = max(0, min(self.change_cursor, len(items) - 1))
            return items[self.change_cursor]
        if not items:
            self.file_cursor = 0
            return None
        self.file_cursor = max(0, min(self.file_cursor, len(items) - 1))
        return items[self.file_cursor]

    def move(self, delta: int, pane: str = "files") -> NavItem | None:
        items = self.nav_items(pane)
        if not items:
            if pane == "changes":
                self.change_cursor = 0
            else:
                self.file_cursor = 0
            return None
        if pane == "changes":
            self.change_cursor = max(0, min(len(items) - 1, self.change_cursor + delta))
            return items[self.change_cursor]
        self.file_cursor = max(0, min(len(items) - 1, self.file_cursor + delta))
        return items[self.file_cursor]

    def toggle_dir(self, rel: str | None = None) -> NavItem | None:
        item = self.selected("files") if rel is None else NavItem("dir", rel)
        if item is None or item.kind != "dir" or not item.rel:
            return item
        if item.rel in self.expanded:
            self.expanded.discard(item.rel)
        else:
            self.expanded.add(item.rel)
        return self.selected("files")

    def jump_changes(self) -> NavItem | None:
        items = self.change_items()
        if not items:
            self.change_cursor = 0
            return None
        self.change_cursor = 0
        return items[0]

    def render_files(self, *, width: int, height: int, focused: bool = False) -> Text:
        dirty = {item.path for item in self.changes()}
        body, offset, hint = render_tree(
            self.tree(),
            dirty=dirty,
            width=width,
            height=height,
            selected=self.selected("files"),
            focused=focused,
            offset=self.file_offset,
            expanded=self.expanded,
        )
        self.file_offset = offset
        self.file_hint = hint
        return body

    def render_changes(self, *, width: int, height: int, focused: bool = False) -> Text:
        body, offset, hint = render_changes(
            self.changes(),
            width=width,
            height=height,
            selected=self.selected("changes"),
            focused=focused,
            offset=self.change_offset,
        )
        self.change_offset = offset
        self.change_hint = hint
        return body

    def render(self, *, width: int, height: int, focused: bool = False) -> Text:
        return self.render_files(width=width, height=height, focused=focused)

    def _refresh(self) -> None:
        with self._lock:
            root = self._root
            key = str(root or "")
            age = time.monotonic() - self._scanned_at
            if self._scan_key == key and age < _CACHE_S:
                return
        tree = collect_tree(root) if root is not None else ()
        git = read_git_status(root) if root is not None else ()
        with self._lock:
            self._tree = tree
            self._git = git
            self._scan_key = key
            self._scanned_at = time.monotonic()


_sidebar: WorkspaceSidebar | None = None


def get_sidebar() -> WorkspaceSidebar:
    global _sidebar
    if _sidebar is None:
        _sidebar = WorkspaceSidebar()
    return _sidebar


def reset_sidebar() -> WorkspaceSidebar:
    global _sidebar
    _sidebar = WorkspaceSidebar()
    return _sidebar
