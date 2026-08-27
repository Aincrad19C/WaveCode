"""write_file (docs/05 §3.2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coding_agent.errors import ToolError
from coding_agent.tools.base import Tool, ToolContext


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create or overwrite a UTF-8 file. Always overwrites. Parent dirs are created."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace root."},
            "content": {"type": "string", "description": "Full file content."},
        },
        "required": ["path", "content"],
    }

    def execute(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        path = ctx.workspace.resolve(args["path"])
        content: str = args["content"]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode("utf-8")
            path.write_bytes(data)
        except PermissionError:
            raise ToolError(f"EACCES: {args['path']}") from None
        except OSError as exc:
            raise ToolError(f"write failed: {exc}") from None
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"wrote {ctx.workspace.relpath(path)} ({len(data)} bytes, {lines} lines)"
