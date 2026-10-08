"""The single entry point the api and ui layers use to track and read tickers.
It hides the store, the updater and the crawler behind a small set of operations.
Callers never import storage or crawler directly.
"""

from livestocks.config import Settings
from livestocks.domain import PriceBar, TickerId, TrackedTicker, parse_ticker
from livestocks.services.models import TickerView, TrackResult
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
