"""Wire-format contract for DeepSeek messages (docs/11 §6)."""

from __future__ import annotations

import json

import httpx
import pytest

from coding_agent.domain.messages import ChatMessage, Role, ToolCallRequest
from coding_agent.errors import (
    LLMAuthError,
    LLMBadResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from coding_agent.llm.deepseek import DeepSeekClient, parse_chat_completion
from coding_agent.llm.retry import ExponentialBackoffRetry
from coding_agent.llm.stream import StreamAssembler
from coding_agent.llm.types import ModelRequest


def test_to_api_messages_snapshot() -> None:
    messages = [
        ChatMessage(role=Role.SYSTEM, content="sys"),
        ChatMessage(role=Role.USER, content="task"),
        ChatMessage(
            role=Role.ASSISTANT,
            content=None,
            tool_calls=(
                ToolCallRequest("call_1", "write_file", '{"path":"a.py","content":"x"}'),
                ToolCallRequest("call_2", "bash", '{"command":"ls"}'),
            ),
        ),
        ChatMessage(role=Role.TOOL, content="wrote a.py", tool_call_id="call_1"),
        ChatMessage(role=Role.TOOL, content="exit_code: 0", tool_call_id="call_2"),
        ChatMessage(role=Role.ASSISTANT, content="done", reasoning_content="thought"),
    ]
    wire = DeepSeekClient._to_api_messages(messages)
    json.dumps(wire)  # must be serializable
    assert wire[0] == {"role": "system", "content": "sys"}
    assert wire[1] == {"role": "user", "content": "task"}
    assistant = wire[2]
    assert assistant["content"] is None  # JSON null when no narration
    assert assistant["tool_calls"][0] == {
        "id": "call_1",
        "type": "function",
        "function": {"name": "write_file", "arguments": '{"path":"a.py","content":"x"}'},
    }
    assert wire[3] == {"role": "tool", "tool_call_id": "call_1", "content": "wrote a.py"}
    assert wire[4]["tool_call_id"] == "call_2"
    assert wire[5] == {"role": "assistant", "content": "done", "reasoning_content": "thought"}


def test_reasoning_key_omitted_when_absent() -> None:
    wire = DeepSeekClient._to_api_messages([ChatMessage(role=Role.ASSISTANT, content="hi")])
    assert "reasoning_content" not in wire[0]


def test_parse_chat_completion_maps_fields() -> None:
    raw = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_9",
                            "type": "function",
                            "function": {"name": "grep", "arguments": '{"pattern": "x"}'},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    response = parse_chat_completion(raw)
    assert response.message.tool_calls[0].name == "grep"
    assert response.finish_reason.value == "tool_calls"
    assert response.usage is not None and response.usage.prompt_tokens == 10


def test_parse_chat_completion_no_choices_raises() -> None:
    with pytest.raises(LLMBadResponseError):
        parse_chat_completion({"choices": []})


def test_status_code_mapping() -> None:
    def resp(status: int, text: str = "", headers: dict | None = None) -> httpx.Response:
        return httpx.Response(
            status, text=text, headers=headers,
            request=httpx.Request("POST", "https://api.example.com"),
        )

    with pytest.raises(LLMAuthError):
        DeepSeekClient._raise_for_status(resp(401))
    with pytest.raises(LLMAuthError):
        DeepSeekClient._raise_for_status(resp(403))
    with pytest.raises(LLMRateLimitError) as rate:
        DeepSeekClient._raise_for_status(resp(429, headers={"Retry-After": "2"}))
    assert rate.value.retry_after_s == 2.0
    with pytest.raises(LLMTimeoutError):
        DeepSeekClient._raise_for_status(resp(408))
    with pytest.raises(LLMUnavailableError):
        DeepSeekClient._raise_for_status(resp(503))
    with pytest.raises(LLMBadResponseError):
        DeepSeekClient._raise_for_status(resp(400))


def test_error_detail_scrubs_keys() -> None:
    response = httpx.Response(
        500,
        text='{"error": "bad key sk-abc123"}',  # short fake; hygiene scan ignores
        request=httpx.Request("POST", "https://api.example.com"),
    )
    with pytest.raises(LLMUnavailableError) as exc:
        DeepSeekClient._raise_for_status(response)
    assert "sk-abcdef" not in str(exc.value)
    assert "sk-***" in str(exc.value)


def test_stream_assembler_joins_tool_call_fragments() -> None:
    assembler = StreamAssembler()
    assembler.feed({
        "choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "call_a", "function": {"name": "read_file", "arguments": ""}}
        ]}}]
    })
    assembler.feed({
        "choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": '{"path"'}}
        ]}}]
    })
    assembler.feed({
        "choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": ': "a.py"}'}}
        ]}, "finish_reason": "tool_calls"}]
    })
    response = assembler.finish()
    assert response.message.tool_calls[0].arguments_json == '{"path": "a.py"}'
    assert response.message.tool_calls[0].id == "call_a"


def test_stream_assembler_content_and_reasoning() -> None:
    assembler = StreamAssembler()
    assembler.feed({"choices": [{"delta": {"reasoning_content": "think "}}]})
    assembler.feed({"choices": [{"delta": {"content": "hel"}}]})
    assembler.feed({"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]})
    assembler.feed({"usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                    "choices": []})
    response = assembler.finish()
    assert response.message.content == "hello"
    assert response.message.reasoning_content == "think "
    assert response.finish_reason.value == "stop"
    assert response.usage is not None and response.usage.total_tokens == 5


def test_stream_assembler_empty_stream_raises() -> None:
    with pytest.raises(LLMBadResponseError):
        StreamAssembler().finish()


def _client(http: httpx.Client, model: str = "deepseek-v4-flash") -> DeepSeekClient:
    return DeepSeekClient(
        api_key="test-key-not-real",
        base_url="https://api.deepseek.com",
        model=model,
        retry=ExponentialBackoffRetry(max_attempts=1),
        http=http,
    )


def _request(model: str, *, thinking: bool = True) -> ModelRequest:
    return ModelRequest(
        messages=[],
        tools=[],
        model=model,
        temperature=0.2,
        max_tokens=16,
        thinking_enabled=thinking,
    )


def test_to_body_omits_thinking_when_model_has_no_toggle() -> None:
    client = _client(httpx.Client())
    with_think = client._to_body(_request("deepseek-v4-flash"), stream=False)
    assert with_think["thinking"] == {"type": "enabled"}
    without = client._to_body(_request("other-chat"), stream=False)
    assert "thinking" not in without
    assert "reasoning_effort" not in without


def test_list_model_ids_reads_data_array() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.deepseek.com/models"
        return httpx.Response(
            200,
            json={"data": [{"id": "deepseek-v4-pro"}, {"id": "deepseek-v4-flash"}]},
            request=request,
        )

    client = _client(httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.list_model_ids() == ["deepseek-v4-pro", "deepseek-v4-flash"]
