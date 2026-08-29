from __future__ import annotations

from coding_agent.cli.editor import decode_csi
from coding_agent.cli.hub import get_hub, reset_hub


def test_hub_opens_file_as_text_tab(tmp_path) -> None:
    (tmp_path / "note.md").write_text("hello\nworld\n", encoding="utf-8")
    hub = reset_hub()
    assert hub.open_file(tmp_path, "note.md") == ""
    assert hub.tab == "text"
    assert hub.file_lines == ("hello", "world")
    hub.scroll_text(1, 1)
    assert hub.file_scroll == 1
    assert hub.file_styled
    assert hub.file_mode == "code"
    py = tmp_path / "app.py"
    py.write_text("def foo():\n    return 1\n", encoding="utf-8")
    assert hub.open_file(tmp_path, "app.py") == ""
    assert "def foo" in hub.file_lines[0]
    assert hub.cycle_tab() == "chat"
    assert get_hub().tab == "chat"


def test_decode_csi_wheel_and_fkeys() -> None:
    wheel = decode_csi("<65;1;1", "M")
    assert wheel is not None
    assert wheel.kind == "wheel"
    assert decode_csi("11", "~") is not None
    assert decode_csi("11", "~").kind == "main_tab"
    assert decode_csi("11", "~").text == "chat"
    assert decode_csi("<64;2;2", "M").kind == "wheel"
    assert decode_csi("13", "~") is None
