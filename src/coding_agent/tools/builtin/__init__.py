"""Built-in tools registered in stable order (docs/05 §5)."""

from __future__ import annotations

from coding_agent.tools.base import Tool
from coding_agent.tools.builtin.bash import BashTool
from coding_agent.tools.builtin.edit_file import EditFileTool
from coding_agent.tools.builtin.glob_search import GlobSearchTool
from coding_agent.tools.builtin.grep import GrepTool
from coding_agent.tools.builtin.list_dir import ListDirTool
from coding_agent.tools.builtin.read_file import ReadFileTool
from coding_agent.tools.builtin.write_file import WriteFileTool

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".wavecode",
        ".wavemio",
        ".coding_agent",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
    }
)


def all_builtin_tools() -> list[Tool]:
    # Schema order influences model preference; keep it deterministic.
    return [
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        ListDirTool(),
        GlobSearchTool(),
        GrepTool(),
        BashTool(),
    ]
