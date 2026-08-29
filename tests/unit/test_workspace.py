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


def test_undo_restores_edits_and_deletes_new_files(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    old = tmp_path / "keep.py"
    old.write_text("v1\n", encoding="utf-8")
    ws.mark_new_task()
    ws.remember(old)
    old.write_text("v2\n", encoding="utf-8")
    created = tmp_path / "new.py"
    ws.remember(created)
    created.write_text("fresh\n", encoding="utf-8")
    assert ws.restore_task_files() == ["keep.py", "new.py"]
    assert old.read_text(encoding="utf-8") == "v1\n"
    assert not created.exists()
    assert ws.restore_task_files() == []


def test_undo_window_survives_task_without_writes(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    path = tmp_path / "a.py"
    path.write_text("one\n", encoding="utf-8")
    ws.mark_new_task()
    ws.remember(path)
    path.write_text("two\n", encoding="utf-8")
    ws.mark_new_task()
    assert path.read_text(encoding="utf-8") == "two\n"
    assert ws.restore_task_files() == ["a.py"]
    assert path.read_text(encoding="utf-8") == "one\n"


def test_first_write_of_new_task_drops_previous_undo(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    path = tmp_path / "a.py"
    path.write_text("one\n", encoding="utf-8")
    ws.mark_new_task()
    ws.remember(path)
    path.write_text("two\n", encoding="utf-8")
    ws.mark_new_task()
    ws.remember(path)
    path.write_text("three\n", encoding="utf-8")
    assert ws.restore_task_files() == ["a.py"]
    assert path.read_text(encoding="utf-8") == "two\n"


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
