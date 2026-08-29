from __future__ import annotations

import subprocess
import sys

import pytest

import coding_agent
from coding_agent.cli.app import EXIT_CONFIG, main
from coding_agent.cli.branding import CLI_NAME, PRODUCT_NAME, TAGLINE


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
    assert "✦" not in strip.plain
    assert "✧" not in strip.plain
    styles = " ".join(str(span.style) for span in strip.spans).lower()
    assert "#ffffff" in styles
    assert "#3ec8e8" in styles
    assert "#d7f4ff" not in styles
    white_cells = sum(
        span.end - span.start
        for span in strip.spans
        if span.style and "#ffffff" in str(span.style).lower()
    )
    assert 1 <= white_cells <= 3


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
    assert "DeepSeek" not in out
    assert TAGLINE in out
    assert "已就绪" in out
    assert "鲸鱼娘" not in out
    assert "✦" not in out


def test_boot_panel_boat_draws_channel() -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.boot import boot_panel

    buf = StringIO()
    console = Console(
        file=buf,
        width=80,
        height=24,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(boot_panel(80, 24, 0.55))
    out = console.export_text()
    assert PRODUCT_NAME in out
    assert "DeepSeek" not in out
    assert TAGLINE in out
    assert "┏" in out
    assert "█" in out
    assert set("▁▂▃▄▅▆▇") & set(out)
    sailing = boot_panel(80, 24, 0.55)
    wooded = [
        span
        for span in sailing.renderable.spans
        if span.style and "#a0714a" in str(span.style).lower()
    ]
    hull = [
        span
        for span in sailing.renderable.spans
        if span.style and "#6b3f24" in str(span.style).lower()
    ]
    sail = [
        span
        for span in sailing.renderable.spans
        if span.style
        and "#ffffff" in str(span.style).lower()
        and "on #" not in str(span.style).lower()
    ]
    assert wooded
    assert hull
    assert sail
    mark = boot_panel(80, 24, 0.85)
    inked = [
        span
        for span in mark.renderable.spans
        if span.style
        and "#ffffff" in str(span.style).lower()
        and "on #" in str(span.style).lower()
    ]
    assert inked
    foam = [
        span
        for span in sailing.renderable.spans
        if span.style
        and "#ffffff" in str(span.style).lower()
        and "on #" not in str(span.style).lower()
    ]
    assert foam
    early_buf = StringIO()
    early = Console(
        file=early_buf,
        width=80,
        height=24,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    early.print(boot_panel(80, 24, 0.05))
    assert PRODUCT_NAME not in early.export_text()


def test_boot_sea_whitecaps_are_sparse() -> None:
    from coding_agent.cli.boot import boot_panel

    panel = boot_panel(80, 24, 0.05)
    white = 0
    total = 0
    foam = 0
    for span in panel.renderable.spans:
        if not span.style:
            continue
        style = str(span.style).lower()
        n = span.end - span.start
        total += n
        if "#ffffff" in style and "on #" not in style:
            white += n
        if "#d7f4ff" in style:
            foam += n
    assert total > 400
    assert foam == 0
    assert white < total // 25


def test_ocean_frame_skip_boot_shows_workspace() -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.tui import OceanFrame
    from coding_agent.cli.view import ChatView

    view = ChatView()
    frame = OceanFrame(view, boot_started=0.0)
    buf = StringIO()
    console = Console(
        file=buf,
        width=80,
        height=24,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(frame)
    assert PRODUCT_NAME in console.export_text()
    frame.skip_boot()
    buf2 = StringIO()
    console2 = Console(
        file=buf2,
        width=80,
        height=24,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console2.print(frame)
    out = console2.export_text()
    assert "工作区" in out
    assert "✦" not in out


def test_reveal_from_left_uncovers_workspace() -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.boot import boot_panel, reveal_from_left
    from coding_agent.cli.tui import render_frame
    from coding_agent.cli.view import ChatView

    view = ChatView()
    main = render_frame(view, width=80)
    cover = boot_panel(80, 24, 1.0)

    def paint(t: float) -> str:
        buf = StringIO()
        console = Console(
            file=buf,
            width=80,
            height=24,
            force_terminal=True,
            color_system=None,
            record=True,
        )
        console.print(reveal_from_left(main, cover, t))
        return console.export_text()

    start = paint(0.0)
    assert "工作区" not in start
    assert PRODUCT_NAME in start
    assert set("▁▂▃▄▅▆▇") & set(start)
    done = paint(1.0)
    assert "工作区" in done
    assert "对话" in done
    mid = paint(0.45)
    assert "▓" in mid or "▒" in mid


def test_ocean_frame_holds_splash_until_reveal_finishes() -> None:
    import time
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.boot import BOOT_DURATION_S
    from coding_agent.cli.tui import OceanFrame
    from coding_agent.cli.view import ChatView

    view = ChatView()
    frame = OceanFrame(view, boot_started=time.monotonic() - BOOT_DURATION_S - 0.05)
    buf = StringIO()
    console = Console(
        file=buf,
        width=80,
        height=24,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(frame)
    out = console.export_text()
    assert PRODUCT_NAME in out
    assert "█" in out or set("▁▂▃▄▅▆▇") & set(out)




def test_tui_sink_hides_reasoning_and_keeps_activity() -> None:
    from coding_agent.cli.renderer import TuiEventSink, describe_tool
    from coding_agent.cli.sidebar import reset_sidebar
    from coding_agent.cli.sprites.bank import reset_bank
    from coding_agent.cli.view import ChatView
    from coding_agent.domain.events import (
        ContentDelta,
        FinalAnswer,
        LLMRequestStarted,
        ReasoningDelta,
        ToolCallScheduled,
        ToolExecutionFinished,
        UserMessageAccepted,
    )
    from coding_agent.domain.messages import ToolCallRequest
    from coding_agent.domain.results import ToolResult

    view = ChatView()
    sink = TuiEventSink(view)
    bank = reset_bank()
    reset_sidebar()
    assert bank.pose == "idle"
    sink.on_event(UserMessageAccepted(text="列出文件"))
    assert bank.pose == "think"
    sink.on_event(ReasoningDelta(text="secret chain of thought"))
    sink.on_event(ContentDelta(text="partial token"))
    call = ToolCallRequest("1", "list_dir", '{"path": "."}')
    sink.on_event(ToolCallScheduled(call=call))
    assert bank.pose == "tool"
    sink.on_event(LLMRequestStarted())
    assert bank.pose == "tool"
    sink.on_event(
        ToolExecutionFinished(result=ToolResult("1", "list_dir", True, "ok", {}))
    )
    assert bank.pose == "tool"
    sink.on_event(FinalAnswer(text="当前目录是空的。", reason="natural"))
    assert bank.pose == "idle"
    snap = view.snapshot()
    blob = "\n".join(item.text for item in snap.items)
    assert "secret chain of thought" not in blob
    assert "partial token" not in blob
    assert "列出文件" in blob
    assert "当前目录是空的。" in blob
    assert describe_tool(call) in blob
    assert snap.status == ""
    assert snap.busy is False


def test_tui_sink_records_write_in_changes() -> None:
    from coding_agent.cli.renderer import TuiEventSink
    from coding_agent.cli.sidebar import get_sidebar, reset_sidebar
    from coding_agent.cli.sprites.bank import reset_bank
    from coding_agent.cli.view import ChatView
    from coding_agent.domain.events import (
        ToolCallScheduled,
        ToolExecutionFinished,
        UserMessageAccepted,
    )
    from coding_agent.domain.messages import ToolCallRequest
    from coding_agent.domain.results import ToolResult

    reset_bank()
    reset_sidebar()
    sink = TuiEventSink(ChatView())
    sink.on_event(UserMessageAccepted(text="写一个 hello.py"))
    call = ToolCallRequest("1", "write_file", '{"path": "hello.py", "content": "x"}')
    sink.on_event(ToolCallScheduled(call=call))
    sink.on_event(
        ToolExecutionFinished(result=ToolResult("1", "write_file", True, "wrote hello.py", {}))
    )
    changes = get_sidebar().changes()
    assert any(item.path == "hello.py" and item.code == "A" for item in changes)


def test_tui_frame_fills_terminal_like_top() -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.branding import GLYPH_WAVE
    from coding_agent.cli.chrome import WorkspaceChrome
    from coding_agent.cli.sidebar import reset_sidebar
    from coding_agent.cli.sprites.bank import reset_bank
    from coding_agent.cli.tui import render_frame
    from coding_agent.cli.view import ChatView

    reset_bank()
    reset_sidebar()
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
        height=32,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(render_frame(view, chrome=chrome))
    out = console.export_text()
    assert PRODUCT_NAME in out
    assert "吉祥物" not in out
    assert "预留" not in out
    assert "工作区" in out
    assert "对话" in out
    assert "文本" in out
    assert "终端" not in out
    assert "文件" in out
    assert "Changes" in out
    assert "输入" in out
    assert "你" in out
    assert "wavemio-proj" in out
    assert "deepseek-v4-flash" in out
    assert "列出文件" in out
    assert "当前目录是空的。" in out
    assert "List ." in out
    assert f"{GLYPH_WAVE} {CLI_NAME} ›" in out
    assert "已就绪" in out
    assert "DeepSeek" not in out
    assert "目录" in out
    assert "模型" in out
    assert "thinking" in out
    assert "流式" in out
    assert "轮次" in out
    assert "✦" not in out
    assert "✧" not in out
    assert "╭" in out
    assert "┌" in out
    assert "┏" in out
    assert "╔" in out
    assert "╚" in out
    assert "╝" in out
    for banned in ("鲸鱼娘", "鲸鱼酿", "像素鲸鱼娘"):
        assert banned not in out


def test_file_change_rail_splits_one_to_one(tmp_path) -> None:
    from io import StringIO

    from rich.console import Console
    from rich.layout import Layout

    from coding_agent.cli.sidebar import reset_sidebar
    from coding_agent.cli.tui import _FileChangeRail, file_change_heights

    assert file_change_heights(20) == (10, 10)
    assert file_change_heights(21) == (11, 10)
    assert file_change_heights(2) == (1, 1)

    reset_sidebar()
    height = 20
    console = Console(
        file=StringIO(),
        width=28,
        height=height,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    frame = Layout(size=height)
    frame.update(_FileChangeRail(str(tmp_path)))
    console.print(frame)
    lines = console.export_text().splitlines()
    files_at = next(i for i, line in enumerate(lines) if "文件" in line)
    changes_at = next(i for i, line in enumerate(lines) if "Changes" in line)
    assert changes_at - files_at == height // 2


def test_tui_file_pane_lists_workspace_below_portrait(tmp_path) -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.chrome import WorkspaceChrome
    from coding_agent.cli.sidebar import reset_sidebar
    from coding_agent.cli.sprites.bank import reset_bank
    from coding_agent.cli.tui import render_frame
    from coding_agent.cli.view import ChatView

    (tmp_path / "alpha.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "beta.py").write_text("b\n", encoding="utf-8")
    reset_bank()
    reset_sidebar()
    chrome = WorkspaceChrome(workdir=str(tmp_path), root=str(tmp_path), version="2.7.0")
    buf = StringIO()
    console = Console(
        file=buf,
        width=80,
        height=40,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(render_frame(ChatView(), chrome=chrome, width=80))
    out = console.export_text()
    assert "文件" in out
    assert "alpha.py" in out
    assert "pkg/" in out
    assert "beta.py" not in out
    assert "Changes" in out
    assert "（无）" in out
    assert "对话" in out
    assert "文本" in out
    assert "终端" not in out
    assert out.count("在下方输入任务") == 1
    assert "Enter 发送" in out


def test_tui_text_tab_shows_file_contents(tmp_path) -> None:
    from io import StringIO

    from rich.console import Console

    from coding_agent.cli.chrome import WorkspaceChrome
    from coding_agent.cli.hub import get_hub
    from coding_agent.cli.tui import render_frame
    from coding_agent.cli.view import ChatView

    (tmp_path / "note.md").write_text("alpha-line\nbeta-line\n", encoding="utf-8")
    hub = get_hub()
    assert hub.open_file(tmp_path, "note.md") == ""
    buf = StringIO()
    console = Console(
        file=buf,
        width=80,
        height=32,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(render_frame(ChatView(), chrome=WorkspaceChrome(version="2.9.0"), width=80))
    out = console.export_text()
    assert "alpha-line" in out
    assert "note.md" in out
    hub.cycle_tab()
    console.print(render_frame(ChatView(), chrome=WorkspaceChrome(version="2.10.0"), width=80))
    chat_out = console.export_text()
    assert "对话" in chat_out
    assert "终端" not in chat_out


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
    actions = editor.feed(b"\t")
    assert actions[0].kind == "cycle_focus"
    assert editor.feed(b"\x14")[0].kind == "cycle_tab"
    f1 = editor.feed(b"\x1b[11~")
    assert f1[0].kind == "main_tab"
    assert f1[0].text == "chat"
    assert "█" not in editor.display(active=False)


def test_dispatch_slash_help_and_quit() -> None:
    from coding_agent.cli.commands import dispatch_slash
    from fakes.settings import make_settings

    settings = make_settings()
    dummy = object()
    assert dispatch_slash("/q", dummy, settings).quit is True  # type: ignore[arg-type]
    help_out = dispatch_slash("/help", dummy, settings)  # type: ignore[arg-type]
    assert help_out.kind == "help"
    assert "/reset" in help_out.body
    assert "/mascot" in help_out.body
    assert "/term" not in help_out.body
    assert "/vim" in help_out.body
    assert dispatch_slash("/term", dummy, settings).kind == "warn"  # type: ignore[arg-type]
    assert dispatch_slash("/vim src/a.py", dummy, settings).body == "src/a.py"  # type: ignore[arg-type]
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

    from coding_agent.cli.chrome import (
        detect_git_branch,
        mascot_placeholder,
        short_home_path,
        usage_bar,
    )
    from coding_agent.cli.sprites.bank import reset_bank

    reset_bank()

    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert detect_git_branch(tmp_path) == "main"
    assert detect_git_branch(tmp_path / "nope") == ""
    assert usage_bar(0, 100, 10) == "░" * 10
    assert "█" in usage_bar(50, 100, 10)
    doodle = mascot_placeholder(phase=0).plain
    assert mascot_placeholder(phase=7).plain == doodle
    assert "预留" not in doodle
    assert any(ch in doodle for ch in "▀▄")
    assert len(doodle.splitlines()) == 16
    for banned in ("鲸鱼娘", "鲸鱼酿", "像素鲸鱼娘"):
        assert banned not in doodle
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


def test_dispatch_slash_mascot_lists_and_switches(tmp_path) -> None:
    from types import SimpleNamespace

    from coding_agent.agent.state import LoopState
    from coding_agent.cli.commands import dispatch_slash
    from coding_agent.cli.sprites.bank import get_bank, reset_bank
    from fakes.settings import make_settings

    reset_bank()
    settings = make_settings()
    settings.workdir = tmp_path
    session = SimpleNamespace(loop=SimpleNamespace(state=LoopState(), settings=settings))
    listed = dispatch_slash("/mascot", session, settings)
    assert listed.kind == "status"
    assert "default" in listed.body
    assert "投放目录" in listed.body
    assert ".wavecode/mascots" in listed.body
    assert "动作" not in listed.body
    assert dispatch_slash("/mascot think", session, settings).kind == "warn"
    assert get_bank().pose == "idle"
    assert dispatch_slash("/mascot nope", session, settings).kind == "warn"
    pack = tmp_path / ".wavecode" / "mascots" / "blob"
    pack.mkdir(parents=True)
    (pack / "palette.txt").write_text("k=#FF0000\n", encoding="utf-8")
    (pack / "idle.txt").write_text(("k" * 32 + "\n") + ("." * 32 + "\n") * 31, encoding="utf-8")
    switched = dispatch_slash("/mascot blob", session, settings)
    assert switched.body == "立绘包 = blob"
    assert get_bank().pack_name == "blob"
    reset_bank()


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


def test_tui_tab_focuses_files_and_nav_moves(tmp_path) -> None:
    from types import SimpleNamespace

    from coding_agent.agent.state import LoopState
    from coding_agent.cli.editor import KeyAction, LineEditor, NavKeys
    from coding_agent.cli.sidebar import reset_sidebar
    from coding_agent.cli.tui import OceanTui
    from coding_agent.cli.view import ChatView
    from fakes.settings import make_settings

    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b\n", encoding="utf-8")
    pane = reset_sidebar()
    pane.set_root(tmp_path)
    view = ChatView()
    settings = make_settings(workdir=tmp_path)
    session = SimpleNamespace(
        loop=SimpleNamespace(state=LoopState(), settings=settings),
        reset=lambda: None,
    )
    tui = OceanTui(session, None, settings, view)  # type: ignore[arg-type]
    editor = LineEditor()
    tui._apply([KeyAction("cycle_focus")], editor)
    assert view.snapshot().focus == "files"
    first = pane.selected("files")
    tui._apply_nav(NavKeys().feed(b"j"), editor)
    assert pane.selected("files") != first
    tui._apply_nav([KeyAction("cycle_focus")], editor)
    assert view.snapshot().focus == "changes"
    tui._apply_nav([KeyAction("focus_input")], editor)
    assert view.snapshot().focus == "input"


def test_stdin_is_ready_accepts_fd_or_file() -> None:
    from coding_agent.cli.tui import stdin_is_ready

    class _FakeStdin:
        def fileno(self) -> int:
            return 0

    assert stdin_is_ready([0], 0) is True
    assert stdin_is_ready([_FakeStdin()], 0) is True
    assert stdin_is_ready([], 0) is False
    assert stdin_is_ready([1], 0) is False


def test_tui_enter_opens_text_tab(tmp_path) -> None:
    from types import SimpleNamespace

    from coding_agent.agent.state import LoopState
    from coding_agent.cli.editor import KeyAction, LineEditor
    from coding_agent.cli.hub import get_hub
    from coding_agent.cli.sidebar import reset_sidebar
    from coding_agent.cli.tui import OceanTui
    from coding_agent.cli.view import ChatView
    from fakes.settings import make_settings

    (tmp_path / "note.md").write_text("hello\nworld\n", encoding="utf-8")
    pane = reset_sidebar()
    pane.set_root(tmp_path)
    view = ChatView()
    settings = make_settings(workdir=tmp_path)
    session = SimpleNamespace(
        loop=SimpleNamespace(state=LoopState(), settings=settings),
        reset=lambda: None,
    )
    tui = OceanTui(session, None, settings, view)  # type: ignore[arg-type]
    editor = LineEditor()
    tui._apply_nav([KeyAction("open")], editor)
    hub = get_hub()
    assert hub.tab == "text"
    assert hub.file_lines == ("hello", "world")
    assert view.snapshot().focus == "text"



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
    assert f"{CLI_NAME} ›" in out

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
    assert view.snapshot().focus == "input"
    view.set_focus("files")
    assert view.snapshot().focus == "files"
    view.set_focus("changes")
    assert view.snapshot().focus == "changes"
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

