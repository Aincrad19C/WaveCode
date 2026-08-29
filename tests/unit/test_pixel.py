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


def test_idle_sprite_is_32x32_gif() -> None:
    _, poses = load_pack("default", include_user=False)
    clip = poses["idle"]
    assert len(clip.frames) == 8
    assert clip.delay_ms == 100
    grid = clip.at(0)
    assert len(grid) == 32
    assert len(grid[0]) == 32
    assert any(pixel[3] for row in grid for pixel in row)
    assert any(pixel[3] == 0 for row in grid for pixel in row)
    art = render_halfblock(grid)
    lines = art.plain.splitlines()
    assert len(lines) == 16
    assert all(len(line) <= 32 for line in lines)
    assert any(ch in art.plain for ch in "▀▄")
    for banned in ("鲸鱼娘", "鲸鱼酿", "像素鲸鱼娘", "预留"):
        assert banned not in art.plain


def test_default_pack_maps_gif_poses() -> None:
    from coding_agent.cli.sprites.pack import BUILTIN_PACKS, POSES, SPRITE_SIZE, load_pack

    root = BUILTIN_PACKS / "default"
    files = ("idle", "think", "tool", "err")
    for pose in files:
        assert (root / f"{pose}.gif").is_file()
        assert not (root / f"{pose}.png").exists()
        assert not (root / f"{pose}.txt").exists()
    assert not (root / "ok.gif").is_file()
    palette, poses = load_pack("default", include_user=False)
    assert palette == {}
    assert set(poses) == set(POSES)
    for name in files:
        clip = poses[name]
        assert len(clip.frames) == 8
        grid = clip.frames[0]
        assert len(grid) == SPRITE_SIZE
        assert len(grid[0]) == SPRITE_SIZE
        assert any(pixel[3] for row in grid for pixel in row)
    assert poses["ok"] is poses["idle"]
    assert poses["think"].frames[0] != poses["idle"].frames[0]
    assert poses["tool"].frames[0] != poses["idle"].frames[0]
    assert poses["err"].frames[0] != poses["idle"].frames[0]


def test_builtin_pack_gif_is_package_data() -> None:
    from importlib.resources import files

    idle = files("coding_agent.cli.sprites.packs").joinpath("default", "idle.gif")
    assert idle.is_file()


def test_ensure_user_packs_writes_howto(tmp_path) -> None:
    from coding_agent.cli.sprites.pack import ensure_user_packs

    dest = ensure_user_packs(home=tmp_path)
    assert dest == tmp_path / ".wavecode" / "mascots"
    readme = dest / "README.txt"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "~/.wavecode/mascots" in text
    assert "idle.gif" in text
    ensure_user_packs(home=tmp_path)
    assert readme.read_text(encoding="utf-8") == text


def test_wavecode_pack_overrides_legacy_wavemio(tmp_path) -> None:
    from coding_agent.cli.sprites.pack import discover_packs

    legacy = tmp_path / ".wavemio" / "mascots" / "blob"
    current = tmp_path / ".wavecode" / "mascots" / "blob"
    legacy.mkdir(parents=True)
    current.mkdir(parents=True)
    (legacy / "idle.txt").write_text(("k" * 32 + "\n") + ("." * 32 + "\n") * 31, encoding="utf-8")
    (legacy / "palette.txt").write_text("k=#FF0000\n", encoding="utf-8")
    (current / "idle.txt").write_text(("k" * 32 + "\n") + ("." * 32 + "\n") * 31, encoding="utf-8")
    (current / "palette.txt").write_text("k=#00FF00\n", encoding="utf-8")
    packs = discover_packs(tmp_path)
    assert packs["blob"] == current


def test_workspace_pack_overrides_and_falls_back_pose(tmp_path) -> None:
    from coding_agent.cli.sprites.bank import MascotBank
    from coding_agent.cli.sprites.pack import discover_packs

    root = tmp_path / ".wavemio" / "mascots" / "blob"
    root.mkdir(parents=True)
    (root / "palette.txt").write_text("k=#FF0000\nb=#00FF00\n", encoding="utf-8")
    (root / "idle.txt").write_text(("k" * 32 + "\n") + ("." * 32 + "\n") * 31, encoding="utf-8")
    packs = discover_packs(tmp_path)
    assert packs["blob"] == root
    bank = MascotBank()
    bank.set_workdir(tmp_path)
    kind, body = bank.apply("blob")
    assert kind == "note"
    assert "blob" in body
    pixel = bank.grid()[0][0]
    assert pixel[:3] == (255, 0, 0)
    bank.set_pose("think")
    # missing think.txt falls back to idle
    assert bank.grid()[0][0][:3] == (255, 0, 0)


def _blank_grid(pixel: tuple[int, int, int, int] = (0, 0, 0, 0)):
    row = tuple(pixel for _ in range(32))
    return tuple(row for _ in range(32))


def _stamp(rgb: tuple[int, int, int], x: int = 0, y: int = 0):
    rows = [list(row) for row in _blank_grid()]
    rows[y][x] = (rgb[0], rgb[1], rgb[2], 255)
    return tuple(tuple(px) for px in rows)


def test_gif_decoder_rejects_garbage() -> None:
    from coding_agent.cli.sprites.gifdec import decode_gif

    with pytest.raises(ValueError, match="not a GIF"):
        decode_gif(b"not-a-gif")


def test_png_roundtrip_and_rejects_wrong_size() -> None:
    from coding_agent.cli.sprites.png import decode_png, encode_png

    grid = _stamp((26, 127, 191), 3, 5)
    out = decode_png(encode_png(grid))
    assert out == grid
    assert out[5][3][:3] == (26, 127, 191)
    tiny = (((255, 0, 0, 255), (0, 0, 0, 0)), ((0, 0, 0, 0), (0, 0, 0, 0)))
    with pytest.raises(ValueError, match="32x32"):
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
    assert poses["idle"].frames[0][0][0][:3] == (255, 0, 0)
    assert poses["ok"].frames[0][0][1][:3] == (0, 255, 0)
    assert poses["think"] is poses["idle"]
    bank = MascotBank()
    bank.set_workdir(tmp_path)
    bank.apply("pngpet")
    bank.set_pose("ok")
    assert bank.grid()[0][1][:3] == (0, 255, 0)


