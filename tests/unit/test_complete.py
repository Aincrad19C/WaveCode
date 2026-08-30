from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

from rich.console import Console

from coding_agent.agent.state import LoopState
from coding_agent.cli.branding import PRODUCT_NAME
from coding_agent.cli.chrome import WorkspaceChrome
from coding_agent.cli.commands import filled_command, slash_matches, slash_prefix
from coding_agent.cli.editor import LineEditor
from coding_agent.cli.sidebar import reset_sidebar
from coding_agent.cli.sprites.bank import reset_bank
from coding_agent.cli.tui import OceanTui, render_frame
from coding_agent.cli.view import ChatView
from fakes.settings import make_settings


def test_slash_matches_prefix_and_hides_think() -> None:
    all_names = [spec.name for spec in slash_matches("/", thinking=True)]
    assert "/help" in all_names
    assert "/think" in all_names
    assert "/q" in all_names
    hidden = [spec.name for spec in slash_matches("/", thinking=False)]
    assert "/think" not in hidden
    assert [spec.name for spec in slash_matches("/he", thinking=True)] == ["/help"]
    assert [spec.name for spec in slash_matches("/m", thinking=True)] == [
        "/model",
        "/mode",
        "/mascot",
    ]
    assert slash_matches("/help extra", thinking=True) == ()
    assert slash_prefix("/he█lp") == "/help"
    assert filled_command(slash_matches("/mode", thinking=True)[0]) == "/mode "


def test_tui_slash_complete_up_down_enter() -> None:
    view = ChatView()
    settings = make_settings()
    session = SimpleNamespace(
        loop=SimpleNamespace(state=LoopState(), settings=settings),
        ask=lambda text: None,
        reset=lambda: None,
    )
    tui = OceanTui(session, None, settings, view)  # type: ignore[arg-type]
    editor = LineEditor()
    tui._apply(editor.feed(b"/"), editor)
    view.set_input(editor.display())
    names = [spec.name for spec in slash_matches("/", thinking=True)]
    tui._apply(editor.feed(b"\x1b[B"), editor)
    view.set_input(editor.display())
    assert view.snapshot().complete_index == 1
    tui._apply(editor.feed(b"\r"), editor)
    view.set_input(editor.display())
    assert editor.buffer == names[1]
    assert names[1] == "/reset"


def test_tui_slash_complete_help_then_submit() -> None:
    view = ChatView()
    settings = make_settings()
    session = SimpleNamespace(
        loop=SimpleNamespace(state=LoopState(), settings=settings),
        ask=lambda text: None,
        reset=lambda: None,
    )
    tui = OceanTui(session, None, settings, view)  # type: ignore[arg-type]
    editor = LineEditor()
    tui._apply(editor.feed(b"/he"), editor)
    view.set_input(editor.display())
    tui._apply(editor.feed(b"\r"), editor)
    assert editor.buffer == "/help"
    tui._apply(editor.feed(b"\r"), editor)
    assert editor.buffer == ""
    assert view.snapshot().items[-1].kind == "help"


def test_exact_slash_enter_runs_without_expanding_alias() -> None:
    view = ChatView()
    settings = make_settings()
    session = SimpleNamespace(
        loop=SimpleNamespace(state=LoopState(), settings=settings),
        ask=lambda text: None,
        reset=lambda: None,
    )
    tui = OceanTui(session, None, settings, view)  # type: ignore[arg-type]
    editor = LineEditor()
    assert tui._apply(editor.feed(b"/q\r"), editor) == "quit"
    assert [spec.name for spec in slash_matches("/q", thinking=True)][0] == "/q"


def test_tui_frame_shows_slash_menu() -> None:
    reset_bank()
    reset_sidebar()
    view = ChatView()
    view.set_input("/█")
    buf = StringIO()
    console = Console(
        file=buf,
        width=80,
        height=32,
        force_terminal=True,
        color_system=None,
        record=True,
    )
    console.print(render_frame(view, chrome=WorkspaceChrome(version="3.2.0"), width=80))
    out = console.export_text()
    assert PRODUCT_NAME in out
    assert "/help" in out
    assert "列出命令" in out
    assert "▸" in out


def test_history_up_when_not_completing() -> None:
    view = ChatView()
    settings = make_settings()
    session = SimpleNamespace(
        loop=SimpleNamespace(state=LoopState(), settings=settings),
        ask=lambda text: None,
        reset=lambda: None,
    )
    tui = OceanTui(session, None, settings, view)  # type: ignore[arg-type]
    editor = LineEditor()
    editor.history.append("hello")
    tui._apply(editor.feed(b"\x1b[A"), editor)
    assert editor.buffer == "hello"
