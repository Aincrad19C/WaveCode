"""Ocean palette for the WaveCode CLI (blue sea + foam)."""

from __future__ import annotations

from rich.theme import Theme

# Abyss → horizon → foam. Keep enough contrast on both dark and light terminals.
UI_DEEP = "#0B4F7A"
UI_PRIMARY = "#1A7FBF"
UI_CYAN = "#3EC8E8"
UI_WHITE = "#FFFFFF"
UI_FOAM = "#D7F4FF"
UI_ICE = "#8EC8E6"
UI_TEXT = "#E7F3FA"
UI_OK = "#3DDC97"
UI_WARN = "#F5C15A"
UI_WOOD = "#A0714A"
UI_WOOD_DEEP = "#6B3F24"
UI_ERR = "#FF7B7B"
UI_TOOL = "#5EB5E0"

MODE_COLORS = {
    "ask": UI_ICE,
    "plan": UI_WARN,
    "agent": UI_OK,
}

THEME = Theme(
    {
        "prompt": f"bold {UI_CYAN}",
        "mode.ask": f"bold {UI_ICE}",
        "mode.plan": f"bold {UI_WARN}",
        "mode.agent": f"bold {UI_OK}",
        "title": f"bold {UI_FOAM}",
        "thinking": f"italic {UI_ICE}",
        "reasoning": f"italic {UI_ICE}",
        "assistant": UI_TEXT,
        "tool": UI_TOOL,
        "success": UI_OK,
        "error": UI_ERR,
        "muted": UI_ICE,
        "warn": UI_WARN,
        "user": UI_CYAN,
        "wave": UI_PRIMARY,
        "foam": UI_FOAM,
    }
)
