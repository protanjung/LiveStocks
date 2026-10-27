"""Serves the market dividend calendar, cached so visitors do not each query the scanner.
The calendar is cached per exchange for calendar_ttl seconds, Ex Date history for trap_ttl.
History is fetched in the background, so the calendar is served at once and gains trap stats later.
"""

import asyncio
import time
from dataclasses import replace

import httpx
from loguru import logger

from livestocks.config import Settings
from livestocks.crawler import ParseError, UpstreamError, fetch_calendar, fetch_trap_stats
from livestocks.domain import CalendarEntry, TrapStats
from livestocks.services.errors import CalendarUnavailableError

TRAP_LOOKUPS = 5  # Yahoo requests in flight at once while filling trap statistics
TRAP_RETRY = 900.0  # seconds before a failed or empty trap lookup is tried again


class CalendarService:
    """Return the dividend calendar of an exchange, refreshing it at most once per TTL.
    A single lock stops concurrent visitors from starting duplicate scans.
    Rows gain their Ex Date trap statistics as the background fill completes.
    """

    def __init__(self, settings: Settings):
        """Create the service with its own HTTP client and empty caches."""
        self._ttl = settings.calendar_ttl
        self._trap_ttl = float(settings.trap_ttl)
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)
        self._cache: dict[str, tuple[float, list[CalendarEntry]]] = {}
        self._traps: dict[str, tuple[float, TrapStats | None]] = {}
        self._lock = asyncio.Lock()
        self._fill_task: asyncio.Task[None] | None = None

    async def entries(self, exchange: str) -> list[CalendarEntry]:
        """Return the calendar rows of an exchange, fetching them when the cache is stale.
        Raises CalendarUnavailableError when the scan fails and nothing is cached yet.
        Rows carry the trap statistics known so far; the rest are fetched in the background.
        """
        rows = await self._rows(exchange.upper())
        self._ensure_traps(rows)
        return [self._with_trap(e) for e in rows]

    async def close(self) -> None:
        """Stop the background fill and close the HTTP client held by the service.
        Call it once at shutdown, after the pages have stopped asking for data.
        Closing twice is harmless because httpx ignores a second close.
        """
        task = self._fill_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._client.aclose()

    async def _rows(self, key: str) -> list[CalendarEntry]:
        """Return the cached scan rows of an exchange, running the scan when they are stale."""
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

    def _fresh(self, key: str) -> list[CalendarEntry] | None:
        """Return the cached rows of an exchange while they are within the TTL, else None."""
        cached = self._cache.get(key)
        if cached is None or time.monotonic() - cached[0] >= self._ttl:
            return None
        return cached[1]

    def _trap_key(self, entry: CalendarEntry) -> str:
        """Return the cache key of one stock's trap statistics."""
        return f"{entry.exchange}:{entry.symbol}"

    def _trap_fresh(self, entry: CalendarEntry) -> bool:
        """Return True when the stock's trap statistics, or a recent failed attempt, are cached."""
        cached = self._traps.get(self._trap_key(entry))
        return cached is not None and time.monotonic() - cached[0] < self._trap_ttl

    def _with_trap(self, entry: CalendarEntry) -> CalendarEntry:
        """Return the entry with its cached trap statistics, or unchanged when none are cached."""
        if not self._trap_fresh(entry):
            return entry
        stats = self._traps[self._trap_key(entry)][1]
        return entry if stats is None else replace(entry, trap=stats)

    def _ensure_traps(self, rows: list[CalendarEntry]) -> None:
        """Start the background fill for stocks without fresh trap stats, if none is running."""
        missing = [e for e in rows if not self._trap_fresh(e)]
        if not missing or (self._fill_task is not None and not self._fill_task.done()):
            return
        self._fill_task = asyncio.create_task(self._fill(missing))

    async def _fill(self, missing: list[CalendarEntry]) -> None:
        """Fetch trap statistics for the given stocks, TRAP_LOOKUPS at a time, and cache them.
        A failure or an empty result is cached too, but expires after TRAP_RETRY seconds.
        """
        gate = asyncio.Semaphore(TRAP_LOOKUPS)

        async def one(entry: CalendarEntry) -> None:
            async with gate:
                try:
                    stats = await fetch_trap_stats(self._client, entry.exchange, entry.symbol)
                except (UpstreamError, ParseError) as e:
                    logger.debug("no trap statistics for {}: {}", entry.symbol, e)
                    stats = None
            fetched = time.monotonic()
            if stats is None:
                fetched -= max(0.0, self._trap_ttl - TRAP_RETRY)
            self._traps[self._trap_key(entry)] = (fetched, stats)

        try:
            await asyncio.gather(*(one(e) for e in missing))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - a background fill must never take the service down
            logger.warning("trap statistics fill failed: {}", e)
