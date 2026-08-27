"""bash: run a shell command inside the workspace (docs/05 §3.7).

The subprocess environment is stripped of anything credential-like so the
model cannot read DEEPSEEK_API_KEY back into its own context via `env`.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
from collections.abc import Mapping
from typing import Any

from coding_agent.errors import ToolError, ToolTimeoutError
from coding_agent.tools.base import Tool, ToolContext

MAX_TIMEOUT_S = 120

_SENSITIVE_KEY_RE = re.compile(r"(?i)(key|token|secret|password|passwd|authorization)$")
_ALWAYS_REMOVE = {"DEEPSEEK_API_KEY"}

# Tiny denylist of obviously catastrophic commands (docs/05: not a full sandbox).
_DENYLIST = ("rm -rf /", "rm -rf /*", "rm -rf ~", "mkfs", "dd if=")


def sanitized_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in _ALWAYS_REMOVE or _SENSITIVE_KEY_RE.search(key):
            continue
        env[key] = value
    return env


class BashTool(Tool):
    name = "bash"
    description = (
        "Run a shell command with cwd at the workspace root. "
        "Returns exit_code, stdout and stderr. Do not leave the workspace."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run."},
            "timeout_s": {"type": "number", "description": "Timeout in seconds (max 120)."},
        },
        "required": ["command"],
    }

    def execute(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        command: str = args["command"].strip()
        if not command:
            raise ToolError("empty command")
        for banned in _DENYLIST:
            if banned in command:
                raise ToolError(f"refused: command contains dangerous pattern {banned!r}")
        timeout = min(MAX_TIMEOUT_S, float(args.get("timeout_s", ctx.timeout_s)))
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(ctx.workspace.root),
                env=sanitized_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
                start_new_session=True,  # own process group so timeout can kill children
            )
        except subprocess.TimeoutExpired as exc:
            self._kill_children(exc)
            raise ToolTimeoutError(f"TIMEOUT after {timeout:g}s: {command}") from None
        return f"exit_code: {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"

    @staticmethod
    def _kill_children(exc: subprocess.TimeoutExpired) -> None:
        # subprocess.run has already killed the direct child; sweep the group.
        pid = getattr(getattr(exc, "process", None), "pid", None)
        if pid is None:
            return
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
