"""Conservative JSON repair for tool arguments (docs/06 §6).

Handles markdown fences, trailing commas, Python literals and (very
conservatively) single-quoted objects. Never evaluates code.
"""

from __future__ import annotations

import json
import re

from coding_agent.errors import ToolCallParseError

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_PY_LITERALS = ((re.compile(r"\bTrue\b"), "true"), (re.compile(r"\bFalse\b"), "false"),
                (re.compile(r"\bNone\b"), "null"))


def repair_json_object(text: str) -> str:
    """Return a string that parses as a JSON object, or raise ToolCallParseError."""
    candidate = _FENCE_RE.sub("", text.strip()).strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        candidate = candidate[start : end + 1]
    # Single -> double quotes only when it clearly is single-quoted JSON.
    if "'" in candidate and '"' not in candidate:
        candidate = candidate.replace("'", '"')
    for pattern, replacement in _PY_LITERALS:
        candidate = pattern.sub(replacement, candidate)
    candidate = _TRAILING_COMMA_RE.sub(r"\1", candidate)
    try:
        json.loads(candidate)
    except ValueError as exc:
        raise ToolCallParseError(f"cannot repair arguments JSON: {exc}") from exc
    return candidate
