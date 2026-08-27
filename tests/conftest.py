from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.config.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


def make_settings(**overrides) -> Settings:
    """Settings isolated from .env and real credentials."""
    defaults: dict = {
        "deepseek_api_key": "test-key-not-real",
        "workdir": Path("."),
        "max_wallclock_s": 600,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return make_settings(workdir=tmp_path)
