"""Serves the market dividend calendar, cached so visitors do not each query the scanner.
The cache is kept per exchange and expires after calendar_ttl seconds.
When a refresh fails, the last good calendar is served instead of an error.
"""

import asyncio
import time

import httpx

from livestocks.config import Settings
from livestocks.crawler import ParseError, UpstreamError, fetch_calendar
from livestocks.domain import CalendarEntry
from livestocks.services.errors import CalendarUnavailableError


class CalendarService:
    """Return the dividend calendar of an exchange, refreshing it at most once per TTL.
    A single lock stops concurrent visitors from starting duplicate scans.
    Each exchange keeps its own cached rows and fetch time.
    """

    def __init__(self, settings: Settings):
        """Create the service with its own HTTP client and an empty cache."""
        self._ttl = settings.calendar_ttl
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)
        self._cache: dict[str, tuple[float, list[CalendarEntry]]] = {}
        self._lock = asyncio.Lock()

    async def entries(self, exchange: str) -> list[CalendarEntry]:
        """Return the calendar rows of an exchange, fetching them when the cache is stale.
        Raises CalendarUnavailableError when the scan fails and nothing is cached yet.
        A failed refresh keeps serving the rows fetched last time.
        """
        key = exchange.upper()
        cached = self._fresh(key)
        if cached is not None:
            return cached
        async with self._lock:
            cached = self._fresh(key)
            if cached is not None:
                return cached
            previous = self._cache.get(key)
            try:
                rows = await fetch_calendar(self._client, key)
            except (UpstreamError, ParseError) as e:
                if previous is not None:
                    return previous[1]
                raise CalendarUnavailableError(
                    "the dividend calendar is unavailable right now"
                ) from e
            self._cache[key] = (time.monotonic(), rows)
            return rows

    async def close(self) -> None:
        """Close the HTTP client held by the service.
        Call it once at shutdown, after the pages have stopped asking for data.
        Closing twice is harmless because httpx ignores a second close.
        """
        await self._client.aclose()

    def _fresh(self, key: str) -> list[CalendarEntry] | None:
        """Return the cached rows of an exchange while they are within the TTL, else None."""
        cached = self._cache.get(key)
        if cached is None or time.monotonic() - cached[0] >= self._ttl:
            return None
        return cached[1]
