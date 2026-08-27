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
