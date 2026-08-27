from __future__ import annotations

import json

import pytest

from coding_agent.errors import ToolCallParseError
from coding_agent.parsing.json_repair import repair_json_object


def test_plain_object_passthrough() -> None:
    assert json.loads(repair_json_object('{"a": 1}')) == {"a": 1}


def test_markdown_fence_removed() -> None:
    fixed = repair_json_object('```json\n{"path": "a.py"}\n```')
    assert json.loads(fixed) == {"path": "a.py"}


def test_trailing_comma() -> None:
    assert json.loads(repair_json_object('{"a": 1,}')) == {"a": 1}


def test_trailing_comma_in_array() -> None:
    assert json.loads(repair_json_object('{"a": [1, 2,]}')) == {"a": [1, 2]}


def test_single_quotes_when_unambiguous() -> None:
    assert json.loads(repair_json_object("{'a': 'b'}")) == {"a": "b"}


def test_python_literals() -> None:
    assert json.loads(repair_json_object('{"a": True, "b": None}')) == {"a": True, "b": None}


def test_prefix_noise_sliced() -> None:
    fixed = repair_json_object('Sure! Here you go: {"a": 1} hope it helps')
    assert json.loads(fixed) == {"a": 1}


def test_unrepairable_raises() -> None:
    with pytest.raises(ToolCallParseError):
        repair_json_object("not even close")
