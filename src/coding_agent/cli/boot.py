"""Boot splash: a large ASCII boat cuts a channel that reveals a block wordmark.

Character-as-medium, same idea as the Copilot CLI banner: the logo is the art,
not a tiny label sitting on a texture.
"""

from __future__ import annotations

import math

from rich import box
from rich.cells import cell_len
from rich.console import RenderableType
from rich.panel import Panel
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

from coding_agent.cli.branding import PRODUCT_NAME, TAGLINE
from coding_agent.cli.theme import (
    UI_CYAN,
    UI_DEEP,
    UI_FOAM,
    UI_ICE,
    UI_PRIMARY,
    UI_WHITE,
    UI_WOOD,
    UI_WOOD_DEEP,
)

BOOT_DURATION_S = 2.6
REVEAL_DURATION_S = 1.5
INTRO_DURATION_S = BOOT_DURATION_S + REVEAL_DURATION_S
_SHORE = "▓▒░"
_INK = f"bold {UI_WHITE} on #000000"
_PLATE = "on #000000"
_UNITS = "▁▂▃▄▅▆▇▆▅▄▃▂"
_CROSS = 0.8
_HULL_ROW = 8

# Side-view cutter, bow on the right. Spaces are transparent.
_BOAT = (
    "                 /\\      ",
    "                /██\\     ",
    "               /████\\    ",
    "              /██████\\   ",
    "             /████████\\  ",
    "            /    ██    \\ ",
    "           /     ██     \\",
    "          /      ██      \\",
    "▄▄████████████████████████▄",
    "▀▀███████████████████████▀ ",
    "   ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀    ",
)

# 6x7 block glyphs. Built so WAVEMIO reads at banner scale, not one cell.
_GLYPHS: dict[str, tuple[str, ...]] = {
    "W": (
        "██    ██",
        "██    ██",
        "██ ██ ██",
        "████████",
        "██    ██",
        "██    ██",
    ),
    "A": (
        "  ████  ",
        " ██  ██ ",
        "████████",
        "██    ██",
        "██    ██",
        "██    ██",
    ),
    "V": (
        "██    ██",
        "██    ██",
        "██    ██",
        " ██  ██ ",
        "  ████  ",
        "   ██   ",
    ),
    "E": (
        "████████",
        "██      ",
        "██████  ",
        "██      ",
        "██      ",
        "████████",
    ),
    "M": (
        "██    ██",
        "███  ███",
        "████████",
        "██ ██ ██",
        "██    ██",
        "██    ██",
    ),
    "I": (
        "  ████  ",
        "   ██   ",
        "   ██   ",
        "   ██   ",
        "   ██   ",
        "  ████  ",
    ),
    "O": (
        "  ████  ",
        " ██  ██ ",
        "██    ██",
        "██    ██",
        " ██  ██ ",
        "  ████  ",
    ),
}


