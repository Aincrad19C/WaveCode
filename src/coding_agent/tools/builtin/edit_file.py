"""edit_file: literal, exactly-once replacement (docs/05 §3.3)."""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from typing import Any

from coding_agent.errors import ToolError
from coding_agent.tools.base import Tool, ToolContext


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Replace exactly one occurrence of old_text with new_text in a file. "
        "Matching is literal, not a regular expression. "
        "old_text must occur once; zero or multiple matches fail."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative path."},
            "old_text": {
                "type": "string",
                "description": "Exact text to replace. Must occur once in the file.",
            },
            "new_text": {"type": "string", "description": "Replacement text."},
        },
        "required": ["path", "old_text", "new_text"],
    }

    def execute(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        path = ctx.workspace.resolve(args["path"])
        if not path.is_file():
            raise ToolError(f"ENOENT: {args['path']}")
        old_text: str = args["old_text"]
        new_text: str = args["new_text"]
        if not old_text:
            raise ToolError("old_text must not be empty")
        ctx.workspace.remember(path)
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ToolError(f"binary file: {args['path']}") from None

        count = original.count(old_text)
        if count == 0:
            hint = self._nearby_hint(original, old_text)
            raise ToolError(f"old_text not found in {args['path']}.{hint}")
        if count > 1:
            raise ToolError(f"old_text matched {count} times; make it unique")

        updated = original.replace(old_text, new_text, 1)
        try:
            path.write_text(updated, encoding="utf-8")
        except PermissionError:
            raise ToolError(f"EACCES: {args['path']}") from None

        diff = "\n".join(
            difflib.unified_diff(
                original.splitlines(),
                updated.splitlines(),
                fromfile=args["path"],
                tofile=args["path"],
                lineterm="",
                n=3,
            )
        )
        return f"edited {args['path']}\n{diff}"

    @staticmethod
    def _nearby_hint(original: str, old_text: str) -> str:
        probe = old_text.strip().splitlines()[0][:40] if old_text.strip() else ""
        if not probe:
            return ""
        hits = [
            f"line {no}" for no, line in enumerate(original.splitlines(), 1) if probe in line
        ][:3]
        if hits:
            return f" Lines containing the first 40 chars of old_text: {', '.join(hits)}."
        close = difflib.get_close_matches(probe, original.splitlines(), n=1, cutoff=0.6)
        return f" Did you mean: {close[0]!r}?" if close else ""
