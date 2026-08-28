"""Half-block pixel renderer: one terminal cell holds two stacked RGB pixels."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from rich.text import Text

Pixel = tuple[int, int, int, int]
PixelGrid = tuple[tuple[Pixel, ...], ...]

_TRANSPARENT: Pixel = (0, 0, 0, 0)


def parse_grid(rows: Sequence[str], palette: Mapping[str, str]) -> PixelGrid:
    """Turn palette-index strings into an even-height RGBA grid."""
    if not rows:
        raise ValueError("sprite is empty")
    width = max(len(row) for row in rows)
    rgb: dict[str, Pixel] = {".": _TRANSPARENT, "0": _TRANSPARENT}
    for key, hex_color in palette.items():
        rgb[key] = _hex_pixel(hex_color)
    lines: list[tuple[Pixel, ...]] = []
    for row in rows:
        padded = row.ljust(width, ".")
        pixels: list[Pixel] = []
        for ch in padded:
            if ch not in rgb:
                raise ValueError(f"unknown sprite pixel {ch!r}")
            pixels.append(rgb[ch])
        lines.append(tuple(pixels))
    if len(lines) % 2:
        lines.append(tuple(_TRANSPARENT for _ in range(width)))
    return tuple(lines)


def _hex_pixel(hex_color: str) -> Pixel:
    raw = hex_color.removeprefix("#")
    if len(raw) != 6:
        raise ValueError(f"expected RRGGBB, got {hex_color!r}")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), 255)


def _css(pixel: Pixel) -> str:
    return f"#{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}"


def _cell(top: Pixel, bot: Pixel) -> tuple[str, str]:
    top_on = top[3] > 0
    bot_on = bot[3] > 0
    if not top_on and not bot_on:
        return " ", ""
    if top_on and bot_on:
        return "▀", f"{_css(top)} on {_css(bot)}"
    if top_on:
        return "▀", _css(top)
    return "▄", _css(bot)


def render_halfblock(grid: PixelGrid) -> Text:
    """Map each pair of rows onto ``▀`` cells (fg = top, bg = bottom)."""
    if not grid:
        return Text()
    width = len(grid[0])
    height = len(grid)
    out = Text()
    for y in range(0, height, 2):
        top_row = grid[y]
        bot_row = grid[y + 1] if y + 1 < height else tuple(_TRANSPARENT for _ in range(width))
        if y:
            out.append("\n")
        pending: list[str] = []
        pending_style = ""
        for x in range(width):
            ch, style = _cell(top_row[x], bot_row[x])
            if pending and style != pending_style:
                out.append("".join(pending), style=pending_style or None)
                pending = []
            pending.append(ch)
            pending_style = style
        if pending:
            out.append("".join(pending), style=pending_style or None)
    return out
