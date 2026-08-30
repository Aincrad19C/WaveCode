from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agent.domain.messages import ToolCallRequest
from coding_agent.errors import ConfigError
from coding_agent.tools.base import ToolContext, clip
from coding_agent.tools.builtin import all_builtin_tools
from coding_agent.tools.builtin.bash import BashTool, sanitized_env
from coding_agent.tools.builtin.edit_file import EditFileTool
from coding_agent.tools.builtin.glob_search import GlobSearchTool
from coding_agent.tools.builtin.grep import GrepTool
from coding_agent.tools.builtin.list_dir import ListDirTool
from coding_agent.tools.builtin.read_file import ReadFileTool
from coding_agent.tools.builtin.write_file import WriteFileTool
from coding_agent.tools.executor import ToolExecutor
from coding_agent.tools.registry import ToolRegistry
from coding_agent.tools.workspace import Workspace
from fakes.sink import RecordingSink


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(workspace=Workspace(tmp_path), timeout_s=10, output_limit=10_000)


def call(name: str, **args) -> ToolCallRequest:
    return ToolCallRequest(id="c1", name=name, arguments_json=json.dumps(args))


# -- registry -----------------------------------------------------------------

def test_registry_order_and_duplicates() -> None:
    registry = ToolRegistry()
    for tool in all_builtin_tools():
        registry.register(tool)
    assert registry.names() == (
        "read_file", "write_file", "edit_file", "list_dir", "glob_search", "grep", "bash",
    )
    with pytest.raises(ConfigError):
        registry.register(ReadFileTool())


def test_tool_schema_copy_is_professional() -> None:
    banned = ("内置", "改的不管", "(", ")")
    for tool in all_builtin_tools():
        schema = tool.schema()["function"]
        blob = schema["description"]
        for prop in schema["parameters"]["properties"].values():
            blob += " " + prop["description"]
        for phrase in banned:
            assert phrase not in blob, f"{tool.name}: {blob!r}"
        assert blob.strip()
        assert blob[0].isupper()


# -- read_file ------------------------------------------------------------------

