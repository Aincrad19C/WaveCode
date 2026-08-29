from __future__ import annotations

from types import SimpleNamespace

from coding_agent.llm.catalog import (
    apply_model,
    discover_models,
    is_vision_model,
    resolve_model_id,
    supports_thinking,
)
from fakes.settings import make_settings


def test_known_v4_text_models_support_thinking() -> None:
    assert supports_thinking("deepseek-v4-flash") is True
    assert supports_thinking("deepseek-v4-pro") is True


def test_legacy_and_unknown_have_no_thinking_toggle() -> None:
    assert supports_thinking("deepseek-chat") is False
    assert supports_thinking("deepseek-reasoner") is False
    assert supports_thinking("other-chat") is False
    assert supports_thinking("gpt-style-id") is False


def test_retired_aliases_still_resolve_for_bootstrap() -> None:
    assert resolve_model_id("deepseek-chat") == "deepseek-v4-flash"
    assert resolve_model_id("deepseek-reasoner") == "deepseek-v4-flash"


def test_vision_ids_are_detected() -> None:
    assert is_vision_model("deepseek-v4-flash-vision-exp") is True
    assert is_vision_model("deepseek-v4-flash") is False


def test_discover_models_falls_back_to_text_catalog() -> None:
    models = discover_models(object(), current="deepseek-v4-flash")
    ids = [item.id for item in models]
    assert ids[:2] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert "deepseek-chat" in ids
    assert "deepseek-reasoner" in ids
    assert all("vision" not in item.id for item in models)


def test_discover_models_unions_catalog_when_api_is_v4_only() -> None:
    llm = SimpleNamespace(
        list_model_ids=lambda: [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-v4-flash-vision-exp",
        ]
    )
    ids = [item.id for item in discover_models(llm, current="deepseek-v4-flash")]
    assert ids == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-chat",
        "deepseek-reasoner",
    ]


def test_discover_models_keeps_api_ids_and_drops_vision() -> None:
    llm = SimpleNamespace(
        list_model_ids=lambda: [
            "deepseek-chat",
            "deepseek-v4-flash",
            "deepseek-v4-flash-vision-exp",
            "deepseek-v4-pro",
        ]
    )
    models = discover_models(llm, current="deepseek-chat")
    ids = [item.id for item in models]
    assert ids == [
        "deepseek-chat",
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-reasoner",
    ]
    assert all("vision" not in item.id for item in models)


def test_discover_models_falls_back_when_lister_fails() -> None:
    def boom() -> list[str]:
        raise RuntimeError("offline")

    models = discover_models(SimpleNamespace(list_model_ids=boom), current="deepseek-v4-flash")
    assert models[0].id == "deepseek-v4-flash"


def test_apply_model_keeps_legacy_id() -> None:
    settings = make_settings()
    settings.thinking = True
    seen: list[str] = []
    llm = SimpleNamespace(set_model=seen.append)
    session = SimpleNamespace(loop=SimpleNamespace(settings=settings, llm=llm))
    kind, body = apply_model(session, settings, "deepseek-chat")
    assert kind == "note"
    assert body == "模型 = deepseek-chat"
    assert settings.deepseek_model == "deepseek-chat"
    assert settings.thinking is False
    assert seen == ["deepseek-chat"]


def test_apply_model_rejects_vision() -> None:
    settings = make_settings()
    session = SimpleNamespace(loop=SimpleNamespace(settings=settings, llm=None))
    kind, body = apply_model(session, settings, "deepseek-v4-flash-vision-exp")
    assert kind == "warn"
    assert settings.deepseek_model == "deepseek-v4-flash"


def test_apply_model_updates_settings_llm_and_clears_thinking() -> None:
    settings = make_settings()
    settings.thinking = True
    seen: list[str] = []
    llm = SimpleNamespace(set_model=seen.append)
    summarizer = SimpleNamespace(set_model=seen.append)
    session = SimpleNamespace(
        loop=SimpleNamespace(settings=settings, llm=llm),
        context=SimpleNamespace(policy=SimpleNamespace(_summarizer=summarizer)),
    )
    kind, body = apply_model(session, settings, "other-chat")
    assert kind == "note"
    assert body == "模型 = other-chat"
    assert settings.deepseek_model == "other-chat"
    assert settings.thinking is False
    assert seen == ["other-chat", "other-chat"]
