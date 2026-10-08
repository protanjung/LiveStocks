"""Immutable value objects shared by every layer: forecasts, estimates, tracked tickers."""

from dataclasses import dataclass
from enum import StrEnum


class TickerStatus(StrEnum):
    """Where a tracked ticker stands in its crawl lifecycle."""

    PENDING = "pending"
    OK = "ok"
    ERROR = "error"
    FAILED = "failed"


class RatingTone(StrEnum):
    """Sentiment bucket of an analyst consensus, used for colouring."""

    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class TickerId:
    """Exchange and symbol that together identify one ticker."""

    exchange: str
    symbol: str

    @property
    def key(self) -> str:
        """Return the ``EXCHANGE:SYMBOL`` form used in URLs, logs and caches."""
        return f"{self.exchange}:{self.symbol}"


@dataclass(frozen=True, slots=True)
class Forecast:
    """One snapshot of TradingView's analyst forecast for a ticker."""

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
    """One daily close of a ticker's price history."""

    ts: int  # unix seconds
    close: float


@dataclass(frozen=True, slots=True)
class Period:
    """One fiscal period of an EPS or revenue series."""

    label: str  # "2026" or "2026-Q2"
    actual: float | None
    estimate: float | None
    reported: bool

    @property
    def surprise(self) -> float | None:
        """Return (actual - estimate) / |estimate|, or None when either side is missing."""
        if self.actual is None or not self.estimate:
            return None
        return (self.actual - self.estimate) / abs(self.estimate)


@dataclass(frozen=True, slots=True)
class Extras:
    """Analyst rating breakdown and EPS / revenue actuals vs estimates."""

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
        """Return (label, analysts) from strong buy to strong sell, or None if any count is missing."""
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
    """Tracked ticker joined with its latest forecast (if any) and crawl status."""

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

    @property
    def key(self) -> str:
        """Return the ``EXCHANGE:SYMBOL`` form of this ticker."""
        return f"{self.exchange}:{self.symbol}"

    @property
    def status(self) -> TickerStatus:
        """Return the crawl lifecycle state derived from data and failure counters."""
        if self.dead:
            return TickerStatus.FAILED
        if self.forecast is None:
            return TickerStatus.ERROR if self.last_error else TickerStatus.PENDING
        return TickerStatus.OK

    @property
    def upside(self) -> float | None:
        """Return the average price target's distance from the current price as a fraction."""
        f = self.forecast
        if f and f.pt_avg and f.price:
            return f.pt_avg / f.price - 1
        return None
