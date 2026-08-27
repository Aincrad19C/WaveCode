"""Test Settings factory. Keep this out of conftest so unit tests can import
it without needing the `tests` package on sys.path (GitHub Actions)."""

from __future__ import annotations

from pathlib import Path

from coding_agent.config.settings import Settings


def make_settings(**overrides) -> Settings:
    """Settings isolated from .env and real credentials."""
    defaults: dict = {
        "deepseek_api_key": "test-key-not-real",
        "workdir": Path("."),
        "max_wallclock_s": 600,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)
