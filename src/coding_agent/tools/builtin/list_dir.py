"""list_dir: single level, dirs first (docs/05 §3.4)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coding_agent.errors import ToolError
from coding_agent.tools.base import Tool, ToolContext


class ListDirTool(Tool):
    name = "list_dir"
    description = (
        "List a single directory. Each line is d followed by a subdirectory name, "
        "or f followed by a file name. Directories appear first, then files, both sorted by name."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path relative to the workspace root.",
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum entries to return. Default 200.",
            },
        },
        "required": [],
    }

    def execute(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        path = ctx.workspace.resolve(args.get("path", "."))
        if not path.exists():
            raise ToolError(f"ENOENT: {args.get('path', '.')}")
        if not path.is_dir():
            raise ToolError(f"ENOTDIR: {args.get('path', '.')} is a file; use read_file")
        max_entries = max(1, int(args.get("max_entries", 200)))
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            raise ToolError(f"EACCES: {args.get('path', '.')}") from None
        lines = [f"{'d' if entry.is_dir() else 'f'} {entry.name}" for entry in entries]
        if len(lines) > max_entries:
            extra = len(lines) - max_entries
            lines = lines[:max_entries] + [f"... and {extra} more"]
        return "\n".join(lines) if lines else "(empty directory)"
