from __future__ import annotations

import subprocess
import sys

import pytest

import coding_agent
from coding_agent.cli.app import main
from coding_agent.cli.branding import CLI_NAME, PRODUCT_NAME


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exited:
        main(["--help"])
    assert exited.value.code == 0


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["--version"])
    assert exited.value.code == 0
    assert capsys.readouterr().out.strip() == f"{CLI_NAME} {coding_agent.__version__}"


def test_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert PRODUCT_NAME in output
    assert CLI_NAME in output


def test_console_script_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "coding_agent", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == f"{CLI_NAME} {coding_agent.__version__}"
