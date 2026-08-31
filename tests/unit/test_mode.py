from __future__ import annotations

from coding_agent.agent.mode import (
    allowed_tool_names,
    is_plan_document,
    parse_mode,
    parse_plan_interview,
    placeholder_for,
)
from coding_agent.app.system_prompt import build_system_prompt
from coding_agent.tools.executor import READONLY_TOOLS


def test_parse_mode_aliases() -> None:
    assert parse_mode("PLAN") == "plan"
    assert parse_mode("问答") == "ask"
    assert parse_mode("代理") == "agent"
    assert parse_mode("nope") is None


def test_allowed_tools_ask_and_plan_are_readonly() -> None:
    assert allowed_tool_names("ask") == READONLY_TOOLS
    assert allowed_tool_names("plan") == READONLY_TOOLS
    assert allowed_tool_names("agent") is None


def test_is_plan_document() -> None:
    assert is_plan_document("# 计划\n目标")
    assert is_plan_document("  # Plan\nGoal")
    assert not is_plan_document("选哪个框架？\n1. A\n2. B")


def test_ask_prompt_forbids_writes() -> None:
    text = build_system_prompt(workspace_root="/ws", tool_names=["read_file"], mode="ask")
    assert "ask mode" in text
    assert "Do not write" in text
    assert "Use bash only" not in text


def test_plan_prompt_requires_heading() -> None:
    text = build_system_prompt(workspace_root="/ws", tool_names=["read_file"], mode="plan")
    assert "exactly one question" in text
    assert "# 计划" in text
    assert "问题：" in text
    assert "FORBIDDEN" in text
    assert "You MUST solve programming tasks" not in text


def test_parse_plan_interview_one_question() -> None:
    good = (
        "问题：这个「番茄书城」的核心定位是什么？\n"
        "\n"
        "1. 在线书城（浏览、购买、阅读）\n"
        "2. 番茄钟与阅读结合\n"
        "3. 个人书架管理\n"
        "4. 以上都要\n"
        "\n"
        "回复数字，或自己写。\n"
    )
    got = parse_plan_interview(good)
    assert got is not None
    assert got.question.startswith("这个「番茄书城」")
    assert got.choices[0].startswith("在线书城")
    assert len(got.choices) == 4


def test_parse_plan_interview_rejects_batch() -> None:
    batch = (
        "明白了，确认几个关键点：\n"
        "1. 这个「番茄书城」的核心定位是什么？\n"
        "   1. 在线书城\n"
        "2. 技术栈有偏好吗？\n"
        "   1. 纯前端\n"
    )
    assert parse_plan_interview(batch) is None
    two_headers = "问题：A？\n1. x\n2. y\n\n问题：B？\n1. p\n2. q\n"
    assert parse_plan_interview(two_headers) is None
    assert parse_plan_interview("# 计划\n目标") is None


def test_agent_prompt_injects_plan_document() -> None:
    text = build_system_prompt(
        workspace_root="/ws",
        tool_names=["read_file", "write_file"],
        mode="agent",
        plan_document="# 计划\n改 a.py",
    )
    assert "Prefer tools over guessing" in text
    assert "## Active plan" in text
    assert "改 a.py" in text


def test_placeholder_for_plan() -> None:
    assert "每次只问一个问题" in placeholder_for("plan")
