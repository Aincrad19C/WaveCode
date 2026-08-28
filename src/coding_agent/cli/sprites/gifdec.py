"""GIF89a decoder for mascot clips (stdlib only). Scales to the pack canvas."""

from __future__ import annotations

from pathlib import Path

from coding_agent.cli.pixel import Pixel, PixelGrid

_TRANSPARENT: Pixel = (0, 0, 0, 0)
_GIF87 = b"GIF87a"
_GIF89 = b"GIF89a"


def load_gif(path: Path | str, size: int = 32) -> tuple[tuple[PixelGrid, ...], int]:
    """Return scaled frames and the shared delay in milliseconds."""
    return decode_gif(Path(path).read_bytes(), size=size)


def decode_gif(data: bytes, size: int = 32) -> tuple[tuple[PixelGrid, ...], int]:
    if len(data) < 13 or data[:6] not in (_GIF87, _GIF89):
        raise ValueError("not a GIF")
    width, height = int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    packed = data[10]
    pos = 13
    gct: list[Pixel] | None = None
    if packed & 0x80:
        gct, pos = _color_table(data, pos, packed & 7)
    canvas = [_TRANSPARENT] * (width * height)
    frames: list[PixelGrid] = []
    delays: list[int] = []
    trans: int | None = None
    disposal = 0
    delay = 10
    while pos < len(data):
        kind = data[pos]
        pos += 1
        if kind == 0x3B:
            break
        if kind == 0x21:
            if pos >= len(data):
                break
            label = data[pos]
            pos += 1
            block, pos = _subblocks(data, pos)
            if label == 0xF9 and len(block) >= 4:
                disposal = (block[0] >> 2) & 7
                delay = int.from_bytes(block[1:3], "little")
                trans = block[3] if block[0] & 1 else None
            continue
        if kind != 0x2C:
            raise ValueError("bad GIF block")
        if pos + 9 > len(data):
            raise ValueError("truncated GIF image")
        left = int.from_bytes(data[pos : pos + 2], "little")
        top = int.from_bytes(data[pos + 2 : pos + 4], "little")
        iw = int.from_bytes(data[pos + 4 : pos + 6], "little")
        ih = int.from_bytes(data[pos + 6 : pos + 8], "little")
        ipacked = data[pos + 8]
        pos += 9
        palette = gct
        if ipacked & 0x80:
            palette, pos = _color_table(data, pos, ipacked & 7)
        if palette is None:
            raise ValueError("GIF missing color table")
        if pos >= len(data):
            raise ValueError("truncated GIF LZW")
        min_code = data[pos]
        pos += 1
        compressed, pos = _subblocks(data, pos)
        indexes = _lzw(compressed, min_code)
        if ipacked & 0x40:
            indexes = _deinterlace(indexes, iw, ih)
        backup = list(canvas) if disposal == 3 else None
        _blit(canvas, width, height, left, top, iw, ih, indexes, palette, trans)
        frames.append(_scale(_grid(canvas, width, height), size))
        delays.append(max(10, delay) * 10)
        if disposal == 2:
            _clear(canvas, width, height, left, top, iw, ih)
        elif disposal == 3 and backup is not None:
            canvas = backup
    if not frames:
        raise ValueError("GIF has no frames")
    common = delays[0] if delays and all(d == delays[0] for d in delays) else delays[0]
    return tuple(frames), common


def _color_table(data: bytes, pos: int, size_bits: int) -> tuple[list[Pixel], int]:
    n = 3 * (2 ** (size_bits + 1))
    chunk = data[pos : pos + n]
    if len(chunk) != n:
        raise ValueError("truncated GIF color table")
    table = [(chunk[i], chunk[i + 1], chunk[i + 2], 255) for i in range(0, n, 3)]
    return table, pos + n


def _subblocks(data: bytes, pos: int) -> tuple[bytes, int]:
    out = bytearray()
    while pos < len(data):
        n = data[pos]
        pos += 1
        if n == 0:
            return bytes(out), pos
        out.extend(data[pos : pos + n])
        pos += n
    raise ValueError("truncated GIF sub-blocks")


