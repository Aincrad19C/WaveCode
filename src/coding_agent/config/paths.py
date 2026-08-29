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


def legacy_workspace_mascot_dir(workdir: Path | None) -> Path | None:
    if workdir is None:
        return None
    return Path(workdir) / LEGACY_DIRNAME / MASCOTS


def extra_mascot_roots(workdir: Path | None = None, *, include_user: bool = True) -> list[Path]:
    """User and workspace mascot dirs. Later entries override the same pack name."""
    if not include_user:
        return []
    roots: list[Path] = [legacy_user_mascot_dir(), user_mascot_dir()]
    legacy_ws = legacy_workspace_mascot_dir(workdir)
    ws = workspace_mascot_dir(workdir)
    if legacy_ws is not None:
        roots.append(legacy_ws)
    if ws is not None:
        roots.append(ws)
    return roots
