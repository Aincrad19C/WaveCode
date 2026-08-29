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

_USAGE = "请输入 /mascot 打开勾选列表。"


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

    def rows(self) -> list[tuple[str, str, bool]]:
        """name, origin, checked. Radio: at most one checked."""
        self._ensure()
        return [
            (name, pack_origin(path), name == self.pack_name)
            for name, path in discover_packs(self.workdir).items()
        ]

    def list_text(self) -> str:
        lines = [
            f"当前  {self.pack_name}",
            "",
            "新包放到  ~/.wavecode/mascots/<包名>/  或  <工作区>/.wavecode/mascots/<包名>/",
            "启动时会把 default 复制进上述目录（已有文件不覆盖）。",
            f"本机用户目录  {user_home_packs()}",
            "全屏：空格勾选，Enter 确认，Esc 取消。",
            "同名时工作区覆盖用户目录，用户目录覆盖发行包。",
            "",
            "包：",
        ]
        for name, origin, checked in self.rows():
            mark = "✓" if checked else " "
            lines.append(f"  [{mark}] {name:12} {origin}")
        lines.append("")
        lines.append(_USAGE)
        return "\n".join(lines)

    def set_pose(self, name: str) -> None:
        if name in POSES:
            self.pose = name

    def select(self, name: str) -> tuple[str, str]:
        packs = discover_packs(self.workdir)
        if name in packs:
            self.pack_name = name
            self._loaded_key = None
            return "note", f"立绘包 = {name}"
        return "warn", f"未知立绘包 {name}。{_USAGE}"

    def apply(self, token: str) -> tuple[str, str]:
        """Slash dispatch: empty token opens the picker; extra arguments are rejected."""
        if token.strip():
            return "warn", _USAGE
        return "pick", self.list_text()


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
