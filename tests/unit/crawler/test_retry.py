import pytest

from livestocks.crawler import NotFoundError, UpstreamError
from livestocks.crawler.retry import with_retries


class TestWithRetries:
    async def test_returns_first_success_without_sleeping(self, retry_sleeps):
        async def ok():
            return "done"

        assert await with_retries(ok) == "done"
        assert retry_sleeps == []

    async def test_retries_upstream_errors_with_exponential_backoff(self, retry_sleeps):
        calls = 0

        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise UpstreamError("HTTP 429")
            return "ok"

        assert await with_retries(flaky, attempts=3, base_delay=2) == "ok"
        assert calls == 3
        first, second = retry_sleeps
        assert 2 <= first <= 3  # base delay plus up to 1 s of jitter
        assert 4 <= second <= 5  # doubled

    async def test_raises_the_last_error_when_attempts_run_out(self):
        async def always_down():
            raise UpstreamError("HTTP 503")

        with pytest.raises(UpstreamError, match="503"):
            await with_retries(always_down, attempts=2)

    async def test_other_errors_are_not_retried(self):
        calls = 0

        async def missing():
            nonlocal calls
            calls += 1
            raise NotFoundError("gone")

        with pytest.raises(NotFoundError):
            await with_retries(missing, attempts=3)
        assert calls == 1
