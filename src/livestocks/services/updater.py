"""Background loop that keeps every tracked ticker's forecast fresh.
It polls the store for due tickers and starts one crawl task per ticker, bounded by a semaphore.
Callers can watch a ticker to learn when its running or next crawl has finished.
"""

import asyncio
import contextlib
import random
import time
from collections.abc import Awaitable, Callable

import httpx
from loguru import logger

from livestocks.config import Settings
from livestocks.crawler import CrawlError, CrawlResult, NotFoundError, UpstreamError, crawl_ticker
from livestocks.domain import ErrorKind
from livestocks.storage import Store

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
        self._inflight: dict[str, asyncio.Task[None]] = {}
        self._waiters: dict[str, list[asyncio.Future[None]]] = {}
        self.fetching: set[str] = set()  # "EXCH:SYM" keys currently crawling, read by the UI

    async def start(self) -> None:
        """Start the polling loop as a background task.
        Creates the shared HTTP client when no crawler was injected.
        Also queues tickers that lack extras for an immediate refresh.
        """
        if self._crawler is None:
            self._client = httpx.AsyncClient(timeout=self.settings.request_timeout)
            self._crawler = self._default_crawl
            await self.store.queue_missing_extras()
        self._task = asyncio.create_task(self._run(), name="livestocks-updater")

    async def stop(self) -> None:
        """Cancel the polling loop and every running crawl, then close the HTTP client.
        Anyone still watching a ticker is told the updater stopped.
        Safe to call even if start() never ran.
        """
        tasks = [t for t in [self._task, *self._inflight.values()] if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for key in list(self._waiters):
            self._resolve(key, UpstreamError("the updater stopped"))
        if self._client:
            await self._client.aclose()

    def wake(self) -> None:
        """Run a sweep now instead of waiting for the next poll.
        Call it after adding or retrying a ticker so work starts immediately.
        Waking during a sweep schedules another one right after it.
        """
        self._wake.set()

    def watch(self, key: str) -> asyncio.Future[None]:
        """Return a future that resolves when the next crawl of EXCHANGE:SYMBOL finishes.
        It yields None on success and raises the crawl's exception on failure.
        Register before reading the store so a crawl finishing in between is not missed.
        """
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.setdefault(key, []).append(future)
        return future

    def unwatch(self, key: str, future: asyncio.Future[None]) -> None:
        """Forget a future returned by watch(), for example after the caller timed out.
        Does nothing if it already resolved or was never registered.
        An exception set on a forgotten future is marked as retrieved to keep logs quiet.
        """
        waiting = self._waiters.get(key)
        if waiting and future in waiting:
            waiting.remove(future)
            if not waiting:
                del self._waiters[key]
        if future.done() and not future.cancelled():
            future.exception()

    async def drain(self) -> None:
        """Wait until every crawl that is currently running has finished.
        Mostly useful in tests and during a graceful shutdown.
        New crawls started meanwhile are not awaited.
        """
        await asyncio.gather(*list(self._inflight.values()), return_exceptions=True)

    async def _default_crawl(self, exchange: str, symbol: str) -> CrawlResult:
        assert self._client is not None
        return await crawl_ticker(self._client, exchange, symbol)

    async def _run(self) -> None:
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop must survive any single sweep failure
                logger.exception("sweep failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self.settings.poll_interval)
            self._wake.clear()

    async def sweep(self) -> None:
        """Start a crawl task for every due ticker that is not already being crawled.
        Returns at once without waiting for the crawls; use drain() for that.
        Concurrency is limited by Settings.concurrency.
        """
        for exchange, symbol in await self.store.due():
            key = f"{exchange}:{symbol}"
            if key in self._inflight:
                continue
            task = asyncio.create_task(self._update(exchange, symbol), name=f"crawl-{key}")
            self._inflight[key] = task
            task.add_done_callback(lambda _done, k=key: self._inflight.pop(k, None))

    async def _update(self, exchange: str, symbol: str) -> None:
        key = f"{exchange}:{symbol}"
        outcome: BaseException | None = None
        try:
            async with self._sem:
                outcome = await self._crawl_and_record(exchange, symbol)
        except asyncio.CancelledError:
            outcome = UpstreamError("the crawl was cancelled")
            raise
        finally:
            self._resolve(key, outcome)

    async def _crawl_and_record(self, exchange: str, symbol: str) -> BaseException | None:
        """Crawl one ticker and store the result; return the failure, or None on success."""
        assert self._crawler is not None
        key = f"{exchange}:{symbol}"
        s = self.settings
        self.fetching.add(key)
        try:
            if s.jitter_max:
                await asyncio.sleep(random.uniform(0, s.jitter_max))
            result = await self._crawler(exchange, symbol)
            await self.store.record_success(result.forecast, s.refresh_interval)
            if result.prices is not None:
                await self.store.upsert_prices(exchange, symbol, result.prices)
            if result.extras is not None:
                await self.store.save_extras(exchange, symbol, result.extras)
            logger.bind(ticker=key).info("updated")
            return None
        except CrawlError as e:
            logger.bind(ticker=key).warning("fetch failed: {}", e)
            kind = ErrorKind.NOT_FOUND if isinstance(e, NotFoundError) else ErrorKind.UPSTREAM
            await self.store.record_failure(
                exchange, symbol, str(e), s.refresh_interval, s.max_failures, kind=kind
            )
            return e
        except Exception as e:  # noqa: BLE001 - a bug in one crawl must not stop the others
            logger.bind(ticker=key).exception("unexpected error while fetching")
            failure = UpstreamError(f"unexpected: {e.__class__.__name__}")
            await self.store.record_failure(
                exchange,
                symbol,
                str(failure),
                s.refresh_interval,
                s.max_failures,
                kind=ErrorKind.UPSTREAM,
            )
            return failure
        finally:
            self.fetching.discard(key)

    def _resolve(self, key: str, error: BaseException | None) -> None:
        for future in self._waiters.pop(key, []):
            if future.done():
                continue
            if error is None:
                future.set_result(None)
            else:
                future.set_exception(error)

    async def next_sweep_in(self) -> int | None:
        """Return seconds until the next ticker is due, or None when nothing is tracked.
        Zero means something is due now.
        Used by the header status line.
        """
        nxt = await self.store.next_due_at()
        return None if nxt is None else max(0, nxt - int(time.time()))
