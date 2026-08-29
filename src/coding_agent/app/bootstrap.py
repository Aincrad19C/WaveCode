"""Composition root (docs/01 §1): the only place concrete classes are wired.

No singletons; everything is constructor-injected so the loop can be unit
tested with fakes.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from coding_agent.agent.loop import AgentLoop
from coding_agent.agent.session import AgentSession
from coding_agent.app.system_prompt import build_system_prompt
from coding_agent.config.settings import Settings
from coding_agent.context.estimator import HeuristicTokenEstimator
from coding_agent.context.manager import ContextManager
from coding_agent.context.policy import (
    ContextPolicy,
    SummarizingContextPolicy,
    TruncatingContextPolicy,
)
from coding_agent.context.store import ConversationStore
from coding_agent.domain.messages import ChatMessage, Role
from coding_agent.domain.ports import EventSink, FanoutSink, NullSink
from coding_agent.errors import ConfigError
from coding_agent.llm.catalog import MODEL_ALIASES
from coding_agent.llm.deepseek import DeepSeekClient
from coding_agent.llm.retry import ExponentialBackoffRetry
from coding_agent.llm.summarize import LlmConversationSummarizer
from coding_agent.parsing.fallback import ContentFallbackParser
from coding_agent.parsing.native import NativeToolCallParser
from coding_agent.parsing.pipeline import ParserPipeline
from coding_agent.skills.bank import reset_skills
from coding_agent.termination.composite import AnyOfTermination
from coding_agent.termination.conditions import (
    CancelledCondition,
    ConsecutiveFailureCondition,
    ContextOverflowCondition,
    MaxTurnsCondition,
    NaturalCompletionCondition,
    WallClockCondition,
)
from coding_agent.tools.builtin import all_builtin_tools
from coding_agent.tools.executor import ToolExecutor
from coding_agent.tools.registry import ToolRegistry
from coding_agent.tools.workspace import Workspace

logger = logging.getLogger(__name__)

_PROXY_ENV_KEYS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
)
_SOCKS_SCHEMES = {"socks", "socks4", "socks5", "socks5h"}


def build_http_client(timeout_s: float) -> httpx.Client:
    """Construct httpx.Client without crashing on Clash-style socks:// env proxies.

    httpx only understands http/https (and socks5 with an extra package). Local
    mixed ports (e.g. 7897) usually speak HTTP CONNECT, so socks://host:port is
    rewritten to http://host:port. If that still fails, env proxies are ignored.
    """
    try:
        return httpx.Client(timeout=timeout_s)
    except ValueError as exc:
        rewritten = _http_proxy_from_socks_env()
        if rewritten:
            logger.warning(
                "httpx cannot use %s; trying HTTP proxy %s instead", exc, rewritten
            )
            try:
                return httpx.Client(timeout=timeout_s, proxy=rewritten, trust_env=False)
            except ValueError:
                pass
        logger.warning("ignoring unsupported environment proxy: %s", exc)
        return httpx.Client(timeout=timeout_s, trust_env=False)


def _http_proxy_from_socks_env() -> str | None:
    for key in _PROXY_ENV_KEYS:
        raw = os.environ.get(key)
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.scheme in _SOCKS_SCHEMES and parsed.hostname:
            port = f":{parsed.port}" if parsed.port else ""
            return f"http://{parsed.hostname}{port}"
    return None


def load_settings() -> Settings:
    load_dotenv()  # does not override already-exported environment variables
    settings = Settings()
    if alias := MODEL_ALIASES.get(settings.deepseek_model):
        model, force_thinking = alias
        logger.warning(
            "model %s is retired; using %s instead", settings.deepseek_model, model
        )
        update: dict = {"deepseek_model": model}
        if force_thinking:
            update["thinking"] = True
        settings = settings.model_copy(update=update)
    return settings


def build_session(settings: Settings, sinks: list[EventSink] | None = None) -> AgentSession:
    if not settings.deepseek_api_key:
        raise ConfigError(
            "DEEPSEEK_API_KEY is missing. Export it or put it in a gitignored .env"
        )
    if settings.max_tokens > settings.completion_reserve_tokens:
        raise ConfigError("max_tokens must not exceed completion_reserve_tokens (docs/04 §3)")

    sink: EventSink = FanoutSink(sinks) if sinks else NullSink()
    workspace = Workspace(settings.workdir)

    registry = ToolRegistry()
    for tool in all_builtin_tools():
        registry.register(tool)
    executor = ToolExecutor(
        registry,
        workspace,
        timeout_s=settings.bash_timeout_s,
        output_limit=settings.tool_output_max_chars,
        parallel_readonly=settings.parallel_readonly_tools,
    )

    estimator = HeuristicTokenEstimator()
    send_budget = settings.max_context_tokens - settings.completion_reserve_tokens
    truncating = TruncatingContextPolicy(
        send_budget=send_budget,
        tool_output_max_chars=settings.tool_output_max_chars,
        estimator=estimator,
    )
    llm = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        retry=ExponentialBackoffRetry(),
        http=build_http_client(settings.http_timeout_s),
    )
    policy: ContextPolicy = truncating
    if settings.summarize_context:
        policy = SummarizingContextPolicy(
            inner=truncating,
            summarizer=LlmConversationSummarizer(llm, model=settings.deepseek_model),
        )
    skills = reset_skills()
    skills.set_workdir(workspace.root)
    system = ChatMessage(
        role=Role.SYSTEM,
        content=build_system_prompt(
            workspace_root=str(workspace.root),
            tool_names=registry.names(),
            skill_catalog=skills.catalog(),
            active_skills=skills.active_bodies(),
        ),
    )
    context = ContextManager(
        store=ConversationStore(system),
        policy=policy,
        estimator=estimator,
        send_budget=send_budget,
    )

    parser = ParserPipeline([NativeToolCallParser(), ContentFallbackParser()])
    termination = AnyOfTermination(
        [
            CancelledCondition(),
            ConsecutiveFailureCondition(settings.max_consecutive_failures),
            WallClockCondition(settings.max_wallclock_s),
            ContextOverflowCondition(settings.max_context_tokens),
            MaxTurnsCondition(settings.max_turns),
            NaturalCompletionCondition(),
        ]
    )

    loop = AgentLoop(
        llm=llm,
        context=context,
        executor=executor,
        registry=registry,
        parser=parser,
        termination=termination,
        settings=settings,
        sink=sink,
    )
    return AgentSession(loop, context, sink)
