import pytest

from livestocks.crawler import NotFoundError, UpstreamError
from livestocks.crawler.retry import with_retries


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr("livestocks.crawler.retry.asyncio.sleep", fake_sleep)
    return recorded


class TestWithRetries:
    async def test_returns_first_success_without_sleeping(self, sleeps):
        async def ok():
            return "done"

        assert await with_retries(ok) == "done"
        assert sleeps == []

    async def test_retries_upstream_errors_with_exponential_backoff(self, sleeps):
        calls = 0

        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise UpstreamError("HTTP 429")
            return "ok"

        assert await with_retries(flaky, attempts=3, base_delay=2) == "ok"
        assert calls == 3 and sleeps == [2, 4]

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
