"""Leave the fullscreen TUI to run vim or a diff."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

_DIFF_TIMEOUT_S = 2.0


def editor_cmd() -> list[str] | None:
    for raw in (os.environ.get("VISUAL"), os.environ.get("EDITOR"), "vim", "vi"):
        if not raw:
            continue
        parts = shlex.split(raw, posix=True)
        if parts and shutil.which(parts[0]):
            return parts
    return None


def resolve_under_root(root: Path | str, rel: str) -> Path | None:
    base = Path(root).resolve()
    if not rel or rel.startswith("…"):
        return None
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def is_vim_like(argv: list[str]) -> bool:
    name = Path(argv[0]).name.lower()
    return name in {"vim", "vi", "nvim", "view"}


def file_open_argv(root: Path | str, rel: str) -> list[str] | None:
    editor = editor_cmd()
    path = resolve_under_root(root, rel)
    if editor is None or path is None or not path.is_file():
        return None
    return [*editor, str(path)]


def read_diff(root: Path | str, rel: str) -> str:
    base = Path(root)
    path = resolve_under_root(base, rel)
    if path is None:
        return ""
    if not (base / ".git").exists():
        return ""
    text = _git_output(base, ["git", "--no-pager", "diff", "--no-color", "--", rel])
    if text.strip():
        return text
    if path.is_file():
        return _git_output(
            base,
            ["git", "--no-pager", "diff", "--no-color", "--no-index", "--", "/dev/null", rel],
        )
    return text


def _git_output(cwd: Path, argv: list[str]) -> str:
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=_DIFF_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout or ""
