from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.errors import ToolPathError
from coding_agent.tools.workspace import Workspace


def test_resolve_relative_inside(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    assert ws.resolve("a/b.txt") == (tmp_path / "a/b.txt").resolve()


def test_resolve_dotdot_escape_raises(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    with pytest.raises(ToolPathError):
        ws.resolve("../etc/passwd")


def test_resolve_absolute_outside_raises(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    with pytest.raises(ToolPathError):
        ws.resolve("/etc/passwd")


def test_resolve_absolute_inside_ok(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    target = tmp_path / "x.txt"
    assert ws.resolve(str(target)) == target.resolve()


def test_symlink_escape_raises(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-target"
    outside.mkdir(exist_ok=True)
    root = tmp_path / "root"
    root.mkdir()
    link = root / "sneaky"
    link.symlink_to(outside)
    ws = Workspace(root)
    with pytest.raises(ToolPathError):
        ws.resolve("sneaky/file.txt")


def test_relpath(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    assert ws.relpath(tmp_path / "sub" / "f.py") == "sub/f.py"


def test_cwd_starts_at_root_and_can_leave(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    assert ws.cwd == tmp_path.resolve()
    parent = tmp_path.resolve().parent
    ws.set_cwd(parent)
    assert ws.cwd == parent
    ws.reset_cwd()
    assert ws.cwd == tmp_path.resolve()
    ws.set_cwd(tmp_path / "no-such-dir")
    assert ws.cwd == tmp_path.resolve()