def _lzw(data: bytes, min_code: int) -> list[int]:
    clear = 1 << min_code
    eoi = clear + 1
    code_size = min_code + 1
    next_code = eoi + 1
    table: list[list[int] | None] = [[i] for i in range(clear)] + [None, None]
    table.extend([None] * (4096 - len(table)))
    bits = 0
    buf = 0
    src = 0
    out: list[int] = []
    prev: list[int] | None = None

    def read_code() -> int | None:
        nonlocal bits, buf, src, code_size
        while bits < code_size:
            if src >= len(data):
                return None
            buf |= data[src] << bits
            src += 1
            bits += 8
        code = buf & ((1 << code_size) - 1)
        buf >>= code_size
        bits -= code_size
        return code

    while True:
        code = read_code()
        if code is None or code == eoi:
            break
        if code == clear:
            table = [[i] for i in range(clear)] + [None, None]
            table.extend([None] * (4096 - len(table)))
            code_size = min_code + 1
            next_code = eoi + 1
            prev = None
            continue
        if prev is None:
            seq = table[code]
            if seq is None:
                raise ValueError("bad GIF LZW code")
            out.extend(seq)
            prev = seq
            continue
        if code < next_code and table[code] is not None:
            seq = table[code]
            assert seq is not None
        elif code == next_code:
            seq = prev + [prev[0]]
        else:
            raise ValueError("bad GIF LZW code")
        out.extend(seq)
        if next_code < 4096:
            table[next_code] = prev + [seq[0]]
            next_code += 1
            if next_code == (1 << code_size) and code_size < 12:
                code_size += 1
        prev = seq
    return out


def _deinterlace(indexes: list[int], width: int, height: int) -> list[int]:
    rows: list[list[int]] = [[] for _ in range(height)]
    i = 0
    for start, step in ((0, 8), (4, 8), (2, 4), (1, 2)):
        y = start
        while y < height:
            rows[y] = indexes[i : i + width]
            i += width
            y += step
    out: list[int] = []
    for row in rows:
        out.extend(row)
    return out


def _blit(
    canvas: list[Pixel],
    cw: int,
    ch: int,
    left: int,
    top: int,
    iw: int,
    ih: int,
    indexes: list[int],
    palette: list[Pixel],
    trans: int | None,
) -> None:
    for y in range(ih):
        cy = top + y
        if not (0 <= cy < ch):
            continue
        base = y * iw
        for x in range(iw):
            cx = left + x
            if not (0 <= cx < cw):
                continue
            idx = indexes[base + x] if base + x < len(indexes) else 0
            if trans is not None and idx == trans:
                continue
            if idx >= len(palette):
                continue
            canvas[cy * cw + cx] = palette[idx]


def _clear(
    canvas: list[Pixel], cw: int, ch: int, left: int, top: int, iw: int, ih: int
) -> None:
    for y in range(top, min(ch, top + ih)):
        row = y * cw
        for x in range(left, min(cw, left + iw)):
            canvas[row + x] = _TRANSPARENT


def _grid(canvas: list[Pixel], width: int, height: int) -> PixelGrid:
    rows = []
    for y in range(height):
        start = y * width
        rows.append(tuple(canvas[start : start + width]))
    return tuple(rows)


def _scale(grid: PixelGrid, size: int) -> PixelGrid:
    height = len(grid)
    width = len(grid[0]) if height else 0
    if (width, height) == (size, size):
        return grid
    if width == 0 or height == 0:
        blank = tuple(_TRANSPARENT for _ in range(size))
        return tuple(blank for _ in range(size))
    rows = []
    for y in range(size):
        sy = min(height - 1, (y * height + height // 2) // size)
        line = []
        src = grid[sy]
        for x in range(size):
            sx = min(width - 1, (x * width + width // 2) // size)
            line.append(src[sx])
        rows.append(tuple(line))
    return tuple(rows)
