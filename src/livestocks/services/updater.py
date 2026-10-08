"""Background loop that keeps every tracked ticker's forecast fresh.
It polls the store for due tickers and crawls them with bounded concurrency.
Outcomes, including failures with backoff, are written back to the store.
"""

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Awaitable, Callable

import httpx

from livestocks.config import Settings
from livestocks.crawler import CrawlError, CrawlResult, crawl_ticker
from livestocks.storage import Store

log = logging.getLogger("livestocks.updater")

Crawler = Callable[[str, str], Awaitable[CrawlResult]]


class Updater:
    """Polls the store for due tickers and crawls them under a concurrency limit.
    Pass a crawler to replace the real network crawl, for example in tests.
    The set of in-flight keys is exposed so the UI can show activity.
    """

    def __init__(self, store: Store, settings: Settings, crawler: Crawler | None = None):
        """Create an updater; pass ``crawler`` to replace the real network crawl (tests)."""
        self.store = store
        self.settings = settings
        self._crawler = crawler
        self._client: httpx.AsyncClient | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._sem = asyncio.Semaphore(settings.concurrency)
        self.fetching: set[str] = set()  # "EXCH:SYM" keys currently in flight, read by the UI

    async def start(self) -> None:
        """Start the polling loop as a background task.
        Creates the shared HTTP client when no crawler was injected.
        Also queues tickers that lack extras for an immediate refresh.
        """
        if self._crawler is None:
            self._client = httpx.AsyncClient(timeout=self.settings.request_timeout)
            self._crawler = self._default_crawl
            self.store.queue_missing_extras()
        self._task = asyncio.create_task(self._run(), name="livestocks-updater")

    async def stop(self) -> None:
        """Cancel the polling loop and close the HTTP client.
        Safe to call even if start() never ran.
        Registered as a NiceGUI shutdown hook.
        """
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._client:
            await self._client.aclose()

    def wake(self) -> None:
        """Run a sweep now instead of waiting for the next poll.
        Call it after adding or retrying a ticker so work starts immediately.
        Waking during a sweep schedules another one right after it.
        """
        self._wake.set()

    async def _default_crawl(self, exchange: str, symbol: str) -> CrawlResult:
        assert self._client is not None
        return await crawl_ticker(self._client, exchange, symbol)

    async def _run(self) -> None:
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("sweep failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self.settings.poll_interval)
            self._wake.clear()

    async def sweep(self) -> None:
        """Crawl every ticker that is due and wait for all of them to finish.
        Concurrency is limited by Settings.concurrency.
        Each ticker's outcome is recorded individually.
        """
        due = self.store.due()
        if due:
            await asyncio.gather(*(self._update(ex, sym) for ex, sym in due))

    async def _update(self, exchange: str, symbol: str) -> None:
        assert self._crawler is not None
        key = f"{exchange}:{symbol}"
        s = self.settings
        async with self._sem:
            self.fetching.add(key)
            try:
                if s.jitter_max:
                    await asyncio.sleep(random.uniform(0, s.jitter_max))
                result = await self._crawler(exchange, symbol)
                self.store.record_success(result.forecast, s.refresh_interval)
                if result.prices is not None:
                    self.store.upsert_prices(exchange, symbol, result.prices)
                if result.extras is not None:
                    self.store.save_extras(exchange, symbol, result.extras)
                log.info("updated %s", key)
            except CrawlError as e:
                log.warning("fetch %s failed: %s", key, e)
                self.store.record_failure(
                    exchange, symbol, str(e), s.refresh_interval, s.max_failures
                )
            except Exception as e:
                log.exception("unexpected error fetching %s", key)
                self.store.record_failure(
                    exchange,
                    symbol,
                    f"unexpected: {e.__class__.__name__}",
                    s.refresh_interval,
                    s.max_failures,
                )
            finally:
                self.fetching.discard(key)

    def next_sweep_in(self) -> int | None:
        """Return seconds until the next ticker is due, or None when nothing is tracked.
        Zero means something is due now.
        Used by the header status line.
        """
        nxt = self.store.next_due_at()
        return None if nxt is None else max(0, nxt - int(time.time()))
