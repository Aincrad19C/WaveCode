"""Render assistant replies as Markdown in the terminal (Rich Markdown)."""

from __future__ import annotations

from functools import lru_cache
from io import StringIO

from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.text import Text

_CODE_THEME = "ansi_dark"


def assistant_markdown(text: str) -> RenderableType:
    """Turn model output into a Rich renderable. Plain text still looks like text."""
    markup = text or ""
    if not markup.strip():
        return Text("")
    return Markdown(markup, code_theme=_CODE_THEME, hyperlinks=False)


@lru_cache(maxsize=128)
def markdown_line_count(text: str, width: int) -> int:
    """How many terminal rows ``assistant_markdown`` occupies at ``width``."""
    buf = StringIO()
    console = Console(
        file=buf,
        width=max(8, width),
        color_system=None,
        force_terminal=False,
        highlight=False,
        legacy_windows=False,
    )
    console.print(assistant_markdown(text))
    rendered = buf.getvalue()
    if not rendered.strip():
        return 1
    return max(1, rendered.count("\n"))
