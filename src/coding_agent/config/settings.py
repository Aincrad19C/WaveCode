"""Runtime settings read from environment / .env (docs/02 §10, docs/10 §11).

DeepSeek credentials use explicit aliases (DEEPSEEK_*); every other field uses
the WAVEMIO_ prefix. The api key never appears in repr/str output.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_prefix="WAVEMIO_",
        env_nested_delimiter="__",
    )

    deepseek_api_key: str = Field(default="", validation_alias="DEEPSEEK_API_KEY", repr=False)
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias="DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias="DEEPSEEK_MODEL",
    )

    workdir: Path = Field(default_factory=Path.cwd)
    stream: bool = True
    thinking: bool = False
    reasoning_effort: str = "high"
    temperature: float = 0.2
    max_tokens: int = 4096
    max_turns: int = 30
    max_consecutive_failures: int = 3
    max_wallclock_s: float = 600
    max_context_tokens: int = 32000
    completion_reserve_tokens: int = 4096
    tool_output_max_chars: int = 80_000
    bash_timeout_s: float = 60
    http_timeout_s: float = 120
    parallel_readonly_tools: bool = False
    log_dir: Path = Path(".wavemio/logs")
    ascii_fallback: bool = Field(default=False, validation_alias="WAVEMIO_ASCII")
    debug: bool = False

    def __str__(self) -> str:  # never leak the key
        return f"Settings(model={self.deepseek_model}, workdir={self.workdir})"
