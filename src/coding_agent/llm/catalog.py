"""DeepSeek model ids from official docs, plus GET /models when a key exists.

Known ids and thinking flags come from api-docs.deepseek.com, not invention.
The picker is text-only: vision ids are never listed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Retired ids still accepted in .env; map like bootstrap (docs/10 §11).
# /model lists and applies the raw id, so the picker is not V4-only.
MODEL_ALIASES: dict[str, tuple[str, bool]] = {
    "deepseek-chat": ("deepseek-v4-flash", False),
    "deepseek-reasoner": ("deepseek-v4-flash", True),
}

# Text Chat Completions ids. Vision models are omitted: this program sends text only.
_KNOWN: tuple[tuple[str, bool], ...] = (
    ("deepseek-v4-flash", True),
    ("deepseek-v4-pro", True),
    ("deepseek-chat", False),
    ("deepseek-reasoner", False),
)
_KNOWN_ORDER = tuple(item[0] for item in _KNOWN)
_KNOWN_MAP = {item[0]: item[1] for item in _KNOWN}


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: str
    thinking: bool


def resolve_model_id(model_id: str) -> str:
    name = model_id.strip()
    if name in MODEL_ALIASES:
        return MODEL_ALIASES[name][0]
    return name


def is_vision_model(model_id: str) -> bool:
    return "vision" in model_id.strip().lower()


def supports_thinking(model_id: str) -> bool:
    """Return whether the Chat Completions thinking toggle applies.

    V4 hosted text ids document Thinking / Non-Thinking. Legacy chat/reasoner
    and unknown ids without v4 in the name have no toggle.
    """
    name = model_id.strip()
    if name in _KNOWN_MAP:
        return _KNOWN_MAP[name]
    return "v4" in name.lower() and not is_vision_model(name)


def infos_for(ids: list[str] | None, *, current: str) -> list[ModelInfo]:
    """Build the picker list. ``ids is None`` uses the documented text catalog."""
    current_id = current.strip()
    if ids is not None:
        ordered = _visible_ids(ids, current=current_id)
    else:
        ordered = [name for name in _KNOWN_ORDER if not is_vision_model(name)]
        if current_id and current_id not in ordered and not is_vision_model(current_id):
            ordered.append(current_id)
    return [
        ModelInfo(id=name, thinking=supports_thinking(name))
        for name in ordered
    ]


def discover_models(llm: Any, *, current: str) -> list[ModelInfo]:
    """Prefer GET /models on the live client; fall back to the documented catalog."""
    lister = getattr(llm, "list_model_ids", None)
    if callable(lister):
        try:
            fetched = [str(item).strip() for item in lister() if str(item).strip()]
        except Exception as exc:
            logger.warning("model list failed: %s", exc)
            fetched = []
        if fetched:
            merged = list(fetched)
            seen = {name.strip() for name in fetched}
            for name in _KNOWN_ORDER:
                if name not in seen:
                    merged.append(name)
            return infos_for(merged, current=current)
    return infos_for(None, current=current)


def list_text(models: list[ModelInfo], *, current: str) -> str:
    current_id = current.strip()
    lines = [
        f"当前  {current_id}",
        "",
        "全屏：空格勾选，Enter 确认，Esc 取消。",
        "",
        "模型：",
    ]
    for info in models:
        mark = "✓" if info.id == current_id else " "
        lines.append(f"  [{mark}] {info.id}")
    lines.append("")
    lines.append("请输入 /model 打开勾选列表。")
    return "\n".join(lines)


def apply_model(session: Any, settings: Any, model_id: str) -> tuple[str, str]:
    name = model_id.strip()
    if not name or is_vision_model(name):
        return "warn", "请输入 /model 打开勾选列表。"
    settings.deepseek_model = name
    loop = getattr(session, "loop", None)
    loop_settings = getattr(loop, "settings", None)
    if loop_settings is not None:
        loop_settings.deepseek_model = name
    llm = getattr(loop, "llm", None)
    setter = getattr(llm, "set_model", None)
    if callable(setter):
        setter(name)
    _sync_summarizer_model(session, name)
    if not supports_thinking(name):
        settings.thinking = False
        if loop_settings is not None:
            loop_settings.thinking = False
    return "note", f"模型 = {name}"


def _sync_summarizer_model(session: Any, model_id: str) -> None:
    context = getattr(session, "context", None)
    policy = getattr(context, "policy", None)
    summarizer = getattr(policy, "_summarizer", None)
    setter = getattr(summarizer, "set_model", None)
    if callable(setter):
        setter(model_id)


def _visible_ids(ids: list[str], *, current: str) -> list[str]:
    """Keep API order. Do not rewrite aliases to V4. Drop vision ids."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in ids:
        name = raw.strip()
        if not name or is_vision_model(name) or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    if current and current not in seen and not is_vision_model(current):
        ordered.append(current)
    return ordered
