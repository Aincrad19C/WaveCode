"""Session-wide current mascot pack and pose."""

from __future__ import annotations

import time
from pathlib import Path

from rich.text import Text

from coding_agent.cli.pixel import PixelGrid, render_halfblock
from coding_agent.cli.sprites.pack import (
    POSES,
    PoseClip,
    discover_packs,
    load_pack,
    pack_origin,
    user_home_packs,
)

_USAGE = "用法：/mascot  或  /mascot 包名"


class MascotBank:
    def __init__(self) -> None:
        self.workdir: Path | None = None
        self.pack_name = "default"
        self.pose = "idle"
        self._loaded_key: tuple[str, str] | None = None
        self._poses: dict[str, PoseClip] = {}

    def set_workdir(self, path: Path | str | None) -> None:
        workdir = None if path is None else Path(path)
        if workdir != self.workdir:
            self.workdir = workdir
            self._loaded_key = None

    def _ensure(self) -> dict[str, PoseClip]:
        key = (self.pack_name, str(self.workdir or ""))
        if self._loaded_key == key and self._poses:
            return self._poses
        try:
            _, poses = load_pack(self.pack_name, self.workdir)
        except FileNotFoundError:
            self.pack_name = "default"
            _, poses = load_pack("default", self.workdir, include_user=False)
        self._poses = poses
        self._loaded_key = (self.pack_name, str(self.workdir or ""))
        return self._poses

    def grid(self) -> PixelGrid:
        poses = self._ensure()
        clip = poses.get(self.pose) or poses["idle"]
        return clip.at(time.monotonic())

    def render(self) -> Text:
        return render_halfblock(self.grid())

    def list_text(self) -> str:
        packs = discover_packs(self.workdir)
        self._ensure()
        lines = [
            f"当前  {self.pack_name}",
            "",
            f"投放目录  {user_home_packs()}",
            "把含 idle.gif / idle.png / idle.txt 的文件夹放进去，然后 /mascot 包名。",
            "工作区也可用  <工作区>/.wavecode/mascots/<包名>/",
            "",
            "包：",
        ]
        for name, path in packs.items():
            mark = "*" if name == self.pack_name else " "
            lines.append(f"  {mark} {name:12} {pack_origin(path)}")
        lines.append("")
        lines.append(_USAGE)
        return "\n".join(lines)

    def set_pose(self, name: str) -> None:
        if name in POSES:
            self.pose = name

    def apply(self, token: str) -> tuple[str, str]:
        """Return (kind, body) for slash dispatch. kind is note|status|warn."""
        name = token.strip()
        if not name:
            return "status", self.list_text()
        packs = discover_packs(self.workdir)
        if name in packs:
            self.pack_name = name
            self._loaded_key = None
            return "note", f"立绘包 = {name}"
        return "warn", f"未知立绘包 {name}。{_USAGE}"


_bank: MascotBank | None = None


def get_bank() -> MascotBank:
    global _bank
    if _bank is None:
        _bank = MascotBank()
    return _bank


def reset_bank() -> MascotBank:
    global _bank
    _bank = MascotBank()
    return _bank