def boot_panel(width: int, height: int, t: float, *, tide: float = 0.0) -> Panel:
    """Boat draws a waterway; a block wordmark is written in the wake."""
    t = max(0.0, min(1.0, t))
    inner_w = max(12, width - 2)
    inner_h = max(6, height - 2)
    grid = _sea(inner_w, inner_h, t + tide)
    mid = inner_h // 2
    amp = 1 if inner_h < 12 else min(2, inner_h // 8)
    boat_w = max(len(row) for row in _BOAT)
    head_x = _head_x(t, inner_w, boat_w)
    cut = min(inner_w, max(0, head_x))
    band = range(-3, 4) if inner_h >= 12 else range(-1, 2)
    for x in range(cut):
        y0 = _channel_y(x, inner_w, mid, amp)
        for dy in band:
            y = y0 + dy
            if not (0 <= y < inner_h):
                continue
            if dy == 0:
                grid[y][x] = (" ", _PLATE)
                continue
            ch = _UNITS[(x + int(t * 16)) % len(_UNITS)]
            style = UI_CYAN if abs(dy) == 1 else UI_PRIMARY
            grid[y][x] = (ch, style)
    _write_wordmark(grid, inner_w, inner_h, mid, cut, t)
    _blit_boat(grid, inner_w, inner_h, mid, amp, head_x)
    return Panel(
        _to_text(grid),
        box=box.HEAVY,
        border_style=UI_PRIMARY,
        padding=(0, 0),
        expand=True,
    )


def _head_x(t: float, width: int, boat_w: int) -> int:
    progress = min(1.0, t / _CROSS)
    return int(progress * (width + boat_w + 6)) - boat_w


def _channel_y(x: int, width: int, mid: int, amp: int) -> int:
    frac = x / max(1, width - 1)
    if 0.18 < frac < 0.82:
        return mid
    return mid + int(round(math.sin(frac * math.pi * 2.0) * amp))


def _sea(width: int, height: int, t: float) -> list[list[tuple[str, str]]]:
    phase = int(t * 18)
    rows: list[list[tuple[str, str]]] = []
    for y in range(height):
        row: list[tuple[str, str]] = []
        for x in range(width):
            ch = _UNITS[(x + y + phase) % len(_UNITS)]
            row.append((ch, f"dim {UI_DEEP}"))
        rows.append(row)
    return rows


def _wordmark() -> tuple[str, ...]:
    glyphs = [_GLYPHS[ch] for ch in PRODUCT_NAME.upper() if ch in _GLYPHS]
    if not glyphs:
        return ()
    rows = len(glyphs[0])
    out: list[str] = []
    for r in range(rows):
        out.append("  ".join(g[r] for g in glyphs))
    return tuple(out)


def _write_wordmark(
    grid: list[list[tuple[str, str]]],
    width: int,
    height: int,
    mid: int,
    cut: int,
    t: float,
) -> None:
    mark = _wordmark()
    if not mark:
        return
    bw = len(mark[0])
    bh = len(mark)
    bx = max(0, (width - bw) // 2)
    by = max(1, mid - bh // 2)
    plate = min(bw, max(0, cut - bx))
    pad = 1
    for r in range(-pad, bh + pad):
        y = by + r
        if not (0 <= y < height):
            continue
        for c in range(-pad, plate + pad):
            x = bx + c
            if 0 <= x < width and x < cut:
                grid[y][x] = (" ", _PLATE)
    visible = 0
    for r, line in enumerate(mark):
        y = by + r
        if not (0 <= y < height):
            continue
        for c, ch in enumerate(line):
            x = bx + c
            if ch == " " or not (0 <= x < width) or x >= cut:
                continue
            grid[y][x] = (ch, _INK)
            visible += 1
    if visible == 0:
        return
    cap_y = min(height - 1, by + bh + 1)
    cap_x = max(0, (width - cell_len(PRODUCT_NAME)) // 2)
    if cut > cap_x + 2:
        for x in range(max(0, cap_x - 1), min(width, cap_x + cell_len(PRODUCT_NAME) + 1)):
            if x < cut:
                grid[cap_y][x] = (" ", _PLATE)
        for i, ch in enumerate(PRODUCT_NAME):
            x = cap_x + i
            if 0 <= x < width and x < cut:
                grid[cap_y][x] = (ch, _INK)
    if t < 0.5:
        return
    tag = TAGLINE
    tag_y = min(height - 1, cap_y + 1)
    tag_x = max(0, (width - cell_len(tag)) // 2)
    if cut <= tag_x:
        return
    for x in range(max(0, tag_x - 1), min(width, tag_x + cell_len(tag) + 1)):
        if x < cut:
            grid[tag_y][x] = (" ", "")
    for i, ch in enumerate(tag):
        x = tag_x + i
        if 0 <= x < width and x < cut:
            grid[tag_y][x] = (ch, UI_ICE)


def _blit_boat(
    grid: list[list[tuple[str, str]]],
    width: int,
    height: int,
    mid: int,
    amp: int,
    head_x: int,
) -> None:
    boat_w = max(len(row) for row in _BOAT)
    if head_x >= width or head_x + boat_w <= 0:
        return
    sample_x = min(width - 1, max(0, head_x + boat_w // 2))
    origin_y = _channel_y(sample_x, width, mid, amp) - _HULL_ROW
    for dy, art in enumerate(_BOAT):
        y = origin_y + dy
        if not (0 <= y < height):
            continue
        for i, ch in enumerate(art):
            x = head_x + i
            if 0 <= x < width and ch != " ":
                grid[y][x] = (ch, _boat_style(dy, ch))


def _boat_style(dy: int, ch: str) -> str:
    if dy >= _HULL_ROW:
        return f"bold {UI_WOOD_DEEP}"
    if ch == "█" and dy >= 5:
        return f"bold {UI_WOOD}"
    return f"bold {UI_WHITE}"


def _to_text(grid: list[list[tuple[str, str]]]) -> Text:
    body = Text()
    for y, row in enumerate(grid):
        if y:
            body.append("\n")
        pending: list[str] = []
        style = ""
        for ch, st in row:
            if pending and st != style:
                body.append("".join(pending), style=style or None)
                pending = []
            pending.append(ch)
            style = st
        if pending:
            body.append("".join(pending), style=style or None)
    return body


def reveal_from_left(under: RenderableType, cover: RenderableType, t: float) -> RenderableType:
    """Wipe the splash to the right so the main frame emerges from the left."""
    return _Reveal(under, cover, max(0.0, min(1.0, t)))


class _Reveal:
    def __init__(self, under: RenderableType, cover: RenderableType, t: float) -> None:
        self.under = under
        self.cover = cover
        self.t = t

    def __rich_console__(self, console, options):
        width = max(1, options.max_width)
        height = max(1, options.height or console.size.height)
        opts = options.update_dimensions(width, height)
        under_lines = list(console.render_lines(self.under, opts, pad=True))
        cover_lines = list(console.render_lines(self.cover, opts, pad=True))
        while len(under_lines) < height:
            under_lines.append([Segment(" " * width)])
        while len(cover_lines) < height:
            cover_lines.append([Segment(" " * width)])
        shore = Style.parse(f"bold {UI_FOAM}")
        foam = Style.parse(f"bold {UI_CYAN}")
        for y in range(height):
            cut = _waterline(self.t, width, y)
            left = _slice_cells(under_lines[y], 0, cut)
            right_from = cut
            edge: list[Segment] = []
            if 0 < cut < width:
                n = min(3, width - cut)
                glyphs = _SHORE[:n]
                styles = (shore, foam, shore)
                edge = [
                    Segment(ch, styles[i % len(styles)])
                    for i, ch in enumerate(glyphs)
                ]
                right_from = cut + n
            right = _slice_cells(cover_lines[y], right_from, width)
            line = left + edge + right
            yield from line
            if y < height - 1:
                yield Segment.line()


def _waterline(t: float, width: int, y: int) -> int:
    """Column where dry land meets water; 0 is all splash, ``width`` is all UI."""
    hold = 0.08
    if t <= hold:
        u = 0.0
    else:
        u = (t - hold) / (1.0 - hold)
    u = u * u * (3.0 - 2.0 * u)
    base = int(u * (width + 8)) - 3
    wobble = int(round(math.sin(y * 0.5 + t * 8.0) * 2.5))
    return max(0, min(width, base + wobble))


def _slice_cells(line: list[Segment], start: int, end: int) -> list[Segment]:
    if end <= start:
        return []
    out: list[Segment] = []
    pos = 0
    for seg in line:
        if seg.control:
            continue
        length = seg.cell_length
        seg_end = pos + length
        if length == 0 or seg_end <= start or pos >= end:
            pos = seg_end
            continue
        keep_from = max(0, start - pos)
        keep_to = min(length, end - pos)
        piece = seg
        if keep_from:
            _, piece = piece.split_cells(keep_from)
            keep_to -= keep_from
        if keep_to < piece.cell_length:
            piece, _ = piece.split_cells(keep_to)
        if piece.text:
            out.append(piece)
        pos = seg_end
    return out
