"""Retry with exponential backoff, jitter, and optional model fallback.

Inspired by Claude Code's withRetry.ts — exponential backoff 500ms * 2^n,
25% jitter, configurable max retries, and optional fallback model on
repeated failures.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_RETRIES = 3
BASE_DELAY_S = 0.5
MAX_DELAY_S = 32.0
JITTER_FACTOR = 0.25


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay_s: float = BASE_DELAY_S
    max_delay_s: float = MAX_DELAY_S
    jitter_factor: float = JITTER_FACTOR
    fallback_model: str = ""


class RetriesExhaustedError(Exception):
    """All retry attempts failed."""

    def __init__(self, last_error: Exception, attempts: int) -> None:
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(f"Failed after {attempts} attempts: {last_error}")


class FallbackTriggeredError(Exception):
    """Retry limit hit — caller should switch to fallback_model."""

    def __init__(self, fallback_model: str, last_error: Exception) -> None:
        self.fallback_model = fallback_model
        self.last_error = last_error
        super().__init__(f"Falling back to {fallback_model}: {last_error}")


def retry_delay(attempt: int, config: RetryConfig | None = None) -> float:
    """Compute delay for attempt N (1-indexed): base * 2^(n-1) + jitter, capped."""
    cfg = config or RetryConfig()
    base = min(cfg.base_delay_s * (2 ** (attempt - 1)), cfg.max_delay_s)
    jitter = random.random() * cfg.jitter_factor * base
    return base + jitter


def with_retry(
    fn,
    *args,
    config: RetryConfig | None = None,
    on_retry=None,
    **kwargs,
):
    """Call fn with retry logic. Returns fn's result or raises.

    Parameters
    ----------
    fn : callable
        The function to call.
    config : RetryConfig, optional
        Retry configuration.
    on_retry : callable, optional
        Called with (attempt, delay, error) before each retry sleep.
    """
    cfg = config or RetryConfig()

    last_error: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            if attempt == cfg.max_retries:
                if cfg.fallback_model:
                    raise FallbackTriggeredError(cfg.fallback_model, exc) from exc
                raise RetriesExhaustedError(exc, attempt) from exc

            delay = retry_delay(attempt, cfg)
            logger.warning(
                "Attempt %d/%d failed (%s), retrying in %.1fs...",
                attempt,
                cfg.max_retries,
                exc,
                delay,
            )
            if on_retry:
                on_retry(attempt, delay, exc)
            time.sleep(delay)

    raise RetriesExhaustedError(last_error or RuntimeError("unreachable"), cfg.max_retries)
