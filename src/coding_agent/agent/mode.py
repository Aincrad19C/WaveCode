"""Session modes: ask, plan, agent (docs/14)."""

from __future__ import annotations

import re
from dataclasses import dataclass

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
    PLAN: "每次只问一个问题，确认后写出计划",
    AGENT: "改文件、执行命令",
}

PLACEHOLDERS = {
    ASK: "提问，只读作答，不改文件。Enter 发送。",
    PLAN: "描述目标。每次只问一个问题；↑↓ 选答案，或自己写。Enter 发送。",
    AGENT: "在下方输入任务。Enter 发送，Ctrl+C 离开，/help 查看命令。",
}

_QUESTION_LINE = re.compile(r"^问题[：:]\s*(.+)$")
_CHOICE_LINE = re.compile(r"^(\d+)[.．、)]\s+(\S.*)$")
_NUMBERED_QUESTION = re.compile(r"^\d+[.．、)]\s+.+\S[？?]\s*$")


@dataclass(frozen=True, slots=True)
class PlanInterview:
    question: str
    choices: tuple[str, ...]


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


def parse_plan_interview(text: str) -> PlanInterview | None:
    """One 问题： plus 2–4 numbered choices. Rejects batched questionnaires."""
    if not text or is_plan_document(text):
        return None
    lines = text.replace("\r\n", "\n").split("\n")
    q_idxs = [i for i, line in enumerate(lines) if _QUESTION_LINE.match(line.strip())]
    if len(q_idxs) != 1:
        return None
    q_at = q_idxs[0]
    extras = [
        line
        for i, line in enumerate(lines)
        if i != q_at and _NUMBERED_QUESTION.match(line.strip())
    ]
    if extras:
        return None
    matched = _QUESTION_LINE.match(lines[q_at].strip())
    question = (matched.group(1) if matched else "").strip()
    if not question:
        return None
    choices: list[str] = []
    expected = 1
    for line in lines[q_at + 1 :]:
        stripped = line.strip()
        if not stripped:
            if choices:
                break
            continue
        choice = _CHOICE_LINE.match(stripped)
        if choice is None:
            break
        if int(choice.group(1)) != expected:
            return None
        choices.append(choice.group(2).strip())
        expected += 1
        if expected > 5:
            return None
    if not 2 <= len(choices) <= 4:
        return None
    return PlanInterview(question=question, choices=tuple(choices))


def placeholder_for(mode: str) -> str:
    return PLACEHOLDERS.get(parse_mode(mode) or AGENT, PLACEHOLDERS[AGENT])
