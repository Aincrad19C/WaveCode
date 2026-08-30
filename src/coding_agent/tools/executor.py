"""Tool executor (docs/02 §4.4, docs/05 §4).

Any failure — unknown tool, bad JSON, path escape, timeout — becomes a failed
ToolResult that is fed back to the model. "工具失败不是 Agent 失败" (docs/08).
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from coding_agent.domain.events import ToolExecutionFinished, ToolExecutionStarted
from coding_agent.domain.messages import ToolCallRequest
from coding_agent.domain.ports import EventSink
from coding_agent.domain.results import ToolResult
from coding_agent.errors import UnknownToolError
from coding_agent.tools.base import ToolContext
from coding_agent.tools.registry import ToolRegistry
from coding_agent.tools.workspace import Workspace

READONLY_TOOLS = frozenset({"read_file", "list_dir", "glob_search", "grep"})


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        workspace: Workspace,
        *,
        timeout_s: float,
        output_limit: int,
        parallel_readonly: bool = False,
        mode: str = "agent",
    ) -> None:
        self._registry = registry
        self.workspace = workspace
        self._ctx = ToolContext(workspace=workspace, timeout_s=timeout_s, output_limit=output_limit)
        self._parallel_readonly = parallel_readonly
        self.mode = mode

    def execute_one(self, call: ToolCallRequest, sink: EventSink) -> ToolResult:
        sink.on_event(ToolExecutionStarted(call=call))
        if self.mode in {"ask", "plan"} and call.name not in READONLY_TOOLS:
            result = ToolResult(
                tool_call_id=call.id,
                name=call.name,
                ok=False,
                content=f"当前是 {self.mode} 模式，不能使用 {call.name}。",
            )
            sink.on_event(ToolExecutionFinished(result=result))
            return result
        try:
            tool = self._registry.get(call.name)
        except UnknownToolError as exc:
            result = ToolResult(tool_call_id=call.id, name=call.name, ok=False, content=str(exc))
        else:
            result = tool.run(call, self._ctx)  # run() already converts errors
        sink.on_event(ToolExecutionFinished(result=result))
        return result

    def execute_all(self, calls: Sequence[ToolCallRequest], sink: EventSink) -> list[ToolResult]:
        if not calls:
            return []
        all_readonly = all(call.name in READONLY_TOOLS for call in calls)
        if self._parallel_readonly and all_readonly and len(calls) > 1:
            with ThreadPoolExecutor(max_workers=min(4, len(calls))) as pool:
                return list(pool.map(lambda c: self.execute_one(c, sink), calls))
        # Serial by default: file tools have ordering dependencies (docs/01 §9)
        return [self.execute_one(call, sink) for call in calls]
