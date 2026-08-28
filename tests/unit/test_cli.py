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


def test_wave_strip_is_ocean_band() -> None:
    from coding_agent.cli.chrome import wave_strip

    strip = wave_strip(24)
    assert len(strip.plain) == 24
    assert set("▁▂▃▄▅▆▇") & set(strip.plain)


def test_ocean_banner_prints_wavemio() -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.chrome import ocean_banner

    buf = StringIO()
    ocean_banner(
        Console(file=buf, force_terminal=False, width=80, color_system=None),
        version="1.3.0",
    )
    out = buf.getvalue()
    assert PRODUCT_NAME in out
    assert "DeepSeek" in out
    assert "已就绪" in out
    assert "鲸鱼娘" not in out


def test_tui_sink_hides_reasoning_and_keeps_activity() -> None:
    from coding_agent.cli.renderer import TuiEventSink, describe_tool
    from coding_agent.cli.view import ChatView
    from coding_agent.domain.events import (
        ContentDelta,
        FinalAnswer,
        ReasoningDelta,
        ToolCallScheduled,
        ToolExecutionFinished,
        UserMessageAccepted,
    )
    from coding_agent.domain.messages import ToolCallRequest
    from coding_agent.domain.results import ToolResult

    view = ChatView()
    sink = TuiEventSink(view)
    sink.on_event(UserMessageAccepted(text="列出文件"))
    sink.on_event(ReasoningDelta(text="secret chain of thought"))
    sink.on_event(ContentDelta(text="partial token"))
    call = ToolCallRequest("1", "list_dir", '{"path": "."}')
    sink.on_event(ToolCallScheduled(call=call))
    sink.on_event(
        ToolExecutionFinished(result=ToolResult("1", "list_dir", True, "ok", {}))
    )
    sink.on_event(FinalAnswer(text="当前目录是空的。", reason="natural"))
    snap = view.snapshot()
    blob = "\n".join(item.text for item in snap.items)
    assert "secret chain of thought" not in blob
    assert "partial token" not in blob
    assert "列出文件" in blob
    assert "当前目录是空的。" in blob
    assert describe_tool(call) in blob
    assert snap.status == ""
    assert snap.busy is False


