"""Retry policy for the LLM transport (docs/02 §3.3, docs/08 §3)."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from coding_agent.errors import (
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)

RETRYABLE = (LLMTimeoutError, LLMRateLimitError, LLMUnavailableError)


class RetryPolicy(ABC):
    @abstractmethod
    def should_retry(self, exc: BaseException, attempt: int) -> bool: ...

    @abstractmethod
    def sleep_seconds(self, attempt: int) -> float: ...


class ExponentialBackoffRetry(RetryPolicy):
    """sleep = min(cap, base * 2**attempt) + jitter[0, 0.3); attempt from 0.

    max_attempts=4 means at most 4 HTTP calls (1 original + 3 retries).
    """

    def __init__(self, max_attempts: int = 4, base: float = 0.8, cap: float = 8.0) -> None:
        self.max_attempts = max_attempts
        self.base = base
        self.cap = cap

    def should_retry(self, exc: BaseException, attempt: int) -> bool:
        if attempt + 1 >= self.max_attempts:
            return False
        return isinstance(exc, RETRYABLE)

    def sleep_seconds(self, attempt: int) -> float:
        return min(self.cap, self.base * (2**attempt)) + random.uniform(0.0, 0.3)
