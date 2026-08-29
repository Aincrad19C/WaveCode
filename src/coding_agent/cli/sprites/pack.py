"""Discover and load swappable 32x32 mascot packs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from coding_agent.cli.pixel import PixelGrid, parse_grid
from coding_agent.cli.sprites.gifdec import load_gif
from coding_agent.cli.sprites.png import load_png
from coding_agent.config.paths import (
    MASCOTS,
    PRODUCT_DIRNAME,
    extra_mascot_roots,
    legacy_user_mascot_dir,
    user_mascot_dir,
    workspace_mascot_dir,
)

POSES = ("idle", "think", "tool", "ok", "err")
SPRITE_SIZE = 32
BUILTIN_PACKS = Path(__file__).resolve().parent / "packs"
_POSE_SUFFIXES = (".gif", ".png", ".txt")


@dataclass(frozen=True, slots=True)
class PoseClip:
    """One pose: a still frame or a looping GIF."""

    frames: tuple[PixelGrid, ...]
    delay_ms: int = 100

    def at(self, t: float = 0.0) -> PixelGrid:
        n = len(self.frames)
        if n == 1:
            return self.frames[0]
        delay = max(1, self.delay_ms)
        return self.frames[int(t * 1000 / delay) % n]


def user_home_packs() -> Path:
    return user_mascot_dir()


def workspace_packs(workdir: Path | None) -> Path | None:
    return workspace_mascot_dir(workdir)


def discover_packs(
    workdir: Path | None = None, *, include_user: bool = True
) -> dict[str, Path]:
    """Return pack name → directory. Later roots override the same name."""
    roots: list[Path] = [BUILTIN_PACKS, *extra_mascot_roots(workdir, include_user=include_user)]
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


def ensure_user_packs(*, home: Path | None = None) -> Path:
    """Create ``~/.wavecode/mascots`` and drop a HOWTO so users can add packs."""
    dest = (Path(home) / PRODUCT_DIRNAME / MASCOTS) if home is not None else user_mascot_dir()
    dest.mkdir(parents=True, exist_ok=True)
    readme = dest / "README.txt"
    if not readme.is_file():
        bundled = BUILTIN_PACKS / "README.txt"
        if bundled.is_file():
            readme.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


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
) -> tuple[dict[str, str], dict[str, PoseClip]]:
    packs = discover_packs(workdir, include_user=include_user)
    root = packs.get(name)
    if root is None:
        raise FileNotFoundError(f"mascot pack {name!r} not found")
    pal_path = root / "palette.txt"
    palette = parse_palette(pal_path.read_text(encoding="utf-8")) if pal_path.is_file() else {}
    poses: dict[str, PoseClip] = {}
    for pose in POSES:
        path = _pose_file(root, pose)
        if path is None:
            continue
        poses[pose] = _load_clip(path, palette)
    if "idle" not in poses:
        raise FileNotFoundError(f"mascot pack {name!r} has no idle.gif, idle.png or idle.txt")
    for pose in POSES:
        poses.setdefault(pose, poses["idle"])
    return palette, poses


def _pose_file(root: Path, pose: str) -> Path | None:
    for suffix in _POSE_SUFFIXES:
        path = root / f"{pose}{suffix}"
        if path.is_file():
            return path
    return None


def _load_clip(path: Path, palette: dict[str, str]) -> PoseClip:
    suffix = path.suffix.lower()
    if suffix == ".gif":
        frames, delay = load_gif(path, SPRITE_SIZE)
        return PoseClip(frames, delay)
    if suffix == ".png":
        return PoseClip((load_png(path, SPRITE_SIZE),))
    if not palette:
        raise ValueError(f"{path.name} requires palette.txt")
    still = parse_grid(parse_frame_text(path.read_text(encoding="utf-8")), palette)
    return PoseClip((still,))


def pack_origin(path: Path) -> str:
    resolved = path.resolve()
    try:
        resolved.relative_to(BUILTIN_PACKS.resolve())
        return "内置"
    except ValueError:
        pass
    for home_root in (user_mascot_dir(), legacy_user_mascot_dir()):
        try:
            resolved.relative_to(home_root.resolve())
            return "用户"
        except ValueError:
            continue
    return "工作区"
