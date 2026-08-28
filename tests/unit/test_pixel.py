from __future__ import annotations

import pytest

from coding_agent.cli.pixel import parse_grid, render_halfblock
from coding_agent.cli.sprites.pack import load_pack


def test_parse_grid_rejects_unknown_pixel() -> None:
    with pytest.raises(ValueError, match="unknown sprite pixel"):
        parse_grid(["z"], {"k": "#0E1E44"})
    with pytest.raises(ValueError, match="sprite is empty"):
        parse_grid([], {"k": "#0E1E44"})


def test_halfblock_stacks_two_rows() -> None:
    grid = parse_grid(["ww", "dd"], {"w": "#FFFFFF", "d": "#174B9E"})
    text = render_halfblock(grid)
    assert text.plain == "▀▀"
    styles = " ".join(str(span.style) for span in text.spans)
    assert "#ffffff" in styles
    assert "#174b9e" in styles


def test_idle_sprite_is_blank_24x24() -> None:
    _, poses = load_pack("default", include_user=False)
    grid = poses["idle"]
    assert len(grid) == 24
    assert len(grid[0]) == 24
    assert all(pixel[3] == 0 for row in grid for pixel in row)
    art = render_halfblock(grid)
    lines = art.plain.splitlines()
    assert len(lines) == 12
    assert all(len(line) <= 24 for line in lines)
    assert not any(ch in art.plain for ch in "▀▄")
    for banned in ("鲸鱼娘", "鲸鱼酿", "像素鲸鱼娘", "预留"):
        assert banned not in art.plain


def test_default_pack_has_five_blank_png_poses() -> None:
    from coding_agent.cli.sprites.pack import BUILTIN_PACKS, POSES, load_pack

    root = BUILTIN_PACKS / "default"
    for pose in POSES:
        assert (root / f"{pose}.png").is_file()
        assert not (root / f"{pose}.txt").exists()
    palette, poses = load_pack("default", include_user=False)
    assert palette == {}
    assert set(poses) == set(POSES)
    for grid in poses.values():
        assert len(grid) == 24
        assert len(grid[0]) == 24
        assert all(pixel[3] == 0 for row in grid for pixel in row)


def test_workspace_pack_overrides_and_falls_back_pose(tmp_path) -> None:
    from coding_agent.cli.sprites.bank import MascotBank
    from coding_agent.cli.sprites.pack import discover_packs

    root = tmp_path / ".wavemio" / "mascots" / "blob"
    root.mkdir(parents=True)
    (root / "palette.txt").write_text("k=#FF0000\nb=#00FF00\n", encoding="utf-8")
    (root / "idle.txt").write_text(("k" * 24 + "\n") + ("." * 24 + "\n") * 23, encoding="utf-8")
    packs = discover_packs(tmp_path)
    assert packs["blob"] == root
    bank = MascotBank()
    bank.set_workdir(tmp_path)
    kind, body = bank.apply("blob")
    assert kind == "note"
    assert "blob" in body
    pixel = bank.grid()[0][0]
    assert pixel[:3] == (255, 0, 0)
    bank.apply("think")
    # missing think.txt falls back to idle
    assert bank.grid()[0][0][:3] == (255, 0, 0)


def _blank_grid(pixel: tuple[int, int, int, int] = (0, 0, 0, 0)):
    row = tuple(pixel for _ in range(24))
    return tuple(row for _ in range(24))


def _stamp(rgb: tuple[int, int, int], x: int = 0, y: int = 0):
    rows = [list(row) for row in _blank_grid()]
    rows[y][x] = (rgb[0], rgb[1], rgb[2], 255)
    return tuple(tuple(px) for px in rows)


def test_png_roundtrip_and_rejects_wrong_size() -> None:
    from coding_agent.cli.sprites.png import decode_png, encode_png

    grid = _stamp((26, 127, 191), 3, 5)
    out = decode_png(encode_png(grid))
    assert out == grid
    assert out[5][3][:3] == (26, 127, 191)
    tiny = (((255, 0, 0, 255), (0, 0, 0, 0)), ((0, 0, 0, 0), (0, 0, 0, 0)))
    with pytest.raises(ValueError, match="24x24"):
        decode_png(encode_png(tiny))
    with pytest.raises(ValueError, match="not a PNG"):
        decode_png(b"not-a-png")


def test_png_only_pack_without_palette(tmp_path) -> None:
    from coding_agent.cli.sprites.bank import MascotBank
    from coding_agent.cli.sprites.pack import discover_packs, load_pack
    from coding_agent.cli.sprites.png import encode_png

    root = tmp_path / ".wavemio" / "mascots" / "pngpet"
    root.mkdir(parents=True)
    (root / "idle.png").write_bytes(encode_png(_stamp((255, 0, 0))))
    (root / "ok.png").write_bytes(encode_png(_stamp((0, 255, 0), 1, 0)))
    (root / "idle.txt").write_text("this should be ignored\n", encoding="utf-8")
    assert "pngpet" in discover_packs(tmp_path)
    palette, poses = load_pack("pngpet", tmp_path)
    assert palette == {}
    assert poses["idle"][0][0][:3] == (255, 0, 0)
    assert poses["ok"][0][1][:3] == (0, 255, 0)
    assert poses["think"] == poses["idle"]
    bank = MascotBank()
    bank.set_workdir(tmp_path)
    bank.apply("pngpet")
    bank.apply("ok")
    assert bank.grid()[0][1][:3] == (0, 255, 0)


