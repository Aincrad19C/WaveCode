"""DeepSeek Chat Completions adapter (docs/02 §3.4, docs/08 §2, docs/11).

Turns ModelRequest into the official JSON body, maps HTTP failures onto the
exception hierarchy, and parses either the JSON body or the SSE stream into a
ModelResponse. This class never executes tools and never touches the
conversation store.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from coding_agent.domain.events import ContentDelta, ReasoningDelta
from coding_agent.domain.messages import ChatMessage, Role, ToolCallRequest
from coding_agent.domain.ports import EventSink
from coding_agent.errors import (
    LLMAuthError,
    LLMBadResponseError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from coding_agent.llm.client import LLMClient
from coding_agent.llm.retry import RetryPolicy
from coding_agent.llm.stream import StreamAssembler, parse_usage
from coding_agent.llm.types import FinishReason, ModelRequest, ModelResponse, TokenUsage

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(r"sk-[a-zA-Z0-9]+")


def _scrub(text: str) -> str:
    """Redact anything that looks like an API key before it reaches logs/UI."""
    return _SECRET_RE.sub("sk-***", text)[:500]


class DeepSeekClient(LLMClient):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        retry: RetryPolicy,
        http: httpx.Client,
    ) -> None:
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._retry = retry
        self._http = http

    # -- public API ---------------------------------------------------------

    def complete(self, request: ModelRequest) -> ModelResponse:
        body = self._to_body(request, stream=False)
        raw = self._with_retry(lambda: self._post_json(body))
        return parse_chat_completion(raw)

    def stream(self, request: ModelRequest, sink: EventSink) -> ModelResponse:
        body = self._to_body(request, stream=True)
        return self._with_retry(lambda: self._post_stream(body, sink))

    # -- request shaping ----------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _to_body(self, request: ModelRequest, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model or self._model,
            "messages": self._to_api_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
            "thinking": {"type": "enabled" if request.thinking_enabled else "disabled"},
        }
        if request.tools:
            body["tools"] = list(request.tools)
            body["tool_choice"] = request.tool_choice
        if request.thinking_enabled:
            body["reasoning_effort"] = request.reasoning_effort
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    @staticmethod
    def _to_api_messages(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
        """The only place ChatMessage becomes wire JSON (docs/11)."""
        out: list[dict[str, Any]] = []
        for msg in messages:
            item: dict[str, Any] = {"role": msg.role.value}
            if msg.role is Role.TOOL:
                item["tool_call_id"] = msg.tool_call_id
                item["content"] = msg.content or ""
            elif msg.role is Role.ASSISTANT:
                if msg.tool_calls:
                    item["content"] = msg.content  # JSON null when no narration
                    item["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments_json,
                            },
                        }
                        for call in msg.tool_calls
                    ]
                else:
                    item["content"] = msg.content or ""
                if msg.reasoning_content:  # required when thinking + tools (docs/11 §2)
                    item["reasoning_content"] = msg.reasoning_content
            else:  # system / user must carry a string
                item["content"] = msg.content or ""
            if msg.name:
                item["name"] = msg.name
            out.append(item)
        return out

    # -- transport ----------------------------------------------------------

    def _with_retry(self, attempt_fn):
        attempt = 0
        while True:
            try:
                return attempt_fn()
            except LLMError as exc:
                if not self._retry.should_retry(exc, attempt):
                    raise
                delay = self._retry.sleep_seconds(attempt)
                if isinstance(exc, LLMRateLimitError) and exc.retry_after_s:
                    delay = max(delay, exc.retry_after_s)
                logger.warning("LLM retry %d in %.1fs: %s", attempt + 1, delay, _scrub(str(exc)))
                time.sleep(delay)
                attempt += 1

    def _post_json(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self._request(body)
        self._raise_for_status(response)
        try:
            return response.json()
        except ValueError as exc:
            raise LLMBadResponseError("HTTP 200 but body is not JSON") from exc

    def _post_stream(self, body: Mapping[str, Any], sink: EventSink) -> ModelResponse:
        assembler = StreamAssembler()
        try:
            with self._http.stream(
                "POST", self._url, headers=self._headers(), json=body
            ) as response:
                if response.status_code != 200:
                    response.read()
                    self._raise_for_status(response)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except ValueError:
                        logger.debug("ignoring non-JSON SSE line")
                        continue
                    before_content = len(assembler.content_so_far)
                    assembler.feed(chunk)
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    if text := delta.get("reasoning_content"):
                        sink.on_event(ReasoningDelta(text=text))
                    if text := delta.get("content"):
                        if len(assembler.content_so_far) > before_content:
                            sink.on_event(ContentDelta(text=text))
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(_scrub(str(exc))) from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(_scrub(str(exc))) from exc
        return assembler.finish()

    def _request(self, body: Mapping[str, Any]) -> httpx.Response:
        try:
            return self._http.post(self._url, headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(_scrub(str(exc))) from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(_scrub(str(exc))) from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status == 200:
            return
        detail = _scrub(response.text)
        if status in (401, 403):
            raise LLMAuthError(f"HTTP {status}: check DEEPSEEK_API_KEY. {detail}")
        if status == 429:
            retry_after: float | None = None
            header = response.headers.get("Retry-After", "")
            if header.replace(".", "", 1).isdigit():
                retry_after = float(header)
            raise LLMRateLimitError(f"HTTP 429: {detail}", retry_after_s=retry_after)
        if status == 408:
            raise LLMTimeoutError(f"HTTP 408: {detail}")
        if status >= 500:
            raise LLMUnavailableError(f"HTTP {status}: {detail}")
        raise LLMBadResponseError(f"HTTP {status}: {detail}")


def parse_chat_completion(raw: Mapping[str, Any]) -> ModelResponse:
    """Field-level mapping from a non-streaming body (docs/06 §2)."""
    choices = raw.get("choices")
    if not choices:
        raise LLMBadResponseError("response has no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    calls = tuple(
        ToolCallRequest(
            id=str(item.get("id", "")),
            name=str((item.get("function") or {}).get("name", "")),
            arguments_json=str((item.get("function") or {}).get("arguments", "")),
        )
        for item in message.get("tool_calls") or []
    )
    usage: TokenUsage | None = parse_usage(raw.get("usage"))
    return ModelResponse(
        message=ChatMessage(
            role=Role.ASSISTANT,
            content=message.get("content"),
            reasoning_content=message.get("reasoning_content"),
            tool_calls=calls,
        ),
        finish_reason=FinishReason.from_api(choice.get("finish_reason")),
        usage=usage,
        raw=raw,
    )
