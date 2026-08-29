"""Discover SKILL.md packs (docs/13). Markdown only; no scripts run."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from coding_agent.config.paths import (
    LEGACY_DIRNAME,
    PRODUCT_DIRNAME,
    SKILLS,
    extra_skill_roots,
    user_skill_dir,
)

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
MAX_BODY = 8000
DESC_CLIP = 160
SKILL_FILE = "SKILL.md"

BUILTIN_SKILLS = Path(__file__).resolve().parent / "packs"

_HOWTO = """Skill 包

每个包是一个目录，内含 SKILL.md。将文件夹放入投放目录即可。

输入 /skill 打开勾选列表：空格切换、Enter 确认、Esc 取消。
滚动 REPL 打印当前列表，不接受包名参数。

投放目录，后者覆盖同名：

  0. 发行     WaveCode 安装包内的默认 skill
  1. 用户     ~/.wavecode/skills/<包名>/
  2. 工作区   <工作区>/.wavecode/skills/<包名>/
  兼容：仍读取 ~/.wavemio/skills/ 与 <工作区>/.wavemio/skills/

SKILL.md 示例：

---
name: frontend-design
description: 写或改网页时启用。先定视觉方向再写代码。
---

正文为 Markdown。仅注入该文件，不执行 scripts。

斜杠命令：

  /skill    打开勾选列表。全屏交互选择，REPL 打印列表。
"""


@dataclass(frozen=True, slots=True)
class SkillPack:
    name: str
    title: str
    description: str
    body: str
    root: Path


def _simple_map(raw: str) -> dict[str, str] | None:
    data: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            return None
        key, sep, value = stripped.partition(":")
        if not sep:
            return None
        key = key.strip()
        if not re.match(r"^[A-Za-z0-9_-]+$", key):
            return None
        data[key] = value.strip().strip("\"'")
    return data


def parse_skill_md(text: str, dirname: str) -> SkillPack | None:
    body = text
    meta: dict[str, str] = {}
    if text.startswith("---"):
        rest = text[3:].lstrip("\n")
        marker = "\n---"
        if marker not in rest and not rest.startswith("---"):
            return None
        if rest.startswith("---"):
            raw_fm, _, body = rest.partition("---")
        else:
            raw_fm, _, body = rest.partition(marker)
        parsed = _simple_map(raw_fm)
        if parsed is None:
            return None
        meta = parsed
        body = body.lstrip("\n")
    title = (meta.get("name") or dirname).strip() or dirname
    description = (meta.get("description") or "no description").strip()[:DESC_CLIP]
    return SkillPack(
        name=dirname,
        title=title,
        description=description,
        body=body[:MAX_BODY],
        root=Path(),
    )


def load_skill(root: Path, name: str) -> SkillPack | None:
    path = root / SKILL_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("unreadable skill %s", path)
        return None
    parsed = parse_skill_md(text, name)
    if parsed is None:
        logger.warning("skip skill %s: bad SKILL.md", root)
        return None
    return SkillPack(
        name=parsed.name,
        title=parsed.title,
        description=parsed.description,
        body=parsed.body,
        root=root,
    )


def discover_skills(
    workdir: Path | None = None,
    *,
    include_user: bool = True,
    include_builtin: bool = True,
) -> dict[str, SkillPack]:
    """Return skill name → pack. Later roots override the same name."""
    found: dict[str, SkillPack] = {}
    roots: list[Path] = []
    if include_builtin:
        roots.append(BUILTIN_SKILLS)
    roots.extend(extra_skill_roots(workdir, include_user=include_user))
    for base in roots:
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or child.name.startswith(".") or not NAME_RE.match(child.name):
                continue
            if not (child / SKILL_FILE).is_file():
                continue
            pack = load_skill(child, child.name)
            if pack is not None:
                found[pack.name] = pack
    return found


def ensure_user_skills(*, home: Path | None = None) -> Path:
    dest = (Path(home) / PRODUCT_DIRNAME / SKILLS) if home is not None else user_skill_dir()
    dest.mkdir(parents=True, exist_ok=True)
    readme = dest / "README.txt"
    if not readme.is_file():
        readme.write_text(_HOWTO, encoding="utf-8")
    return dest


def skill_origin(path: Path) -> str:
    resolved = path.resolve()
    try:
        resolved.relative_to(BUILTIN_SKILLS.resolve())
        return "发行"
    except ValueError:
        pass
    for root in (user_skill_dir(), Path.home() / LEGACY_DIRNAME / SKILLS):
        try:
            resolved.relative_to(root.resolve())
            return "用户"
        except ValueError:
            continue
    return "工作区"
