from __future__ import annotations

import re
import tomllib
from pathlib import Path

import coding_agent


def _changelog_version(repo_root: Path) -> str:
    text = (repo_root / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"当前版本：\*\*v(\d+\.\d+\.\d+)\*\*", text)
    assert match, "CHANGELOG.md must declare 当前版本：**vX.Y.Z**"
    return match.group(1)


def _pyproject_version(repo_root: Path) -> str:
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_package_version_matches_changelog(repo_root: Path) -> None:
    expected = _changelog_version(repo_root)
    assert coding_agent.__version__ == expected
    assert _pyproject_version(repo_root) == expected
