"""Discover SKILL.md packs (docs/13). Markdown only; no scripts run."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from coding_agent.config.paths import PRODUCT_DIRNAME, SKILLS, extra_skill_roots, user_skill_dir

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
MAX_BODY = 8000
DESC_CLIP = 160
SKILL_FILE = "SKILL.md"

BUILTIN_SKILLS = Path(__file__).resolve().parent / "packs"
BUILTIN_SKILL_NAMES = frozenset({"frontend-design", "tdd"})


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
    roots: list[tuple[Path, bool]] = []
    if include_builtin:
        roots.append((BUILTIN_SKILLS, True))
    roots.extend((root, False) for root in extra_skill_roots(workdir, include_user=include_user))
    for base, builtin in roots:
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or child.name.startswith(".") or not NAME_RE.match(child.name):
                continue
            if builtin and child.name not in BUILTIN_SKILL_NAMES:
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
    return dest
