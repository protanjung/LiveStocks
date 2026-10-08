"""Background loop that keeps every tracked ticker's forecast fresh."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

import httpx

from .config import Settings
from .models import Extras, Forecast
from .prices import fetch_prices
from .quotes import fetch_extras
from .scraper import ScrapeError, fetch_forecast
from .store import Store

log = logging.getLogger("livestocks.updater")

Fetcher = Callable[[str, str], Awaitable[Forecast]]
PriceFetcher = Callable[[str, str], Awaitable[list[tuple[int, float]]]]
ExtrasFetcher = Callable[[str, str], Awaitable[Extras]]


class Updater:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        fetcher: Fetcher | None = None,
        price_fetcher: PriceFetcher | None = None,
        extras_fetcher: ExtrasFetcher | None = None,
    ):
        self.store = store
        self.settings = settings
        self._fetcher = fetcher
        self._price_fetcher = price_fetcher
        self._extras_fetcher = extras_fetcher
        self._client: httpx.AsyncClient | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._sem = asyncio.Semaphore(settings.concurrency)
        self.fetching: set[str] = set()  # "EXCH:SYM" keys currently in flight, read by the UI

    async def start(self) -> None:
        if self._fetcher is None:
            self._client = httpx.AsyncClient(timeout=self.settings.request_timeout)
            self._fetcher = self._default_fetch
            if self._price_fetcher is None:
                self._price_fetcher = self._default_prices
            if self._extras_fetcher is None:
                self._extras_fetcher = fetch_extras
            self.store.queue_missing_extras()
        self._task = asyncio.create_task(self._run(), name="livestocks-updater")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._client:
            await self._client.aclose()

    def wake(self) -> None:
        """Run a sweep now instead of waiting for the next poll."""
        self._wake.set()

    async def _default_fetch(self, exchange: str, symbol: str) -> Forecast:
        assert self._client is not None
        return await fetch_forecast(self._client, exchange, symbol)

    async def _default_prices(self, exchange: str, symbol: str) -> list[tuple[int, float]]:
        assert self._client is not None
        return await fetch_prices(self._client, exchange, symbol)

    async def _run(self) -> None:
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("sweep failed")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.settings.poll_interval)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def sweep(self) -> None:
        due = self.store.due()
        if due:
            await asyncio.gather(*(self._update(ex, sym) for ex, sym in due))

    async def _update(self, exchange: str, symbol: str) -> None:
        key = f"{exchange}:{symbol}"
        s = self.settings
        async with self._sem:
            self.fetching.add(key)
            try:
                if s.jitter_max:
                    await asyncio.sleep(random.uniform(0, s.jitter_max))
                forecast = await self._fetcher(exchange, symbol)  # type: ignore[misc]
                self.store.record_success(forecast, s.refresh_interval)
                await self._update_prices(exchange, symbol)
                await self._update_extras(exchange, symbol)
                log.info("updated %s", key)
            except asyncio.CancelledError:
                raise
            except ScrapeError as e:
                log.warning("fetch %s failed: %s", key, e)
                self.store.record_failure(exchange, symbol, str(e), s.refresh_interval, s.max_failures)
            except Exception as e:
                log.exception("unexpected error fetching %s", key)
                self.store.record_failure(
                    exchange, symbol, f"unexpected: {e.__class__.__name__}", s.refresh_interval, s.max_failures
                )
            finally:
                self.fetching.discard(key)

    async def _update_prices(self, exchange: str, symbol: str) -> None:
        """Best-effort: a missing price history must not fail the forecast update."""
        if self._price_fetcher is None:
            return
        try:
            self.store.upsert_prices(exchange, symbol, await self._price_fetcher(exchange, symbol))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("price history %s:%s unavailable: %s", exchange, symbol, e)

    async def _update_extras(self, exchange: str, symbol: str) -> None:
        """Best-effort, like prices: rating counts and EPS/revenue are extras, not the core forecast."""
        if self._extras_fetcher is None:
            return
        try:
            self.store.save_extras(exchange, symbol, await self._extras_fetcher(exchange, symbol))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("extras %s:%s unavailable: %s", exchange, symbol, e)

    def next_sweep_in(self) -> int | None:
        """Seconds until the next ticker is due, for display."""
        nxt = self.store.next_due_at()
        return None if nxt is None else max(0, nxt - int(time.time()))
