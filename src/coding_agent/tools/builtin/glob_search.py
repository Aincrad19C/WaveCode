"""glob_search (docs/05 §3.5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coding_agent.errors import ToolError, ToolPathError
from coding_agent.tools.base import Tool, ToolContext


class GlobSearchTool(Tool):
    name = "glob_search"
    description = (
        "Find files by glob pattern relative to the workspace root. Example: **/*.py."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern relative to the workspace root. Example: **/*.py.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum paths to return. Default 200.",
            },
        },
        "required": ["pattern"],
    }

    def execute(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        from coding_agent.tools.builtin import IGNORED_DIRS

        pattern: str = args["pattern"]
        if not pattern.strip():
            raise ToolError("pattern must not be empty")
        max_results = max(1, int(args.get("max_results", 200)))
        root = ctx.workspace.root
        results: list[str] = []
        truncated = False
        try:
            for path in sorted(root.glob(pattern)):
                if any(part in IGNORED_DIRS for part in path.parts):
                    continue
                try:
                    ctx.workspace.resolve(str(path))
                except ToolPathError:
                    continue
                if path.is_file():
                    results.append(ctx.workspace.relpath(path))
                if len(results) >= max_results:
                    truncated = True
                    break
        except (ValueError, NotImplementedError) as exc:
            raise ToolError(f"bad glob pattern: {exc}") from None
        if not results:
            return "(no matches)"
        out = "\n".join(results)
        if truncated:
            out += "\n... (truncated; refine the pattern)"
        return out
