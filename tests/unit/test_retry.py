from __future__ import annotations

from coding_agent.errors import (
    LLMAuthError,
    LLMBadResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from coding_agent.llm.retry import ExponentialBackoffRetry


def test_retryable_errors() -> None:
    policy = ExponentialBackoffRetry(max_attempts=4)
    for exc in (LLMTimeoutError("t"), LLMRateLimitError("r"), LLMUnavailableError("u")):
        assert policy.should_retry(exc, attempt=0)


def test_non_retryable_errors() -> None:
    policy = ExponentialBackoffRetry(max_attempts=4)
    for exc in (LLMAuthError("a"), LLMBadResponseError("b"), ValueError("v")):
        assert not policy.should_retry(exc, attempt=0)


def test_attempts_exhausted() -> None:
    policy = ExponentialBackoffRetry(max_attempts=4)
    assert policy.should_retry(LLMTimeoutError("t"), attempt=2)
    assert not policy.should_retry(LLMTimeoutError("t"), attempt=3)


def test_backoff_growth_and_cap() -> None:
    policy = ExponentialBackoffRetry(max_attempts=10, base=0.8, cap=8.0)
    s0 = policy.sleep_seconds(0)
    s3 = policy.sleep_seconds(3)
    s9 = policy.sleep_seconds(9)
    assert 0.8 <= s0 < 1.1  # base + jitter[0, 0.3)
    assert 6.4 <= s3 < 6.7
    assert 8.0 <= s9 < 8.3  # capped
