"""Session-wide discovered skills and which are loaded into system."""

from __future__ import annotations

from pathlib import Path

from coding_agent.skills.pack import SkillPack, discover_skills, skill_origin, user_skill_dir

MAX_ACTIVE = 8
_USAGE = "请输入 /skill 打开勾选列表。"


class SkillBank:
    def __init__(self) -> None:
        self.workdir: Path | None = None
        self._active: list[str] = []

    @property
    def active(self) -> tuple[str, ...]:
        return tuple(self._active)

    def set_workdir(self, path: Path | str | None) -> None:
        self.workdir = None if path is None else Path(path)

    def discover(self) -> dict[str, SkillPack]:
        return discover_skills(self.workdir)

    def catalog(self) -> list[tuple[str, str]]:
        return [(pack.name, pack.description) for pack in self.discover().values()]

    def active_bodies(self) -> list[tuple[str, str]]:
        packs = self.discover()
        out: list[tuple[str, str]] = []
        for name in self._active:
            pack = packs.get(name)
            if pack is not None:
                out.append((name, pack.body))
        return out

    def rows(self) -> list[tuple[str, str, str, bool]]:
        """name, description, origin, checked."""
        return [
            (name, pack.description, skill_origin(pack.root), name in self._active)
            for name, pack in self.discover().items()
        ]

    def replace_active(self, names: list[str]) -> tuple[str, str]:
        packs = self.discover()
        chosen = [name for name in names if name in packs]
        if len(chosen) > MAX_ACTIVE:
            return "warn", f"最多同时装载 {MAX_ACTIVE} 个 skill"
        self._active = chosen
        if not chosen:
            return "note", "已卸下全部 skill"
        return "note", f"已装载 {', '.join(chosen)}"

    def list_text(self) -> str:
        lines = [
            f"当前已装载  {', '.join(self._active) if self._active else '无'}",
            "",
            "新包放到  ~/.wavecode/skills/<包名>/",
            f"本机路径  {user_skill_dir()}",
            "工作区也可：<工作区>/.wavecode/skills/<包名>/",
            "全屏：空格勾选，Enter 确认，Esc 取消。",
            "同名时工作区覆盖用户目录，用户目录覆盖发行包。",
            "",
            "包：",
        ]
        for name, description, origin, checked in self.rows():
            mark = "✓" if checked else " "
            lines.append(f"  [{mark}] {name:12} {origin}  {description}")
        lines.append("")
        lines.append(_USAGE)
        return "\n".join(lines)

    def apply(self, token: str) -> tuple[str, str]:
        if token.strip():
            return "warn", _USAGE
        return "pick", self.list_text()


_bank: SkillBank | None = None


def get_skills() -> SkillBank:
    global _bank
    if _bank is None:
        _bank = SkillBank()
    return _bank


def reset_skills() -> SkillBank:
    global _bank
    _bank = SkillBank()
    return _bank
