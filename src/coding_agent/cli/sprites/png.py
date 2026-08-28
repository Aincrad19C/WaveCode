"""Minimal PNG codec for 24x24 mascot frames (stdlib zlib only)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from coding_agent.cli.pixel import Pixel, PixelGrid

_SIG = b"\x89PNG\r\n\x1a\n"
_TRANSPARENT: Pixel = (0, 0, 0, 0)


def load_png(path: Path | str, size: int = 24) -> PixelGrid:
    """Read an 8-bit PNG and require an exact ``size`` x ``size`` canvas."""
    return decode_png(Path(path).read_bytes(), size=size)


def decode_png(data: bytes, size: int = 24) -> PixelGrid:
    if not data.startswith(_SIG):
        raise ValueError("not a PNG")
    ihdr: bytes | None = None
    plte: bytes | None = None
    trns: bytes | None = None
    idat = bytearray()
    pos = 8
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        start = pos + 8
        end = start + length
        if end + 4 > len(data):
            raise ValueError("truncated PNG chunk")
        chunk = data[start:end]
        crc = struct.unpack(">I", data[end : end + 4])[0]
        if zlib.crc32(tag + chunk) & 0xFFFFFFFF != crc:
            raise ValueError("bad PNG CRC")
        pos = end + 4
        if tag == b"IHDR":
            ihdr = chunk
        elif tag == b"PLTE":
            plte = chunk
        elif tag == b"tRNS":
            trns = chunk
        elif tag == b"IDAT":
            idat.extend(chunk)
        elif tag == b"IEND":
            break
    if ihdr is None or len(ihdr) != 13:
        raise ValueError("PNG missing IHDR")
    width, height, depth, color, comp, filt, interlace = struct.unpack(">IIBBBBB", ihdr)
    if (width, height) != (size, size):
        raise ValueError(f"mascot PNG must be {size}x{size}, got {width}x{height}")
    if depth != 8 or comp != 0 or filt != 0 or interlace != 0:
        raise ValueError("mascot PNG must be 8-bit, non-interlaced")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if channels is None:
        raise ValueError(f"unsupported PNG color type {color}")
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    rows = _unfilter(raw, height, stride, channels)
    palette = _palette(plte, trns) if color == 3 else None
    key = _rgb_key(trns) if color in (0, 2) and trns else None
    grid: list[tuple[Pixel, ...]] = []
    for scan in rows:
        line: list[Pixel] = []
        for x in range(width):
            src = scan[x * channels : (x + 1) * channels]
            line.append(_pixel(src, color, palette, key))
        grid.append(tuple(line))
    return tuple(grid)


def encode_png(grid: PixelGrid) -> bytes:
    """Write a 24-bit RGB or 32-bit RGBA PNG (filter None). For tests and packs."""
    height = len(grid)
    width = len(grid[0]) if height else 0
    rgba = any(px[3] < 255 for row in grid for px in row)
    color = 6 if rgba else 2
    raw = bytearray()
    for row in grid:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a) if rgba else (r, g, b))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)
    return b"".join(
        (
            _SIG,
            _chunk(b"IHDR", ihdr),
            _chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
            _chunk(b"IEND", b""),
        )
    )


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> list[bytes]:
    need = height * (stride + 1)
    if len(raw) < need:
        raise ValueError("truncated PNG scanlines")
    rows: list[bytes] = []
    prev = bytes(stride)
    i = 0
    for _ in range(height):
        ftype = raw[i]
        scan = bytearray(raw[i + 1 : i + 1 + stride])
        i += stride + 1
        if ftype == 0:
            pass
        elif ftype == 1:
            for x in range(stride):
                scan[x] = (scan[x] + (scan[x - bpp] if x >= bpp else 0)) & 255
        elif ftype == 2:
            for x in range(stride):
                scan[x] = (scan[x] + prev[x]) & 255
        elif ftype == 3:
            for x in range(stride):
                left = scan[x - bpp] if x >= bpp else 0
                scan[x] = (scan[x] + (left + prev[x]) // 2) & 255
        elif ftype == 4:
            for x in range(stride):
                left = scan[x - bpp] if x >= bpp else 0
                up = prev[x]
                ul = prev[x - bpp] if x >= bpp else 0
                scan[x] = (scan[x] + _paeth(left, up, ul)) & 255
        else:
            raise ValueError(f"unknown PNG filter {ftype}")
        prev = bytes(scan)
        rows.append(prev)
    return rows


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _palette(
    plte: bytes | None, trns: bytes | None
) -> list[Pixel]:
    if not plte or len(plte) % 3:
        raise ValueError("indexed PNG missing PLTE")
    colors: list[Pixel] = []
    for i in range(0, len(plte), 3):
        alpha = trns[i // 3] if trns and i // 3 < len(trns) else 255
        colors.append((plte[i], plte[i + 1], plte[i + 2], alpha))
    return colors


def _rgb_key(trns: bytes) -> Pixel | None:
    if len(trns) == 2:
        y = struct.unpack(">H", trns)[0]
        if y <= 255:
            return (y, y, y, 255)
    if len(trns) == 6:
        r, g, b = struct.unpack(">HHH", trns)
        if max(r, g, b) <= 255:
            return (r, g, b, 255)
    return None


def _pixel(
    src: bytes,
    color: int,
    palette: list[Pixel] | None,
    key: Pixel | None,
) -> Pixel:
    if color == 0:
        y = src[0]
        px: Pixel = (y, y, y, 255)
    elif color == 2:
        px = (src[0], src[1], src[2], 255)
    elif color == 3:
        if palette is None or src[0] >= len(palette):
            raise ValueError("PNG palette index out of range")
        px = palette[src[0]]
    elif color == 4:
        y, a = src[0], src[1]
        px = (y, y, y, a)
    else:
        px = (src[0], src[1], src[2], src[3])
    if px[3] == 0:
        return _TRANSPARENT
    if key is not None and px[:3] == key[:3]:
        return _TRANSPARENT
    return (px[0], px[1], px[2], 255)
