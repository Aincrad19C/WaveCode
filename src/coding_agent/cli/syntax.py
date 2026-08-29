"""Language-aware source coloring plus rainbow brackets."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text

from coding_agent.cli.theme import UI_CYAN, UI_FOAM, UI_ICE, UI_OK, UI_WARN

_RAINBOW = (
    "#FF6B9D",
    "#F5C15A",
    "#3DDC97",
    "#3EC8E8",
    "#7AA2FF",
    "#C678DD",
)
_OPEN = frozenset("([{")
_CLOSE = {")": "(", "]": "[", "}": "{"}
_LEXERS = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".json": "json",
    ".jsonl": "json",
    ".toml": "toml",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".xml": "xml",
    ".lua": "lua",
    ".r": "r",
    ".jl": "julia",
}


def lexer_name(rel: str) -> str:
    return _LEXERS.get(Path(rel).suffix.lower(), "")


def style_source(rel: str, text: str) -> tuple[Text, ...]:
    """Color a source file: pygments tokens when possible, plus rainbow brackets."""
    lines = text.splitlines() or [""]
    name = lexer_name(rel)
    if name:
        styled = _pygments_lines(text, name)
        if styled is not None:
            return _rainbow_brackets(styled)
    return _rainbow_brackets(tuple(Text(line, style=UI_FOAM) for line in lines))


def _pygments_lines(text: str, name: str) -> tuple[Text, ...] | None:
    try:
        from pygments import lex
        from pygments.lexers import get_lexer_by_name
        from pygments.util import ClassNotFound
    except ImportError:
        return None
    try:
        lexer = get_lexer_by_name(name, stripnl=False)
    except ClassNotFound:
        return None
    rows = [Text(overflow="crop", no_wrap=True)]
    for ttype, value in lex(text, lexer):
        style = _token_style(str(ttype))
        chunks = value.split("\n")
        for i, chunk in enumerate(chunks):
            if i:
                rows.append(Text(overflow="crop", no_wrap=True))
            if chunk:
                rows[-1].append(chunk.replace("\t", "    "), style=style)
    if text.endswith("\n") and rows and rows[-1].plain == "":
        rows.pop()
    return tuple(rows or [Text()])


def _token_style(ttype: str) -> str:
    if "Comment" in ttype:
        return f"italic dim {UI_ICE}"
    if "String" in ttype:
        return UI_OK
    if "Keyword" in ttype:
        return f"bold {UI_CYAN}"
    if "Name.Function" in ttype:
        return "bold #7AA2FF"
    if "Name.Class" in ttype:
        return f"bold {UI_WARN}"
    if "Number" in ttype:
        return "#F5C15A"
    if "Operator" in ttype or "Punctuation" in ttype:
        return UI_FOAM
    if "Name.Builtin" in ttype or "Name.Decorator" in ttype:
        return "#C678DD"
    if "Name" in ttype:
        return UI_FOAM
    return UI_FOAM


def _rainbow_brackets(rows: tuple[Text, ...]) -> tuple[Text, ...]:
    depth = 0
    out: list[Text] = []
    for row in rows:
        plain = row.plain
        if not any(ch in _OPEN or ch in _CLOSE for ch in plain):
            out.append(row)
            continue
        rebuilt = Text(overflow="crop", no_wrap=True)
        colors = _span_colors(row)
        for i, ch in enumerate(plain):
            if ch in _OPEN:
                color = _RAINBOW[depth % len(_RAINBOW)]
                depth += 1
                rebuilt.append(ch, style=f"bold {color}")
            elif ch in _CLOSE:
                depth = max(0, depth - 1)
                color = _RAINBOW[depth % len(_RAINBOW)]
                rebuilt.append(ch, style=f"bold {color}")
            else:
                rebuilt.append(ch, style=colors[i] if i < len(colors) else UI_FOAM)
        out.append(rebuilt)
    return tuple(out)


def _span_colors(row: Text) -> list[str]:
    n = len(row.plain)
    colors = [UI_FOAM] * n
    for span in row.spans:
        tag = str(span.style) if span.style is not None else UI_FOAM
        for i in range(max(0, span.start), min(n, span.end)):
            colors[i] = tag
    return colors
