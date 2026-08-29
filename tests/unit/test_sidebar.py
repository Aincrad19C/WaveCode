from __future__ import annotations

from coding_agent.cli.sidebar import (
    FileChange,
    collect_tree,
    merge_changes,
    parse_porcelain,
    render_changes,
    render_tree,
    reset_sidebar,
    visible_tree,
)


def test_collect_tree_skips_dot_and_ignored(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir()
    (tmp_path / "__pycache__").mkdir()
    lines = collect_tree(tmp_path)
    names = {item.rel for item in lines}
    assert "src" in names
    assert "src/app.py" in names
    assert "README.md" in names
    assert ".env" not in names
    assert "node_modules" not in names
    assert "__pycache__" not in names


def test_parse_porcelain_and_merge() -> None:
    parsed = parse_porcelain(" M src/a.py\n?? new.txt\nD  gone.py\nR  old.py -> renamed.py\n")
    assert parsed == (
        FileChange("src/a.py", "M"),
        FileChange("new.txt", "A"),
        FileChange("gone.py", "D"),
        FileChange("renamed.py", "M"),
    )
    merged = merge_changes(parsed, [FileChange("src/a.py", "D"), FileChange("extra.py", "A")])
    by_path = {item.path: item.code for item in merged}
    assert by_path["src/a.py"] == "D"
    assert by_path["extra.py"] == "A"


def test_visible_tree_collapsed_by_default() -> None:
    from coding_agent.cli.sidebar import TreeLine

    tree = (
        TreeLine(0, "docs", True, "docs"),
        TreeLine(1, "a.md", False, "docs/a.md"),
        TreeLine(0, "src", True, "src"),
        TreeLine(1, "app.py", False, "src/app.py"),
    )
    collapsed = visible_tree(tree, set())
    assert [n.rel for n in collapsed] == ["docs", "src"]
    opened = visible_tree(tree, {"src"})
    assert [n.rel for n in opened] == ["docs", "src", "src/app.py"]


def test_sidebar_window_follows_cursor() -> None:
    from coding_agent.cli.sidebar import NavItem, TreeLine, _follow_cursor

    assert _follow_cursor(20, 5, 0, 0) == 0
    assert _follow_cursor(20, 5, 18, 0) == 14
    tree = (
        TreeLine(0, "docs", True, "docs"),
        TreeLine(1, "a.md", False, "docs/a.md"),
        TreeLine(1, "b.md", False, "docs/b.md"),
        TreeLine(1, "c.md", False, "docs/c.md"),
        TreeLine(0, "src", True, "src"),
    )
    selected = NavItem("dir", "src")
    body, offset, hint = render_tree(
        tree,
        dirty=set(),
        width=20,
        height=4,
        selected=selected,
        focused=True,
        expanded={"docs"},
    )
    assert "src/" in body.plain
    assert offset > 0
    assert "↓" in hint or "/" in hint


def test_render_tree_and_changes_are_separate() -> None:
    from coding_agent.cli.sidebar import TreeLine

    tree = (
        TreeLine(0, "src", True, "src"),
        TreeLine(1, "app.py", False, "src/app.py"),
    )
    changes = (FileChange("src/app.py", "M"),)
    tree_body, _off, _hint = render_tree(
        tree, dirty={"src/app.py"}, width=20, height=10, expanded=set()
    )
    change_body, _off2, _hint2 = render_changes(changes, width=20, height=6)
    assert "src/" in tree_body.plain
    assert "▸" in tree_body.plain
    assert "app.py" not in tree_body.plain
    assert "Changes" not in tree_body.plain
    assert "~ src/app.py" in change_body.plain
    assert "M src/app.py" not in change_body.plain
    assert "▸" not in change_body.plain


def test_sidebar_move_and_toggle_dir(tmp_path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "inner.py").write_text("i\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    pane = reset_sidebar()
    pane.set_root(tmp_path)
    first = pane.selected("files")
    assert first is not None
    rels = {n.rel for n in pane.visible()}
    assert "pkg" in rels
    assert "pkg/inner.py" not in rels
    pane.toggle_dir("pkg")
    rels = {n.rel for n in pane.visible()}
    assert "pkg/inner.py" in rels
    pane.move(1, "files")
    assert pane.selected("files") != first
    pane.note("a.py", "M")
    jumped = pane.jump_changes()
    assert jumped is not None
    assert jumped.kind == "change"
    assert jumped.rel == "a.py"
    text = pane.render_changes(width=24, height=6, focused=True).plain
    assert "a.py" in text


def test_sidebar_session_notes_clear_on_new_turn(tmp_path) -> None:
    (tmp_path / "keep.py").write_text("k\n", encoding="utf-8")
    pane = reset_sidebar()
    pane.set_root(tmp_path)
    pane.begin_turn()
    pane.note("keep.py", "M")
    assert any(item.path == "keep.py" for item in pane.changes())
    pane.begin_turn()
    assert pane.changes() == ()
    names = {item.name for item in pane.tree()}
    assert "keep.py" in names
