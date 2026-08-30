from __future__ import annotations

from io import StringIO

from rich.console import Console

from coding_agent.cli.branding import PRODUCT_NAME
from coding_agent.cli.markdown import assistant_markdown, markdown_line_count


def _plain(renderable, *, width: int = 80) -> str:
    buf = StringIO()
    console = Console(
        file=buf,
        width=width,
        color_system=None,
        force_terminal=True,
        highlight=False,
    )
    console.print(renderable)
    return buf.getvalue()


def test_assistant_markdown_heading_bold_and_fence() -> None:
    text = "# 计划\n\n这是 **粗体** 说明。\n\n```python\nprint(1)\n```\n"
    out = _plain(assistant_markdown(text))
    assert "计划" in out
    assert "粗体" in out
    assert "**粗体**" not in out
    assert "print(1)" in out
    assert "```" not in out


def test_assistant_markdown_plain_text_unchanged() -> None:
    out = _plain(assistant_markdown("当前目录是空的。"))
    assert "当前目录是空的。" in out


def test_markdown_line_count_at_least_content() -> None:
    assert markdown_line_count("", 40) == 1
    assert markdown_line_count("hello", 40) >= 1
    tall = "# 计划\n\n- a\n- b\n- c\n"
    assert markdown_line_count(tall, 60) >= markdown_line_count("hello", 60)


def test_tui_renders_assistant_markdown_not_raw() -> None:
    from coding_agent.cli.chrome import WorkspaceChrome
    from coding_agent.cli.sidebar import reset_sidebar
    from coding_agent.cli.sprites.bank import reset_bank
    from coding_agent.cli.tui import render_frame
    from coding_agent.cli.view import ChatView

    reset_bank()
    reset_sidebar()
    view = ChatView()
    view.append("user", "请用 **粗体**")
    view.append("assistant", "# 计划\n\n请用 **粗体**。\n")
    chrome = WorkspaceChrome(version="3.1.0")
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
    assert "计划" in out
    assert "粗体" in out
    assert "**粗体**" in out  # user bubble stays literal
    assert "请用 **粗体**。" not in out  # assistant is rendered


def test_repl_final_answer_renders_markdown() -> None:
    from coding_agent.cli.renderer import RichEventSink
    from coding_agent.domain.events import FinalAnswer

    buf = StringIO()
    sink = RichEventSink(Console(file=buf, force_terminal=False, width=80, color_system=None))
    sink.on_event(FinalAnswer(text="这是 **粗体**。", reason="natural"))
    out = buf.getvalue()
    assert "粗体" in out
    assert "**粗体**" not in out
    assert PRODUCT_NAME in out
