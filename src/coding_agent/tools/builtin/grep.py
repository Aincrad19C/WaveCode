"""grep: regex search over workspace text files (docs/05 §3.6)."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from coding_agent.errors import ToolError
from coding_agent.tools.base import Tool, ToolContext


class GrepTool(Tool):
    name = "grep"
    description = (
        "Search UTF-8 file contents with a Python regular expression. "
        "Each match is path:line_number:line."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Python regular expression."},
            "path": {
                "type": "string",
                "description": "File or directory to search. Default is the workspace root.",
            },
            "flags": {
                "type": "string",
                "description": "Set to i for case-insensitive matching.",
            },
            "max_matches": {
                "type": "integer",
                "description": "Maximum matches to return. Default 50.",
            },
        },
        "required": ["pattern"],
    }

    def execute(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        flags = re.IGNORECASE if "i" in str(args.get("flags", "")) else 0
        try:
            regex = re.compile(args["pattern"], flags)
        except re.error as exc:
            raise ToolError(f"bad regex: {exc}") from None
        target = ctx.workspace.resolve(args.get("path", "."))
        if not target.exists():
            raise ToolError(f"ENOENT: {args.get('path', '.')}")
        max_matches = max(1, int(args.get("max_matches", 50)))

        matches: list[str] = []
        for path in self._files(target):
            try:
                text = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in text[:8192]:
                continue
            try:
                decoded = text.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for line_no, line in enumerate(decoded.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{ctx.workspace.relpath(path)}:{line_no}:{line}")
                    if len(matches) >= max_matches:
                        return "\n".join(matches) + "\n... (max_matches reached)"
        return "\n".join(matches) if matches else "(no matches)"

    @staticmethod
    def _files(target: Path) -> Iterator[Path]:
        from coding_agent.tools.builtin import IGNORED_DIRS

        if target.is_file():
            yield target
            return
        for path in sorted(target.rglob("*")):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if path.is_file():
                yield path
