"""Visual red/green change view (not a raw git diff dump)."""

from __future__ import annotations

from rich.text import Text

from coding_agent.cli.theme import UI_CYAN, UI_ERR, UI_ICE, UI_OK

_SKIP = (
    "diff --git",
    "index ",
    "old mode",
    "new mode",
    "deleted file",
    "new file",
    "similarity",
    "rename ",
    "copy ",
    "--- ",
    "+++ ",
    "Binary files",
)
_ADD_STYLE = f"bold {UI_OK} on #0F3D2A"
_DEL_STYLE = f"bold {UI_ERR} on #3D1518"
_CTX_STYLE = f"dim {UI_ICE}"
_HUNK_STYLE = f"bold {UI_CYAN}"


def visual_diff_lines(raw: str) -> tuple[Text, ...]:
    """Turn unified diff text into red/green rows; drop git headers."""
    rows: list[Text] = []
    for line in raw.splitlines():
        if line.startswith("@@"):
            label = _hunk_label(line)
            row = Text(" ── " + label + " ", style=_HUNK_STYLE)
            rows.append(row)
            continue
        if any(line.startswith(prefix) for prefix in _SKIP):
            continue
        if line.startswith("+"):
            rows.append(_paint(" + ", line[1:], _ADD_STYLE))
        elif line.startswith("-"):
            rows.append(_paint(" − ", line[1:], _DEL_STYLE))
        elif line.startswith("\\"):
            continue
        else:
            body = line[1:] if line.startswith(" ") else line
            rows.append(_paint("   ", body, _CTX_STYLE))
    if not rows:
        return (Text("（没有可显示的改动）", style="muted"),)
    return tuple(rows)


def _hunk_label(line: str) -> str:
    parts = line.split("@@")
    extra = parts[2].strip() if len(parts) > 2 else ""
    return extra or "改动"


def _paint(prefix: str, body: str, style: str) -> Text:
    row = Text(overflow="crop", no_wrap=True)
    row.append(prefix, style=style)
    row.append(body.replace("\t", "    "), style=style)
    return row
