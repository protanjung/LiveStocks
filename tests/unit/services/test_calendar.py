import asyncio

import pytest

from livestocks.config import Settings
from livestocks.crawler import UpstreamError
from livestocks.domain import CalendarEntry, CalendarKind, ExDateEvent, TrapStats
from livestocks.services import CalendarService, CalendarUnavailableError

ENTRY = CalendarEntry("IDX", "SIDO", "PT Sido", 1, 2, 10.0, 10.8, CalendarKind.UPCOMING)
STATS = TrapStats((ExDateEvent(1, 10.0, 500.0, 495.0, 2),) * 3)


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


@pytest.fixture
def traps(monkeypatch):
    """Stand-in for the Yahoo history step; set ``result`` or ``error`` to steer it."""
    state: dict = {"calls": [], "result": STATS, "error": None, "gate": None}

    async def fake_trap(client, exchange, symbol):
        state["calls"].append(symbol)
        if state["gate"] is not None:
            await state["gate"].wait()
        if state["error"] is not None:
            raise state["error"]
        return state["result"]

    monkeypatch.setattr("livestocks.services.calendar.fetch_trap_stats", fake_trap)
    return state


class TestCalendarCache:
    async def test_rows_are_served_from_cache_within_the_ttl(self, fetch, traps):
        calls, _ = fetch
        service = CalendarService(Settings(calendar_ttl=3600))

        first = await service.entries("idx")
        second = await service.entries("IDX")

        assert [e.symbol for e in first] == [e.symbol for e in second] == ["SIDO"]
        assert calls == ["IDX"]
        await service.close()

    async def test_expired_cache_is_fetched_again_in_the_background(self, fetch, traps):
        calls, _ = fetch
        service = CalendarService(Settings(calendar_ttl=0))

        await service.entries("IDX")
        await service.entries("IDX")
        await service._refresh_tasks["IDX"]

        assert calls == ["IDX", "IDX"]
        await service.close()

    async def test_expired_rows_are_served_at_once_while_the_refresh_runs(self, fetch, traps):
        calls, state = fetch
        service = CalendarService(Settings(calendar_ttl=0))
        await service.entries("IDX")
        gate = asyncio.Event()

        async def slow(client, exchange, now=None):
            calls.append(exchange)
            await gate.wait()
            return state["rows"]

        import livestocks.services.calendar as module

        original = module.fetch_calendar
        module.fetch_calendar = slow
        try:
            rows = await asyncio.wait_for(service.entries("IDX"), timeout=1)
        finally:
            gate.set()
            await service._refresh_tasks["IDX"]
            module.fetch_calendar = original

        assert [e.symbol for e in rows] == ["SIDO"]
        await service.close()

    async def test_warm_loads_the_calendar_before_anyone_asks(self, fetch, traps):
        calls, _ = fetch
        service = CalendarService(Settings())

        service.warm("idx")
        await service._warm_task
        await service.entries("IDX")

        assert calls == ["IDX"]
        await service.close()

    async def test_warm_failure_is_swallowed(self, fetch, traps):
        _, state = fetch
        state["error"] = UpstreamError("scanner down")
        service = CalendarService(Settings())

        service.warm("IDX")
        await service._warm_task

        assert service._warm_task.exception() is None
        await service.close()

    async def test_failed_refresh_serves_the_previous_rows(self, fetch, traps):
        _, state = fetch
        service = CalendarService(Settings(calendar_ttl=0))
        await service.entries("IDX")
        state["error"] = UpstreamError("scanner down")

        assert [e.symbol for e in await service.entries("IDX")] == ["SIDO"]
        await service.close()

    async def test_failure_with_nothing_cached_raises_unavailable(self, fetch, traps):
        _, state = fetch
        state["error"] = UpstreamError("scanner down")
        service = CalendarService(Settings(calendar_ttl=3600))

        with pytest.raises(CalendarUnavailableError):
            await service.entries("IDX")
        await service.close()


class TestTrapFill:
    async def test_rows_are_returned_before_the_history_arrives(self, fetch, traps):
        traps["gate"] = asyncio.Event()
        service = CalendarService(Settings())

        rows = await service.entries("IDX")

        assert rows[0].trap is None
        traps["gate"].set()
        await service.close()

    async def test_trap_statistics_appear_once_the_fill_completes(self, fetch, traps):
        service = CalendarService(Settings())
        await service.entries("IDX")
        await service._fill_task

        rows = await service.entries("IDX")

        assert rows[0].trap == STATS
        await service.close()

    async def test_fresh_statistics_are_not_fetched_again(self, fetch, traps):
        service = CalendarService(Settings(calendar_ttl=0))
        await service.entries("IDX")
        await service._fill_task
        await service.entries("IDX")

        assert traps["calls"] == ["SIDO"]
        await service.close()

    async def test_expired_statistics_are_fetched_again(self, fetch, traps):
        service = CalendarService(Settings(trap_ttl=0))
        await service.entries("IDX")
        await service._fill_task
        await service.entries("IDX")
        await service._fill_task

        assert traps["calls"] == ["SIDO", "SIDO"]
        await service.close()

    async def test_a_failed_lookup_leaves_the_row_without_statistics_and_is_not_retried_at_once(
        self, fetch, traps
    ):
        traps["error"] = UpstreamError("yahoo down")
        service = CalendarService(Settings())
        await service.entries("IDX")
        await service._fill_task

        rows = await service.entries("IDX")

        assert rows[0].trap is None
        assert traps["calls"] == ["SIDO"]
        await service.close()

    async def test_only_one_fill_runs_at_a_time(self, fetch, traps):
        traps["gate"] = asyncio.Event()
        service = CalendarService(Settings())
        await service.entries("IDX")
        first = service._fill_task

        await service.entries("IDX")

        assert service._fill_task is first
        traps["gate"].set()
        await service.close()

    async def test_closing_cancels_a_running_fill(self, fetch, traps):
        traps["gate"] = asyncio.Event()
        service = CalendarService(Settings())
        await service.entries("IDX")
        await asyncio.sleep(0)

        await service.close()

        assert service._fill_task.done()
