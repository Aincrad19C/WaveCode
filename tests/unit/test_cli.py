from __future__ import annotations

import subprocess
import sys

import pytest

import coding_agent
from coding_agent.cli.app import EXIT_CONFIG, main
from coding_agent.cli.branding import CLI_NAME, PRODUCT_NAME


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["--help"])
    assert exited.value.code == 0
    output = capsys.readouterr().out
    assert PRODUCT_NAME in output
    assert CLI_NAME in output


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["--version"])
    assert exited.value.code == 0
    assert capsys.readouterr().out.strip() == f"{CLI_NAME} {coding_agent.__version__}"


def test_missing_api_key_exits_2_without_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.chdir(tmp_path)  # no .env around
    code = main(["run", "hello"])
    assert code == EXIT_CONFIG
    output = capsys.readouterr().out
    assert "DEEPSEEK_API_KEY" in output
    assert "Traceback" not in output


def test_console_script_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "coding_agent", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == f"{CLI_NAME} {coding_agent.__version__}"


def test_socks_env_proxy_does_not_crash_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coding_agent.app.bootstrap import build_http_client

    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897/")
    monkeypatch.setenv("all_proxy", "socks://127.0.0.1:7897/")
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    client = build_http_client(5.0)
    try:
        assert client is not None
    finally:
        client.close()


def test_describe_tool_is_short_activity() -> None:
    from coding_agent.cli.renderer import describe_tool
    from coding_agent.domain.messages import ToolCallRequest

    assert describe_tool(ToolCallRequest("1", "read_file", '{"path": "a.py"}')) == "Read a.py"
    assert describe_tool(ToolCallRequest("1", "bash", '{"command": "ls -l"}')) == "Bash ls -l"


def test_sink_hides_reasoning_and_streams_final_only() -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.renderer import RichEventSink
    from coding_agent.domain.events import ContentDelta, FinalAnswer, ReasoningDelta

    buf = StringIO()
    sink = RichEventSink(Console(file=buf, force_terminal=False, width=80, color_system=None))
    sink.on_event(ReasoningDelta(text="secret chain of thought"))
    sink.on_event(ContentDelta(text="partial token"))
    sink.on_event(FinalAnswer(text="任务完成。", reason="natural"))
    out = buf.getvalue()
    assert "secret chain of thought" not in out
    assert "partial token" not in out
    assert "任务完成。" in out
    assert PRODUCT_NAME in out