def test_tui_frame_fills_terminal_like_top() -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.branding import GLYPH_WAVE
    from coding_agent.cli.chrome import WorkspaceChrome
    from coding_agent.cli.tui import render_frame
    from coding_agent.cli.view import ChatView

    view = ChatView()
    view.append("user", "列出文件")
    view.append("tool", "List .", ok=True)
    view.append("assistant", "当前目录是空的。")
    view.set_input("hello█")
    chrome = WorkspaceChrome(
        workdir="/tmp/wavemio-proj",
        model="deepseek-v4-flash",
        turn=2,
        max_turns=30,
        tokens=1200,
        max_tokens=32000,
        git_branch="main",
        version="2.1.0",
    )
    buf = StringIO()
    console = Console(
        file=buf,
        width=80,
        height=24,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(render_frame(view, chrome=chrome))
    out = console.export_text()
    assert PRODUCT_NAME in out
    assert "吉祥物" in out
    assert "预留" in out
    assert "工作区" in out
    assert "对话" in out
    assert "目录" in out
    assert "deepseek-v4-flash" in out
    assert "列出文件" in out
    assert "当前目录是空的。" in out
    assert "List ." in out
    assert f"{GLYPH_WAVE} wavemio ›" in out
    assert "已就绪" in out
    assert "鲸鱼娘" not in out


def test_line_editor_submit_utf8_history_and_continue() -> None:
    from coding_agent.cli.editor import LineEditor

    editor = LineEditor()
    actions = editor.feed("你好".encode() + b"\r")
    assert [(a.kind, a.text) for a in actions] == [("submit", "你好")]

    editor.feed(b"abc\\\r")
    assert "\n" in editor.buffer
    actions = editor.feed(b"def\r")
    assert actions[0].kind == "submit"
    assert actions[0].text == "abc\ndef"

    editor.feed(b"\x1b[A")
    assert editor.buffer == "abc\ndef"
    editor.feed(b"\x1b[A")
    assert editor.buffer == "你好"


def test_line_editor_page_keys_and_backspace() -> None:
    from coding_agent.cli.editor import LineEditor

    editor = LineEditor()
    editor.feed(b"ab")
    editor.feed(b"\x7f")
    assert editor.buffer == "a"
    actions = editor.feed(b"\x1b[5~")
    assert actions[0].kind == "page_up"
    actions = editor.feed(b"\x03")
    assert actions[0].kind == "interrupt"


def test_dispatch_slash_help_and_quit() -> None:
    from coding_agent.cli.commands import dispatch_slash
    from fakes.settings import make_settings

    settings = make_settings()
    dummy = object()
    assert dispatch_slash("/q", dummy, settings).quit is True  # type: ignore[arg-type]
    help_out = dispatch_slash("/help", dummy, settings)  # type: ignore[arg-type]
    assert help_out.kind == "help"
    assert "/reset" in help_out.body
    unknown = dispatch_slash("/nope", dummy, settings)  # type: ignore[arg-type]
    assert unknown.kind == "warn"


def test_wave_strip_phase_rolls() -> None:
    from coding_agent.cli.chrome import wave_strip

    a = wave_strip(16, phase=0).plain
    b = wave_strip(16, phase=3).plain
    assert a != b
    assert len(a) == len(b) == 16


def test_workspace_path_and_git_branch(tmp_path) -> None:
    from pathlib import Path

    from coding_agent.cli.chrome import detect_git_branch, short_home_path, usage_bar

    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert detect_git_branch(tmp_path) == "main"
    assert detect_git_branch(tmp_path / "nope") == ""
    assert usage_bar(0, 100, 10) == "░" * 10
    assert "█" in usage_bar(50, 100, 10)
    home = Path.home()
    assert short_home_path(home) == "~"
    assert short_home_path(home / "proj").startswith("~/")


def test_ocean_frame_directory_follows_bash_cwd(tmp_path) -> None:
    from types import SimpleNamespace

    from coding_agent.agent.state import LoopState
    from coding_agent.cli.tui import OceanFrame
    from coding_agent.cli.view import ChatView
    from coding_agent.tools.workspace import Workspace
    from fakes.settings import make_settings

    workspace = Workspace(tmp_path)
    parent = tmp_path.resolve().parent
    workspace.cwd = parent
    session = SimpleNamespace(
        loop=SimpleNamespace(
            state=LoopState(),
            executor=SimpleNamespace(workspace=workspace),
        )
    )
    frame = OceanFrame(
        ChatView(),
        session=session,  # type: ignore[arg-type]
        settings=make_settings(workdir=tmp_path),
    )
    assert frame._live_chrome().workdir == str(parent)


def test_tui_interrupt_at_idle_prompt_quits() -> None:
    from types import SimpleNamespace

    from coding_agent.agent.state import LoopState
    from coding_agent.cli.editor import KeyAction, LineEditor
    from coding_agent.cli.tui import OceanTui
    from coding_agent.cli.view import ChatView
    from fakes.settings import make_settings

    view = ChatView()
    session = SimpleNamespace(loop=SimpleNamespace(state=LoopState()), reset=lambda: None)
    tui = OceanTui(session, None, make_settings(), view)  # type: ignore[arg-type]
    editor = LineEditor()
    assert tui._apply([KeyAction("interrupt")], editor) == "quit"


def test_dispatch_slash_tools_status_think_reset() -> None:
    from types import SimpleNamespace

    from coding_agent.agent.state import LoopState
    from coding_agent.cli.commands import dispatch_slash
    from fakes.settings import make_settings

    settings = make_settings()
    reset_called: list[bool] = []
    session = SimpleNamespace(
        reset=lambda: reset_called.append(True),
        loop=SimpleNamespace(
            state=LoopState(),
            settings=settings,
            registry=SimpleNamespace(
                schemas=lambda: [{"function": {"name": "bash", "description": "run a command"}}]
            ),
        ),
    )
    assert dispatch_slash("/reset", session, settings).body.startswith("对话已清空")
    assert reset_called
    assert dispatch_slash("/think", session, settings).kind == "warn"
    assert "bash" in dispatch_slash("/tools", session, settings).body
    assert "工作区" in dispatch_slash("/status", session, settings).body
    note = dispatch_slash("/think on", session, settings)
    assert note.body == "thinking = on"
    assert settings.thinking is True


def test_tui_slash_help_and_submit_ask() -> None:
    from types import SimpleNamespace

    from coding_agent.agent.state import LoopState
    from coding_agent.cli.tui import OceanTui
    from coding_agent.cli.view import ChatView
    from fakes.settings import make_settings

    view = ChatView()
    asked: list[str] = []
    settings = make_settings()
    session = SimpleNamespace(
        loop=SimpleNamespace(state=LoopState(), settings=settings),
        ask=lambda text: asked.append(text),
        reset=lambda: None,
    )
    tui = OceanTui(session, None, settings, view)  # type: ignore[arg-type]
    assert tui._slash("/help") is False
    assert view.snapshot().items[-1].kind == "help"
    assert tui._slash("/quit") is True
    assert tui._submit("写一个 hello.py") is False
    assert tui._worker is not None
    tui._worker.join(timeout=1)
    assert asked == ["写一个 hello.py"]
    assert view.snapshot().busy is False


def test_input_viewport_wraps_and_follows_cursor() -> None:
    from coding_agent.cli.tui import _INPUT_MAX_BODY, _input_viewport, _thumb_bar, _wrap_cells
    from coding_agent.cli.view import ChatView

    view = ChatView()
    view.set_input("hi█")
    lines, hint = _input_viewport(view.snapshot(), 40)
    assert hint == ""
    assert any("hi█" in line for line in lines)

    wrapped = _wrap_cells("你好世界", 4)
    assert wrapped == ["你好", "世界"]
    assert _thumb_bar(0, 6, 6, 8) == "█" * 8
    assert _thumb_bar(8, 2, 10, 8).endswith("██")

    long = "x" * 200
    view.set_input("█" + long)
    lines, hint = _input_viewport(view.snapshot(), 20)
    assert "█" in lines[0]
    assert "↓" in hint
    assert "↑" not in hint
    assert f"1-{_INPUT_MAX_BODY}/" in hint.replace(" ", "")

    view.set_input(long + "█")
    lines, hint = _input_viewport(view.snapshot(), 20)
    assert lines[-1].endswith("█")
    assert "↑" in hint
    assert "↓" not in hint


def test_input_bar_grows_and_shows_scrollbar_in_frame() -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.chrome import WorkspaceChrome
    from coding_agent.cli.tui import render_frame
    from coding_agent.cli.view import ChatView

    view = ChatView()
    view.set_input(("w" * 90) + "█")
    chrome = WorkspaceChrome(version="2.3.0")
    buf = StringIO()
    console = Console(
        file=buf,
        width=40,
        height=24,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(render_frame(view, chrome=chrome, width=40))
    out = console.export_text()
    assert out.count("w") >= 90
    assert "wavemio ›" in out

    view.set_input(("w" * 500) + "█")
    console.print(render_frame(view, chrome=chrome, width=40))
    long_out = console.export_text()
    assert "↑" in long_out
    assert "/" in long_out


def test_chat_view_scroll_and_clear() -> None:
    from coding_agent.cli.view import ChatView

    view = ChatView()
    view.append("user", "a")
    view.append("assistant", "b")
    view.append("note", "c")
    view.scroll_up(2)
    assert view.snapshot().scroll == 2
    view.scroll_down(1)
    assert view.snapshot().scroll == 1
    view.scroll_bottom()
    assert view.snapshot().scroll == 0
    view.clear()
    assert view.snapshot().items == ()


def test_tui_interrupt_while_busy_cancels() -> None:
    from types import SimpleNamespace

    from coding_agent.agent.state import LoopState
    from coding_agent.cli.editor import KeyAction, LineEditor
    from coding_agent.cli.tui import OceanTui
    from coding_agent.cli.view import ChatView
    from fakes.settings import make_settings

    view = ChatView()
    view.set_busy(True)
    state = LoopState()
    session = SimpleNamespace(loop=SimpleNamespace(state=state), reset=lambda: None)
    tui = OceanTui(session, None, make_settings(), view)  # type: ignore[arg-type]
    editor = LineEditor()
    assert tui._apply([KeyAction("interrupt")], editor) is None
    assert state.cancelled is True
    assert any("已取消" in item.text for item in view.snapshot().items)

