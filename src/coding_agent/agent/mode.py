"""Session modes: ask, plan, agent (docs/14)."""

from __future__ import annotations

from coding_agent.tools.executor import READONLY_TOOLS

ASK = "ask"
PLAN = "plan"
AGENT = "agent"
MODES = (ASK, PLAN, AGENT)
PLAN_HEADING = "# 计划"
PLAN_HEADING_EN = "# Plan"

_ALIASES = {
    ASK: ASK,
    PLAN: PLAN,
    AGENT: AGENT,
    "问答": ASK,
    "计划": PLAN,
    "代理": AGENT,
}

MODE_DETAILS = {
    ASK: "只读问答，不改文件",
    PLAN: "逐项确认后写出计划",
    AGENT: "改文件、执行命令",
}

PLACEHOLDERS = {
    ASK: "提问，只读作答，不改文件。Enter 发送。",
    PLAN: "描述目标。模型会逐项确认，答序号或自己写。Enter 发送。",
    AGENT: "在下方输入任务。Enter 发送，Ctrl+C 离开，/help 查看命令。",
}


def parse_mode(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    return _ALIASES.get(text.lower()) or _ALIASES.get(text)


def allowed_tool_names(mode: str) -> frozenset[str] | None:
    """None means every registered tool (agent)."""
    parsed = parse_mode(mode) or AGENT
    if parsed in {ASK, PLAN}:
        return READONLY_TOOLS
    return None


def is_plan_document(text: str) -> bool:
    head = text.lstrip()
    return head.startswith(PLAN_HEADING) or head.startswith(PLAN_HEADING_EN)


def placeholder_for(mode: str) -> str:
    return PLACEHOLDERS.get(parse_mode(mode) or AGENT, PLACEHOLDERS[AGENT])
