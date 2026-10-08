from dataclasses import dataclass


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class TickerRow:
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
        return f"{self.exchange}:{self.symbol}"

    @property
    def status(self) -> str:
        if self.dead:
            return "failed"
        if self.forecast is None:
            return "error" if self.last_error else "pending"
        return "ok"

    @property
    def upside(self) -> float | None:
        f = self.forecast
        if f and f.pt_avg and f.price:
            return f.pt_avg / f.price - 1
        return None


@dataclass(frozen=True)
class Period:
    """One fiscal period of an EPS or revenue series."""

    label: str  # "2026" or "2026-Q2"
    actual: float | None
    estimate: float | None
    reported: bool

    @property
    def surprise(self) -> float | None:
        if self.actual is None or not self.estimate:
            return None
        return (self.actual - self.estimate) / abs(self.estimate)


@dataclass(frozen=True)
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
        counts = (self.strong_buy, self.buy, self.hold, self.sell, self.strong_sell)
        if any(c is None for c in counts):
            return None
        return list(zip(("Strong buy", "Buy", "Hold", "Sell", "Strong sell"), counts))


def rating_label(mark: float | None) -> tuple[str, str]:
    """(label, tone) with tone in buy/hold/sell/none."""
    if mark is None:
        return "No rating", "none"
    if mark < 1.5:
        return "Strong buy", "buy"
    if mark < 2.5:
        return "Buy", "buy"
    if mark < 3.5:
        return "Neutral", "hold"
    if mark < 4.5:
        return "Sell", "sell"
    return "Strong sell", "sell"
