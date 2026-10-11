"""Immutable value objects shared by every layer.
Forecasts, estimates, price bars and tracked tickers are frozen dataclasses.
Fixed value sets are StrEnums that compare equal to their plain strings.
"""

from dataclasses import dataclass
from enum import StrEnum


class TickerStatus(StrEnum):
    """Where a tracked ticker stands in its crawl lifecycle.
    PENDING has no data yet, OK has a forecast, ERROR failed but will be retried,
    and FAILED has used up its retries.
    """

    PENDING = "pending"
    OK = "ok"
    ERROR = "error"
    FAILED = "failed"


class RatingTone(StrEnum):
    """Sentiment bucket of an analyst consensus, used for colouring.
    BUY, HOLD and SELL group the five rating labels; NONE means no rating.
    Values are plain strings, so they double as CSS class names.
    """

    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    NONE = "none"


class ErrorKind(StrEnum):
    """Why the last crawl of a ticker failed.
    NOT_FOUND means TradingView has no such ticker; retrying will not help.
    UPSTREAM covers network, rate-limit, server and parsing problems that may pass.
    """

    NOT_FOUND = "not_found"
    UPSTREAM = "upstream"


@dataclass(frozen=True, slots=True)
class TickerId:
    """Exchange and symbol that together identify one ticker.
    Frozen, so it can be used as a dictionary key.
    key gives the EXCHANGE:SYMBOL text form.
    """

    exchange: str
    symbol: str

    @property
    def key(self) -> str:
        """Return the EXCHANGE:SYMBOL form used in URLs, logs and caches.
        For example IDX:TLKM.
        Both parts are already upper-case after parsing.
        """
        return f"{self.exchange}:{self.symbol}"


@dataclass(frozen=True, slots=True)
class Forecast:
    """One snapshot of TradingView's analyst forecast for a ticker.
    Holds the price targets, rating score, price and next earnings date.
    Any field can be None when TradingView does not publish it.
    """

    exchange: str
    symbol: str
    name: str | None
    price: float | None
    change_pct: float | None
    pt_avg: float | None
    pt_high: float | None
    pt_low: float | None
    n_analysts: int | None
    rating_mark: float | None  # 1 = strong buy ... 5 = strong sell
    n_ratings: int | None
    ath: float | None
    next_earnings: int | None  # unix seconds


@dataclass(frozen=True, slots=True)
class PriceBar:
    """One daily close of a ticker's price history.
    ts is a unix timestamp in seconds.
    close is in the ticker's trading currency.
    """

    ts: int  # unix seconds
    close: float


@dataclass(frozen=True, slots=True)
class Period:
    """One fiscal period of an EPS or revenue series.
    label is a year such as 2026 or a quarter such as 2026-Q2.
    actual is None until the period has been reported.
    """

    label: str  # "2026" or "2026-Q2"
    actual: float | None
    estimate: float | None
    reported: bool

    @property
    def surprise(self) -> float | None:
        """Return (actual - estimate) / |estimate|, or None if either value is missing.
        A positive value means the company beat the estimate.
        A zero estimate also gives None, to avoid dividing by zero.
        """
        if self.actual is None or not self.estimate:
            return None
        return (self.actual - self.estimate) / abs(self.estimate)


@dataclass(frozen=True, slots=True)
class Extras:
    """Analyst rating breakdown plus EPS and revenue actuals versus estimates.
    The five counts are analysts per rating, strong buy to strong sell.
    Each series has an annual (fy) and a quarterly (fq) variant.
    """

    strong_buy: int | None
    buy: int | None
    hold: int | None
    sell: int | None
    strong_sell: int | None
    eps_fy: tuple[Period, ...]
    eps_fq: tuple[Period, ...]
    rev_fy: tuple[Period, ...]
    rev_fq: tuple[Period, ...]

    @property
    def rating_counts(self) -> list[tuple[str, int]] | None:
        """Return (label, analysts) pairs from strong buy to strong sell.
        Returns None when any of the five counts is missing.
        The order matches the arcs of the consensus gauge.
        """
        counts = (self.strong_buy, self.buy, self.hold, self.sell, self.strong_sell)
        labels = ("Strong buy", "Buy", "Hold", "Sell", "Strong sell")
        result: list[tuple[str, int]] = []
        for label, count in zip(labels, counts, strict=True):
            if count is None:
                return None
            result.append((label, count))
        return result


@dataclass(frozen=True, slots=True)
class TrackedTicker:
    """A tracked ticker joined with its latest forecast and crawl status.
    forecast is None until the first successful crawl.
    The counters and timestamps drive scheduling and the status the UI shows.
    """

    exchange: str
    symbol: str
    name: str | None
    added_at: int
    last_fetch: int | None
    next_fetch: int
    last_error: str | None
    fail_count: int
    dead: bool
    forecast: Forecast | None
    fetched_at: int | None
    error_kind: ErrorKind | None = None

    @property
    def id(self) -> TickerId:
        """Return this ticker's exchange and symbol as a TickerId.
        Use it to address the ticker in service calls.
        Frozen, so it can be kept or used as a dictionary key.
        """
        return TickerId(self.exchange, self.symbol)

    @property
    def key(self) -> str:
        """Return the EXCHANGE:SYMBOL form of this ticker.
        Matches TickerId.key.
        Used as the key for in-flight crawls and UI rows.
        """
        return f"{self.exchange}:{self.symbol}"

    @property
    def status(self) -> TickerStatus:
        """Derive the crawl lifecycle state from the data and the failure counters.
        Dead tickers are FAILED, tickers without a forecast are ERROR or PENDING,
        and everything else is OK.
        """
        if self.dead:
            return TickerStatus.FAILED
        if self.forecast is None:
            return TickerStatus.ERROR if self.last_error else TickerStatus.PENDING
        return TickerStatus.OK

    @property
    def upside(self) -> float | None:
        """Return how far the average price target is from the current price.
        The result is a fraction: 0.47 means the target is 47% above the price.
        None when the price or the average target is missing.
        """
        f = self.forecast
        if f and f.pt_avg and f.price:
            return f.pt_avg / f.price - 1
        return None


@dataclass(frozen=True, slots=True)
class SuggestionReport:
    """One day's stock suggestions as delivered by the scheduled Claude routine.
    payload is the validated idx-suggestions JSON text, kept verbatim.
    date is the Jakarta trading date it is for and received_at is unix seconds.
    """

    date: str
    generated_at: str
    received_at: int
    payload: str
