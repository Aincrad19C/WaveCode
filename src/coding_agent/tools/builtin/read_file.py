"""read_file (docs/05 §3.1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coding_agent.errors import ToolError
from coding_agent.tools.base import Tool, ToolContext

MAX_LIMIT = 2000
DEFAULT_LIMIT = 400
BIG_FILE_BYTES = 2 * 1024 * 1024


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file from the workspace. Use offset/limit for large files."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace root."},
            "offset": {"type": "integer", "description": "1-based first line to read."},
            "limit": {"type": "integer", "description": "Max lines to read (default 400)."},
        },
        "required": ["path"],
    }

    def execute(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        path = ctx.workspace.resolve(args["path"])
        if not path.exists():
            raise ToolError(f"ENOENT: {args['path']}")
        if path.is_dir():
            raise ToolError(f"EISDIR: {args['path']} is a directory; use list_dir")
        explicit_window = "offset" in args or "limit" in args
        if path.stat().st_size > BIG_FILE_BYTES and not explicit_window:
            raise ToolError(
                f"file is larger than 2MB ({path.stat().st_size} bytes); "
                "pass offset/limit to read a slice"
            )
        raw = path.read_bytes()
        if b"\x00" in raw[:8192]:
            raise ToolError(f"binary file: {args['path']}")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ToolError(f"binary file (not valid UTF-8): {args['path']}") from None

        offset = max(1, int(args.get("offset", 1)))
        limit = min(MAX_LIMIT, max(1, int(args.get("limit", DEFAULT_LIMIT))))
        lines = text.splitlines()
        window = lines[offset - 1 : offset - 1 + limit]
        if not window:
            return f"(no lines in range; file has {len(lines)} lines)"
        body = "\n".join(f"{offset + i:04d}|{line}" for i, line in enumerate(window))
        remaining = len(lines) - (offset - 1 + len(window))
        if remaining > 0:
            body += f"\n... ({remaining} more lines; continue with offset={offset + len(window)})"
        return body
