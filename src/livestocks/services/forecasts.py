"""The single entry point the api and ui layers use to track and read tickers.
It hides the store, the updater and the crawler behind a small set of operations.
Callers never import storage or crawler directly.
"""

import asyncio
import time

from livestocks.config import Settings
from livestocks.crawler import CrawlError, NotFoundError
from livestocks.domain import (
    ErrorKind,
    PriceBar,
    TickerId,
    TickerStatus,
    TrackedTicker,
    parse_ticker,
)
from livestocks.services.errors import (
    CrawlTimeoutError,
    ServiceError,
    TickerNotFoundError,
    UpstreamUnavailableError,
)
from livestocks.services.models import ForecastResult, TickerView, TrackResult
from livestocks.services.updater import Updater
from livestocks.storage import Store


class ForecastService:
    """Track tickers and read their forecasts, history and crawl activity.
    Writes wake the updater so new work starts at once.
    Reads are cheap enough to call on every page refresh.
    """

    def __init__(self, store: Store, updater: Updater, settings: Settings):
        """Create the service over an open store and a started or startable updater."""
        self._store = store
        self._updater = updater
        self._settings = settings

    def list_tickers(self) -> list[TrackedTicker]:
        """Return every tracked ticker with its latest forecast, oldest first.
        Tickers that have not been crawled yet have no forecast.
        Used by the dashboard table and its summary cards.
        """
        return self._store.rows()

    def get_ticker(self, ticker: TickerId) -> TickerView | None:
        """Return one tracked ticker with its extras, or None if it is not tracked.
        The extras are None until the first successful extras crawl.
        Used by the detail page and its change detection.
        """
        row = self._store.row(ticker.exchange, ticker.symbol)
        if row is None:
            return None
        stored = self._store.extras(ticker.exchange, ticker.symbol)
        return TickerView(row, stored[1] if stored else None, stored[0] if stored else None)

    def price_history(self, ticker: TickerId, since: int = 0) -> list[PriceBar]:
        """Return daily closes since a unix timestamp, oldest first; 0 means everything.
        Falls back to the prices saved with each forecast when no history was crawled.
        Exchanges without a price feed therefore still get a short line.
        """
        bars = self._store.prices(ticker.exchange, ticker.symbol, since)
        if len(bars) >= 2:
            return bars
        snapshots = [
            PriceBar(ts, forecast.price)
            for ts, forecast in self._store.history(ticker.exchange, ticker.symbol, since)
            if forecast.price
        ]
        return snapshots or bars

    def fetching(self) -> frozenset[str]:
        """Return the EXCHANGE:SYMBOL keys that are being crawled right now.
        The dashboard uses it for spinners and the header status line.
        The snapshot is immutable, so it is safe to keep.
        """
        return frozenset(self._updater.fetching)

    def seconds_until_next_refresh(self) -> int | None:
        """Return seconds until the next ticker is due, or None when nothing is tracked.
        Zero means a refresh is due now.
        Shown in the header status line.
        """
        return self._updater.next_sweep_in()

    def track(self, raw: str) -> TrackResult:
        """Start tracking a ticker given as text such as TLKM or NASDAQ:AAPL.
        Raises InvalidTickerError for malformed text; an existing ticker is retried instead.
        Wakes the updater so the first crawl begins immediately.
        """
        ticker = parse_ticker(raw, self._settings.default_exchange)
        created = self._store.add_ticker(ticker.exchange, ticker.symbol)
        if not created:
            self._store.retry(ticker.exchange, ticker.symbol)
        self._updater.wake()
        return TrackResult(ticker, created)

    def remove(self, ticker: TickerId) -> None:
        """Stop tracking a ticker and delete everything stored for it.
        Does nothing for an unknown ticker.
        A crawl already running for it discards its result.
        """
        self._store.remove_ticker(ticker.exchange, ticker.symbol)

    def retry(self, ticker: TickerId) -> None:
        """Clear a ticker's failure state and crawl it again right away.
        Revives tickers that were marked failed.
        Does nothing for an unknown ticker.
        """
        self._store.retry(ticker.exchange, ticker.symbol)
        self._updater.wake()

    async def get_or_track(self, raw: str, wait_seconds: float | None = None) -> ForecastResult:
        """Return a ticker's stored forecast, tracking it and waiting for its first crawl if new.
        Raises InvalidTickerError or a ServiceError subclass: not found, upstream or timeout.
        wait_seconds caps the wait and defaults to Settings.api_wait_seconds.
        """
        ticker = parse_ticker(raw, self._settings.default_exchange)
        limit = self._settings.api_wait_seconds if wait_seconds is None else wait_seconds
        # Watch before reading the store so a crawl that finishes in between cannot be missed.
        waiter = self._updater.watch(ticker.key)
        try:
            created = self._store.add_ticker(ticker.exchange, ticker.symbol)
            ready = self._ready(self.get_ticker(ticker), created)
            if ready is not None:
                return ready
            self._updater.wake()
            try:
                await asyncio.wait_for(asyncio.shield(waiter), limit)
            except TimeoutError as e:
                raise CrawlTimeoutError(
                    f"{ticker.key} was not ready within {limit:g} s; try again shortly"
                ) from e
            except CrawlError as e:
                raise _as_service_error(e) from e
            ready = self._ready(self.get_ticker(ticker), created)
            if ready is None:
                raise UpstreamUnavailableError(f"the crawl of {ticker.key} produced no data")
            return ready
        finally:
            self._updater.unwatch(ticker.key, waiter)

    def _ready(self, view: TickerView | None, created: bool) -> ForecastResult | None:
        """Return the answer if data exists, None if still pending, or raise for a known failure."""
        if view is None:
            return None
        ticker = view.ticker
        if ticker.forecast is not None:
            return ForecastResult(view, created, self._is_stale(ticker))
        if ticker.status in (TickerStatus.ERROR, TickerStatus.FAILED):
            if ticker.error_kind is ErrorKind.NOT_FOUND:
                raise TickerNotFoundError(ticker.last_error or "ticker not found")
            raise UpstreamUnavailableError(ticker.last_error or "the upstream request failed")
        return None

    def _is_stale(self, ticker: TrackedTicker) -> bool:
        if ticker.fetched_at is None:
            return False
        return time.time() - ticker.fetched_at > 2 * self._settings.refresh_interval


def _as_service_error(error: CrawlError) -> ServiceError:
    if isinstance(error, NotFoundError):
        return TickerNotFoundError(str(error))
    return UpstreamUnavailableError(str(error))
