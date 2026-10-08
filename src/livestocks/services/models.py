"""Read models returned by the forecast service.
TickerView bundles a tracked ticker with its extras for one page render.
TrackResult reports a submitted ticker and ForecastResult is what the API returns.
"""

from dataclasses import dataclass

from livestocks.domain import Extras, TickerId, TrackedTicker


@dataclass(frozen=True, slots=True)
class TickerView:
    """A tracked ticker together with its EPS, revenue and rating extras.
    extras is None until the first extras crawl succeeds.
    signature changes whenever anything the detail page shows has changed.
    """

    ticker: TrackedTicker
    extras: Extras | None
    extras_fetched_at: int | None

    @property
    def signature(self) -> tuple[int | None, str, str | None, int | None]:
        """Return a cheap tuple that differs whenever the rendered page would differ.
        Pages poll it and re-render only when it changes.
        It covers the forecast time, status, last error and extras time.
        """
        t = self.ticker
        return (t.fetched_at, t.status.value, t.last_error, self.extras_fetched_at)


@dataclass(frozen=True, slots=True)
class TrackResult:
    """Outcome of submitting a ticker for tracking.
    created is True for a new ticker and False if it was already tracked.
    Already-tracked tickers are retried, so a failed one gets another chance.
    """

    ticker: TickerId
    created: bool


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """A ticker's stored forecast as handed to API callers.
    view always carries a forecast; created says whether this request started tracking it.
    stale is True when the data is older than twice the refresh interval.
    """

    view: TickerView
    created: bool
    stale: bool
