from __future__ import annotations

import json

from coding_agent.domain.messages import ChatMessage, Role, ToolCallRequest
from coding_agent.llm.types import FinishReason, ModelResponse
from coding_agent.parsing.fallback import ContentFallbackParser
from coding_agent.parsing.native import NativeToolCallParser
from coding_agent.parsing.pipeline import ParserPipeline


def response(
    content: str | None = None,
    tool_calls: tuple[ToolCallRequest, ...] = (),
    finish: FinishReason = FinishReason.STOP,
) -> ModelResponse:
    return ModelResponse(
        message=ChatMessage(role=Role.ASSISTANT, content=content, tool_calls=tool_calls),
        finish_reason=finish,
    )


def pipeline() -> ParserPipeline:
    return ParserPipeline([NativeToolCallParser(), ContentFallbackParser()])


def test_standard_tool_call() -> None:
    raw = response(
        tool_calls=(ToolCallRequest("c1", "read_file", '{"path": "a.py"}'),),
        finish=FinishReason.TOOL_CALLS,
    )
    parsed = pipeline().parse(raw)
    assert len(parsed.message.tool_calls) == 1
    assert parsed.message.tool_calls[0].name == "read_file"


def test_trailing_comma_arguments_repaired() -> None:
    raw = response(tool_calls=(ToolCallRequest("c1", "read_file", '{"path": "a.py",}'),))
    parsed = pipeline().parse(raw)
    assert json.loads(parsed.message.tool_calls[0].arguments_json) == {"path": "a.py"}


def test_finish_stop_with_tools_normalized_to_tool_calls() -> None:
    raw = response(
        tool_calls=(ToolCallRequest("c1", "bash", '{"command": "ls"}'),),
        finish=FinishReason.STOP,
    )
    parsed = pipeline().parse(raw)
    assert parsed.finish_reason is FinishReason.TOOL_CALLS


def test_empty_arguments_become_empty_object() -> None:
    raw = response(tool_calls=(ToolCallRequest("c1", "list_dir", ""),))
    parsed = pipeline().parse(raw)
    assert parsed.message.tool_calls[0].arguments_json == "{}"


def test_array_arguments_rewritten_as_error_object() -> None:
    raw = response(tool_calls=(ToolCallRequest("c1", "read_file", "[1, 2]"),))
    parsed = pipeline().parse(raw)
    assert json.loads(parsed.message.tool_calls[0].arguments_json) == {
        "_error": "arguments must be object"
    }


def test_empty_names_dropped_then_fallback() -> None:
    raw = response(
        content='<tool_call><name>grep</name><arguments>{"pattern": "x"}</arguments></tool_call>',
        tool_calls=(ToolCallRequest("c1", "  ", "{}"),),
    )
    parsed = pipeline().parse(raw)
    assert [call.name for call in parsed.message.tool_calls] == ["grep"]
    assert parsed.message.tool_calls[0].id.startswith("call_fb_")


def test_fallback_xml_block() -> None:
    raw = response(
        content=(
            "先看一眼文件。\n"
            '<tool_call><name>read_file</name><arguments>{"path": "a.py"}</arguments></tool_call>'
        )
    )
    parsed = pipeline().parse(raw)
    assert parsed.finish_reason is FinishReason.TOOL_CALLS
    assert parsed.message.tool_calls[0].name == "read_file"
    assert "tool_call" not in (parsed.message.content or "")
    assert "先看一眼文件" in (parsed.message.content or "")


def test_fallback_fenced_json() -> None:
    raw = response(content='```json\n{"tool": "list_dir", "arguments": {"path": "."}}\n```')
    parsed = pipeline().parse(raw)
    assert parsed.message.tool_calls[0].name == "list_dir"


def test_plain_code_block_not_mistaken_for_tool() -> None:
    raw = response(content='答案如下：\n```json\n{"result": 42}\n```')
    parsed = pipeline().parse(raw)
    assert parsed.message.tool_calls == ()
    assert parsed.finish_reason is FinishReason.STOP


def test_plain_text_untouched() -> None:
    raw = response(content="任务完成。")
    parsed = pipeline().parse(raw)
    assert parsed.message.content == "任务完成。"
    assert parsed.message.tool_calls == ()
