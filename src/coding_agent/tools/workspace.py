"""Workspace sandbox (docs/02 §4.2, docs/05 §1).

Every file path a tool touches resolves relative to this root; escapes
(including via symlinks) raise ToolPathError. Design rationale in docs/00 §7:
the model proposes paths, so trusting them blindly would let a confused model
edit files outside the project.
"""

from __future__ import annotations

from pathlib import Path

from coding_agent.errors import ToolPathError


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.cwd = self.root
        self._undo: dict[str, bytes | None] = {}
        self._undo_new_task = False

    def set_cwd(self, path: Path | str) -> None:
        """Remember bash's working directory. May leave ``root`` (bash is not sandboxed)."""
        candidate = Path(path).expanduser()
        try:
            candidate = candidate.resolve()
        except OSError:
            return
        if candidate.is_dir():
            self.cwd = candidate

    def reset_cwd(self) -> None:
        self.cwd = self.root

    def resolve(self, user_path: str) -> Path:
        candidate = Path(user_path)
        resolved = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError:
            raise ToolPathError(f"path escapes workspace: {user_path}") from None
        return resolved

    def relpath(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.root))

    def mark_new_task(self) -> None:
        """Next ``remember`` starts a new undo window (docs/05)."""
        self._undo_new_task = True

    def remember(self, path: Path) -> None:
        """Snapshot ``path`` once per undo window, before write_file / edit_file."""
        if self._undo_new_task:
            self._undo.clear()
            self._undo_new_task = False
        rel = self.relpath(path)
        if rel in self._undo:
            return
        if path.is_file():
            try:
                self._undo[rel] = path.read_bytes()
            except OSError:
                return
            return
        self._undo[rel] = None

    def restore_task_files(self) -> list[str]:
        """Restore write_file / edit_file from the current undo window. Clears it."""
        restored: list[str] = []
        for rel, original in list(self._undo.items()):
            path = self.resolve(rel)
            try:
                if original is None:
                    if path.is_file():
                        path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(original)
            except OSError:
                continue
            restored.append(rel)
            del self._undo[rel]
        return restored
