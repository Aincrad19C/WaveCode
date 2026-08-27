"""Blue theme tokens (docs/09 §1)."""

from __future__ import annotations

from rich.theme import Theme

UI_BG = "#0B1220"
UI_PRIMARY = "#3B82F6"
UI_DEEP = "#1D4ED8"
UI_CYAN = "#22D3EE"
UI_ICE = "#93C5FD"
UI_TEXT = "#E2E8F0"
UI_OK = "#34D399"
UI_WARN = "#FBBF24"
UI_ERR = "#F87171"
UI_TOOL = "#60A5FA"

THEME = Theme(
    {
        "prompt": f"bold {UI_PRIMARY}",
        "title": f"bold {UI_PRIMARY}",
        "thinking": f"italic {UI_ICE}",
        "reasoning": f"italic {UI_ICE}",
        "assistant": UI_TEXT,
        "tool": UI_TOOL,
        "success": UI_OK,
        "error": UI_ERR,
        "muted": "dim " + UI_ICE,
        "mascot": UI_CYAN,
        "warn": UI_WARN,
        "user": UI_DEEP,
    }
)
