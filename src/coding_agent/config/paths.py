"""Writable data directories for WaveCode.

The app writes ``.wavecode`` under the home directory and the workspace.
Legacy ``.wavemio`` locations are still scanned so existing packs and logs
keep working after the rename.
"""

from __future__ import annotations

from pathlib import Path

PRODUCT_DIRNAME = ".wavecode"
LEGACY_DIRNAME = ".wavemio"
MASCOTS = "mascots"
SKILLS = "skills"


def user_data_dir() -> Path:
    return Path.home() / PRODUCT_DIRNAME


def user_mascot_dir() -> Path:
    return user_data_dir() / MASCOTS


def legacy_user_mascot_dir() -> Path:
    return Path.home() / LEGACY_DIRNAME / MASCOTS


def workspace_mascot_dir(workdir: Path | None) -> Path | None:
    if workdir is None:
        return None
    return Path(workdir) / PRODUCT_DIRNAME / MASCOTS


def extra_data_roots(
    subdir: str, workdir: Path | None = None, *, include_user: bool = True
) -> list[Path]:
    """Legacy home, current home, then workspace. Later entries override names."""
    if not include_user:
        return []
    roots: list[Path] = [
        Path.home() / LEGACY_DIRNAME / subdir,
        Path.home() / PRODUCT_DIRNAME / subdir,
    ]
    if workdir is not None:
        roots.append(Path(workdir) / LEGACY_DIRNAME / subdir)
        roots.append(Path(workdir) / PRODUCT_DIRNAME / subdir)
    return roots


def extra_mascot_roots(workdir: Path | None = None, *, include_user: bool = True) -> list[Path]:
    """User and workspace mascot dirs. Later entries override the same pack name."""
    return extra_data_roots(MASCOTS, workdir, include_user=include_user)


def extra_skill_roots(workdir: Path | None = None, *, include_user: bool = True) -> list[Path]:
    return extra_data_roots(SKILLS, workdir, include_user=include_user)


def user_skill_dir() -> Path:
    return user_data_dir() / SKILLS