def test_read_file_with_line_numbers(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello\nworld\n")
    result = ReadFileTool().run(call("read_file", path="a.txt"), ctx)
    assert result.ok
    assert "0001|hello" in result.content and "0002|world" in result.content


def test_read_file_missing(ctx: ToolContext) -> None:
    result = ReadFileTool().run(call("read_file", path="nope.txt"), ctx)
    assert not result.ok and "ENOENT" in result.content


def test_read_file_binary(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "bin.dat").write_bytes(b"abc\x00def")
    result = ReadFileTool().run(call("read_file", path="bin.dat"), ctx)
    assert not result.ok and "binary" in result.content


def test_read_file_offset_limit(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "n.txt").write_text("\n".join(f"L{i}" for i in range(1, 11)))
    result = ReadFileTool().run(call("read_file", path="n.txt", offset=3, limit=2), ctx)
    assert result.ok
    assert "0003|L3" in result.content and "0004|L4" in result.content
    assert "L5" not in result.content.split("more lines")[0].split("\n...")[0]


# -- write_file -----------------------------------------------------------------

def test_write_file_creates_parents(ctx: ToolContext, tmp_path: Path) -> None:
    result = WriteFileTool().run(call("write_file", path="d/e/f.py", content="x = 1\n"), ctx)
    assert result.ok and "wrote d/e/f.py" in result.content
    assert (tmp_path / "d/e/f.py").read_text() == "x = 1\n"


def test_write_file_escape_fails(ctx: ToolContext) -> None:
    result = WriteFileTool().run(call("write_file", path="../evil.txt", content="x"), ctx)
    assert not result.ok and "escapes workspace" in result.content


# -- edit_file --------------------------------------------------------------------

def test_edit_file_unique_match(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("a = 1\nb = 2\n")
    result = EditFileTool().run(
        call("edit_file", path="m.py", old_text="b = 2", new_text="b = 3"), ctx
    )
    assert result.ok and "edited m.py" in result.content
    assert (tmp_path / "m.py").read_text() == "a = 1\nb = 3\n"


def test_edit_file_zero_matches(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("a = 1\n")
    result = EditFileTool().run(
        call("edit_file", path="m.py", old_text="zzz", new_text="y"), ctx
    )
    assert not result.ok and "not found" in result.content


def test_edit_file_multiple_matches(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("x\nx\n")
    result = EditFileTool().run(call("edit_file", path="m.py", old_text="x", new_text="y"), ctx)
    assert not result.ok and "matched 2 times" in result.content


def test_write_and_edit_are_undone_together(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "old.py").write_text("alpha\n", encoding="utf-8")
    ctx.workspace.mark_new_task()
    assert WriteFileTool().run(call("write_file", path="new.py", content="beta\n"), ctx).ok
    assert EditFileTool().run(
        call("edit_file", path="old.py", old_text="alpha", new_text="gamma"), ctx
    ).ok
    assert ctx.workspace.restore_task_files() == ["new.py", "old.py"]
    assert not (tmp_path / "new.py").exists()
    assert (tmp_path / "old.py").read_text(encoding="utf-8") == "alpha\n"


# -- list_dir ---------------------------------------------------------------------

def test_list_dir_dirs_first(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "zdir").mkdir()
    (tmp_path / "afile.txt").touch()
    result = ListDirTool().run(call("list_dir"), ctx)
    assert result.ok
    assert result.content.splitlines() == ["d zdir", "f afile.txt"]


# -- glob_search --------------------------------------------------------------------

def test_glob_search(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/a.py").touch()
    (tmp_path / "b.py").touch()
    (tmp_path / "c.txt").touch()
    result = GlobSearchTool().run(call("glob_search", pattern="**/*.py"), ctx)
    assert result.ok
    assert set(result.content.splitlines()) == {"pkg/a.py", "b.py"}


def test_glob_skips_ignored_dirs(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv/x.py").touch()
    result = GlobSearchTool().run(call("glob_search", pattern="**/*.py"), ctx)
    assert result.content == "(no matches)"


# -- grep ---------------------------------------------------------------------------

def test_grep_matches(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "s.py").write_text("import os\nprint(os.name)\n")
    result = GrepTool().run(call("grep", pattern=r"import \w+"), ctx)
    assert result.ok and "s.py:1:import os" in result.content


def test_grep_bad_regex(ctx: ToolContext) -> None:
    result = GrepTool().run(call("grep", pattern="("), ctx)
    assert not result.ok and "bad regex" in result.content


def test_grep_ignore_case_flag(ctx: ToolContext, tmp_path: Path) -> None:
    (tmp_path / "s.txt").write_text("Hello World\n")
    result = GrepTool().run(call("grep", pattern="hello", flags="i"), ctx)
    assert result.ok and "s.txt:1:" in result.content


# -- bash ------------------------------------------------------------------------------

def test_bash_runs_in_workspace(ctx: ToolContext, tmp_path: Path) -> None:
    result = BashTool().run(call("bash", command="pwd"), ctx)
    assert result.ok
    assert f"stdout:\n{tmp_path.resolve()}" in result.content
    assert "exit_code: 0" in result.content


def test_bash_nonzero_exit_is_still_a_result(ctx: ToolContext) -> None:
    result = BashTool().run(call("bash", command="exit 3"), ctx)
    assert result.ok  # business outcome is in the text, not the ok flag
    assert "exit_code: 3" in result.content


def test_bash_env_is_sanitized(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-not-a-real-key")
    monkeypatch.setenv("MY_SECRET_TOKEN", "x")
    monkeypatch.setenv("SAFE_VAR", "keep")
    env = sanitized_env()
    assert "DEEPSEEK_API_KEY" not in env
    assert "MY_SECRET_TOKEN" not in env
    assert env["SAFE_VAR"] == "keep"
    result = BashTool().run(
        call("bash", command='python3 -c "import os; print(os.environ.get(\'DEEPSEEK_API_KEY\'))"'),
        ctx,
    )
    assert result.ok and "None" in result.content


def test_bash_timeout(ctx: ToolContext) -> None:
    result = BashTool().run(call("bash", command="sleep 5", timeout_s=0.2), ctx)
    assert not result.ok and "TIMEOUT" in result.content


def test_bash_denylist(ctx: ToolContext) -> None:
    result = BashTool().run(call("bash", command="rm -rf /"), ctx)
    assert not result.ok and "refused" in result.content


def test_bash_cd_persists_and_hides_cwd_marker(ctx: ToolContext, tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    first = BashTool().run(call("bash", command="cd sub && pwd"), ctx)
    assert first.ok
    assert str(sub.resolve()) in first.content
    assert "__WAVEMIO_CWD__" not in first.content
    assert ctx.workspace.cwd == sub.resolve()
    second = BashTool().run(call("bash", command="pwd"), ctx)
    assert str(sub.resolve()) in second.content
    BashTool().run(call("bash", command="cd .."), ctx)
    assert ctx.workspace.cwd == tmp_path.resolve()


# -- executor ----------------------------------------------------------------------------

def test_executor_unknown_tool_is_failed_result(tmp_path: Path) -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry, Workspace(tmp_path), timeout_s=5, output_limit=1000)
    sink = RecordingSink()
    result = executor.execute_one(
        ToolCallRequest(id="x", name="nope", arguments_json="{}"), sink
    )
    assert not result.ok and "no such tool" in result.content


def test_executor_invalid_json_is_failed_result(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    executor = ToolExecutor(registry, Workspace(tmp_path), timeout_s=5, output_limit=1000)
    result = executor.execute_one(
        ToolCallRequest(id="x", name="read_file", arguments_json="not json"),
        RecordingSink(),
    )
    assert not result.ok and "argument error" in result.content


def test_executor_missing_required_arg(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    executor = ToolExecutor(registry, Workspace(tmp_path), timeout_s=5, output_limit=1000)
    result = executor.execute_one(
        ToolCallRequest(id="x", name="read_file", arguments_json="{}"), RecordingSink()
    )
    assert not result.ok and "missing required argument: path" in result.content


def test_executor_blocks_write_in_plan_mode(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(WriteFileTool())
    executor = ToolExecutor(
        registry, Workspace(tmp_path), timeout_s=5, output_limit=1000, mode="plan"
    )
    result = executor.execute_one(
        ToolCallRequest(
            id="x",
            name="write_file",
            arguments_json='{"path": "a.py", "content": "x"}',
        ),
        RecordingSink(),
    )
    assert not result.ok
    assert "plan" in result.content
    assert not (tmp_path / "a.py").exists()


# -- clip ------------------------------------------------------------------------------------

def test_clip_keeps_head_and_tail() -> None:
    text = "H" * 800 + "M" * 800 + "T" * 400
    clipped = clip(text, 1000)
    assert clipped.startswith("[truncated by agent, original_chars=2000]")
    assert "... middle omitted ..." in clipped
    assert clipped.rstrip().endswith("T" * 10)
