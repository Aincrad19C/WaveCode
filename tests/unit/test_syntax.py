from __future__ import annotations

from coding_agent.cli.prettydiff import visual_diff_lines
from coding_agent.cli.syntax import lexer_name, style_source


def test_visual_diff_skips_headers_and_paints_add_del() -> None:
    raw = """diff --git a/a.py b/a.py
index 111..222 100644
--- a/a.py
+++ b/a.py
@@ -1,2 +1,3 @@ def foo
 keep
-old
+new
"""
    rows = visual_diff_lines(raw)
    plain = "\n".join(row.plain for row in rows)
    assert "diff --git" not in plain
    assert "index " not in plain
    assert "--- a/a.py" not in plain
    assert "old" in plain
    assert "new" in plain
    assert any("+" in row.plain and "new" in row.plain for row in rows)
    assert any("−" in row.plain and "old" in row.plain for row in rows)


def test_style_source_python_keywords_and_rainbow_brackets() -> None:
    assert lexer_name("src/app.py") == "python"
    assert lexer_name("readme.txt") == ""
    rows = style_source("app.py", "def foo(x):\n    return (x + 1)\n")
    joined = "\n".join(row.plain for row in rows)
    assert "def foo" in joined
    assert "(" in joined
    styles = {str(span.style) for row in rows for span in row.spans}
    assert any("3EC8E8" in s or "cyan" in s.lower() or "bold" in s for s in styles)
