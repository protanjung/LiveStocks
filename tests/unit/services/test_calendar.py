import pytest

from livestocks.config import Settings
from livestocks.crawler import UpstreamError
from livestocks.domain import CalendarEntry, CalendarKind
from livestocks.services import CalendarService, CalendarUnavailableError

ENTRY = CalendarEntry("IDX", "SIDO", "PT Sido", 1, 2, 10.0, 10.8, CalendarKind.UPCOMING)


@pytest.fixture
def fetch(monkeypatch):
    calls: list[str] = []
    state: dict = {"rows": [ENTRY], "error": None}

    async def fake_fetch(client, exchange, now=None):
        calls.append(exchange)
        if state["error"] is not None:
            raise state["error"]
        return state["rows"]

    monkeypatch.setattr("livestocks.services.calendar.fetch_calendar", fake_fetch)
    return calls, state


class TestCalendarCache:
    async def test_rows_are_served_from_cache_within_the_ttl(self, fetch):
        calls, _ = fetch
        service = CalendarService(Settings(calendar_ttl=3600))

        first = await service.entries("idx")
        second = await service.entries("IDX")

        assert first == second == [ENTRY]
        assert calls == ["IDX"]
        await service.close()

    async def test_expired_cache_is_fetched_again(self, fetch):
        calls, _ = fetch
        service = CalendarService(Settings(calendar_ttl=0))

        await service.entries("IDX")
        await service.entries("IDX")

        assert calls == ["IDX", "IDX"]
        await service.close()

    async def test_failed_refresh_serves_the_previous_rows(self, fetch):
        _, state = fetch
        service = CalendarService(Settings(calendar_ttl=0))
        await service.entries("IDX")
        state["error"] = UpstreamError("scanner down")

        assert await service.entries("IDX") == [ENTRY]
        await service.close()

    async def test_failure_with_nothing_cached_raises_unavailable(self, fetch):
        _, state = fetch
        state["error"] = UpstreamError("scanner down")
        service = CalendarService(Settings(calendar_ttl=3600))

        with pytest.raises(CalendarUnavailableError):
            await service.entries("IDX")
        await service.close()
