"""Discover and load swappable 24x24 mascot packs."""

from __future__ import annotations

from pathlib import Path

from coding_agent.cli.pixel import PixelGrid, parse_grid
from coding_agent.cli.sprites.png import load_png

POSES = ("idle", "think", "tool", "ok", "err")
SPRITE_SIZE = 24
BUILTIN_PACKS = Path(__file__).resolve().parent / "packs"


def user_home_packs() -> Path:
    return Path.home() / ".wavemio" / "mascots"


def workspace_packs(workdir: Path | None) -> Path | None:
    if workdir is None:
        return None
    return Path(workdir) / ".wavemio" / "mascots"


def discover_packs(
    workdir: Path | None = None, *, include_user: bool = True
) -> dict[str, Path]:
    """Return pack name → directory. Later roots override the same name."""
    roots: list[Path] = [BUILTIN_PACKS]
    if include_user:
        roots.append(user_home_packs())
        ws = workspace_packs(workdir)
        if ws is not None:
            roots.append(ws)
    found: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.name in POSES or child.name.startswith("."):
                continue
            if not child.is_dir():
                continue
            if _pose_file(child, "idle") is not None:
                found[child.name] = child
    return found


def parse_palette(text: str) -> dict[str, str]:
    palette: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"palette line must be k=#RRGGBB, got {raw!r}")
        key, value = key.strip(), value.strip()
        if len(key) != 1:
            raise ValueError(f"palette key must be one character, got {key!r}")
        if not value.startswith("#") or len(value) != 7:
            raise ValueError(f"expected #RRGGBB, got {value!r}")
        palette[key] = value
    if not palette:
        raise ValueError("palette is empty")
    return palette


def parse_frame_text(text: str, size: int = SPRITE_SIZE) -> list[str]:
    rows: list[str] = []
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            continue
        rows.append(stripped[:size].ljust(size, "."))
    if len(rows) < size:
        rows.extend(["." * size] * (size - len(rows)))
    return rows[:size]


def load_pack(
    name: str,
    workdir: Path | None = None,
    *,
    include_user: bool = True,
) -> tuple[dict[str, str], dict[str, PixelGrid]]:
    packs = discover_packs(workdir, include_user=include_user)
    root = packs.get(name)
    if root is None:
        raise FileNotFoundError(f"mascot pack {name!r} not found")
    pal_path = root / "palette.txt"
    palette = parse_palette(pal_path.read_text(encoding="utf-8")) if pal_path.is_file() else {}
    poses: dict[str, PixelGrid] = {}
    for pose in POSES:
        path = _pose_file(root, pose)
        if path is None:
            continue
        poses[pose] = _load_frame(path, palette)
    if "idle" not in poses:
        raise FileNotFoundError(f"mascot pack {name!r} has no idle.txt or idle.png")
    for pose in POSES:
        poses.setdefault(pose, poses["idle"])
    return palette, poses


def _pose_file(root: Path, pose: str) -> Path | None:
    for suffix in (".png", ".txt"):
        path = root / f"{pose}{suffix}"
        if path.is_file():
            return path
    return None


def _load_frame(path: Path, palette: dict[str, str]) -> PixelGrid:
    if path.suffix.lower() == ".png":
        return load_png(path, SPRITE_SIZE)
    if not palette:
        raise ValueError(f"{path.name} requires palette.txt")
    return parse_grid(parse_frame_text(path.read_text(encoding="utf-8")), palette)


def pack_origin(path: Path) -> str:
    resolved = path.resolve()
    try:
        resolved.relative_to(BUILTIN_PACKS.resolve())
        return "内置"
    except ValueError:
        pass
    try:
        resolved.relative_to(user_home_packs().resolve())
        return "用户"
    except ValueError:
        return "工作区"
