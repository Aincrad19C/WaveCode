from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from fakes.settings import make_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_workspace_hub() -> Iterator[None]:
    from coding_agent.cli.hub import reset_hub

    reset_hub()
    yield
    reset_hub()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def settings(tmp_path: Path):
    return make_settings(workdir=tmp_path)
