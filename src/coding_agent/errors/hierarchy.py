"""Exception tree per docs/02 §1.

ToolError subclasses raised inside Tool.run are converted by ToolExecutor into a
failed ToolResult and must never escape the agent loop (docs/08).
"""

from __future__ import annotations


class AgentError(Exception):
    """Base for every error this project raises on purpose."""


class ConfigError(AgentError):
    """Bad or missing configuration; abort at startup (exit 2)."""


class CancelledError(AgentError):
    """User cancelled (Ctrl+C or /quit) while the loop was running."""


class LLMError(AgentError):
    """Transport-level failure talking to the model API."""


class LLMAuthError(LLMError):
    """401/403 — never retried."""


class LLMRateLimitError(LLMError):
    """429 — retried with backoff (honouring Retry-After when present)."""

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class LLMTimeoutError(LLMError):
    """Network timeout — retried."""


class LLMUnavailableError(LLMError):
    """5xx or connection failure — retried."""


class LLMBadResponseError(LLMError):
    """HTTP 200 but the JSON body is structurally invalid — not retried."""


class ParseError(AgentError):
    """Model output could not be interpreted."""


class EmptyResponseError(ParseError):
    """Response carried neither content nor tool calls."""


class ToolCallParseError(ParseError):
    """A tool call could not be extracted / repaired."""


class SchemaValidationError(ParseError):
    """Tool arguments failed JSON-schema validation."""


class ToolError(AgentError):
    """Programming-level tool failure; business failures use ToolResult.ok=False."""


class UnknownToolError(ToolError):
    """Model asked for a tool that is not registered."""


class ToolPathError(ToolError):
    """Path escapes the workspace sandbox."""


class ToolTimeoutError(ToolError):
    """Tool exceeded its wall-clock budget."""
