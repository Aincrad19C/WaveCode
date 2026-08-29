"""System prompt builder (docs/10 §4). Static content only: workspace path,
tool roster, behaviour rules, optional skill catalog. Current file listings
are for list_dir, not the prompt (docs/04 §6)."""

from __future__ import annotations

from collections.abc import Sequence

_TEMPLATE = """You are WaveCode, a local coding agent. You work inside this workspace:
{workspace_root}

You MUST solve programming tasks by calling tools. Available tools:
{tool_names}

Rules:
1. Prefer tools over guessing. Read a file before editing it.
2. Use edit_file for existing files when a unique old_text span exists; use write_file for new files or full rewrites.
3. Use glob_search/grep/list_dir to explore. Do not invent paths.
4. Use bash only inside the workspace. Do not print or request secrets, API keys, or environment variables that look like credentials.
5. After tools succeed, continue until the user task is actually done (tests passing if you can run them).
6. When finished, reply with a concise summary of what changed and how to run it. Do not call tools in that final message.
7. Tool arguments must be a JSON object. Paths are relative to the workspace root.
8. If a tool fails, read the error and recover. Do not claim success without evidence.
9. Match existing project style. Do not add unrelated refactors or extra markdown files unless asked.
10. Never include API keys in files you write."""


def build_system_prompt(
    *,
    workspace_root: str,
    tool_names: Sequence[str],
    skill_catalog: Sequence[tuple[str, str]] = (),
    active_skills: Sequence[tuple[str, str]] = (),
) -> str:
    text = _TEMPLATE.format(workspace_root=workspace_root, tool_names=", ".join(tool_names))
    if skill_catalog:
        lines = [
            "",
            "Available skills, distinct from tools. The user enables them with the /skill picker:",
        ]
        lines.extend(f"- {name}: {desc}" for name, desc in skill_catalog)
        text += "\n" + "\n".join(lines)
    if active_skills:
        parts = ["", "## Active skills"]
        for name, body in active_skills:
            parts.append(f"### {name}\n{body}")
        text += "\n" + "\n".join(parts)
    return text
