from __future__ import annotations

from pathlib import Path

import pytest

from fakes.settings import make_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def settings(tmp_path: Path):
    return make_settings(workdir=tmp_path)
