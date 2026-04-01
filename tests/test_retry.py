"""retry.py 单元测试"""

import pytest

from harness.utils.retry import (
    FallbackTriggeredError,
    RetriesExhaustedError,
    RetryConfig,
    retry_delay,
    with_retry,
)


def test_retry_delay_increases_exponentially():
    cfg = RetryConfig(base_delay_s=1.0, jitter_factor=0.0)
    d1 = retry_delay(1, cfg)
    d2 = retry_delay(2, cfg)
    d3 = retry_delay(3, cfg)
    assert d1 == pytest.approx(1.0)
    assert d2 == pytest.approx(2.0)
    assert d3 == pytest.approx(4.0)


def test_retry_delay_capped():
    cfg = RetryConfig(base_delay_s=1.0, max_delay_s=3.0, jitter_factor=0.0)
    d5 = retry_delay(5, cfg)
    assert d5 == pytest.approx(3.0)


def test_retry_delay_jitter_within_range():
    cfg = RetryConfig(base_delay_s=1.0, jitter_factor=0.25)
    for _ in range(50):
        d = retry_delay(1, cfg)
        assert 1.0 <= d <= 1.25


def test_with_retry_succeeds_first_try():
    call_count = 0

    def fn():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = with_retry(fn, config=RetryConfig(max_retries=3, base_delay_s=0.001))
    assert result == "ok"
    assert call_count == 1


def test_with_retry_succeeds_after_failures():
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("not yet")
        return "done"

    result = with_retry(fn, config=RetryConfig(max_retries=3, base_delay_s=0.001))
    assert result == "done"
    assert len(attempts) == 3


def test_with_retry_exhausted():
    def fn():
        raise RuntimeError("always fails")

    with pytest.raises(RetriesExhaustedError) as exc_info:
        with_retry(fn, config=RetryConfig(max_retries=2, base_delay_s=0.001))
    assert exc_info.value.attempts == 2


def test_with_retry_fallback_triggered():
    def fn():
        raise RuntimeError("fails")

    with pytest.raises(FallbackTriggeredError) as exc_info:
        with_retry(
            fn,
            config=RetryConfig(max_retries=2, base_delay_s=0.001, fallback_model="gpt-4o"),
        )
    assert exc_info.value.fallback_model == "gpt-4o"


def test_on_retry_callback():
    retries = []

    def fn():
        if len(retries) < 2:
            retries.append(1)
            raise ValueError("fail")
        return "ok"

    def on_retry(attempt, delay, error):
        retries.append(("retry", attempt))

    result = with_retry(
        fn,
        config=RetryConfig(max_retries=3, base_delay_s=0.001),
        on_retry=on_retry,
    )
    assert result == "ok"
    assert any(isinstance(r, tuple) and r[0] == "retry" for r in retries)
