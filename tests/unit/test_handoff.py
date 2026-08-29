from __future__ import annotations

from coding_agent.cli.editor import NavKeys
from coding_agent.cli.handoff import resolve_under_root


def test_resolve_under_root_blocks_escape(tmp_path) -> None:
    (tmp_path / "ok.py").write_text("x\n", encoding="utf-8")
    assert resolve_under_root(tmp_path, "ok.py") == (tmp_path / "ok.py").resolve()
    assert resolve_under_root(tmp_path, "../secret") is None


def test_nav_keys_vim_style() -> None:
    keys = NavKeys()
    kinds = [a.kind for a in keys.feed(b"jkcd!\t\r\x1b")]
    assert kinds[:4] == ["move", "move", "jump_changes", "diff"]
    assert "shell" not in kinds
    assert "cycle_focus" in kinds
    assert "open" in kinds
    assert "focus_input" in kinds
    up = NavKeys().feed(b"\x1b[A")
    assert up[0].kind == "move"
    assert up[0].text == "-1"
    wheel = NavKeys().feed(b"\x1b[<64;1;1M")
    assert wheel[0].kind == "wheel"
    f2 = NavKeys().feed(b"\x1b[12~")
    assert f2[0].kind == "main_tab"
    assert f2[0].text == "text"
    assert NavKeys().feed(b"\x1b[13~") == []
