"""Pydantic models that define the JSON the HTTP API returns.
ForecastResponse is built from a service ForecastResult; ErrorResponse is the shared error body.
Percentages are plain numbers in percent, for example 46.9 means 46.9%.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from livestocks.domain import Extras, Forecast, Period, TickerStatus, TrackedTicker, rating_label
from livestocks.services import ForecastResult


class TickerOut(BaseModel):
    """Identity of the ticker the answer is about.
    exchange and symbol are upper case, for example IDX and TLKM.
    name is the company name TradingView shows, when known.
    """

    exchange: str = Field(examples=["IDX"])
    symbol: str = Field(examples=["TLKM"])
    name: str | None = Field(default=None, examples=["PT Telkom Indonesia (Persero) Tbk Class B"])


class PriceOut(BaseModel):
    """Last price, today's change and the all-time high.
    Prices are in the ticker's trading currency.
    Any value is null when TradingView does not publish it.
    """

    last: float | None
    change_pct: float | None = Field(description="Change since the previous close, in percent.")
    all_time_high: float | None


class PriceTargetOut(BaseModel):
    """Analyst 1-year price targets.
    average, high and low come from the analysts who published a target.
    upside_pct relates the average target to the last price.
    """

    average: float | None
    high: float | None
    low: float | None
    upside_pct: float | None = Field(
        description="Average target above (+) or below (-) the last price, in percent."
    )
    analysts: int | None = Field(description="Number of analysts who gave a target.")


class RatingCountsOut(BaseModel):
    """Number of analysts per rating.
    The five counts add up to the number of analysts who rated in the last 3 months.
    They come from the extras crawl, so they can be missing.
    """

    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


class RatingOut(BaseModel):
    """Consensus rating: score from 1 (strong buy) to 5 (strong sell) and its label.
    label is Strong buy, Buy, Neutral, Sell or Strong sell, or No rating without a score.
    counts break the consensus down by analyst.
    """

    score: float | None
    label: str
    total: int | None = Field(description="Number of analysts who rated in the last 3 months.")
    counts: RatingCountsOut | None = Field(
        description="Per-rating counts; null until the extras crawl has succeeded."
    )


class PeriodOut(BaseModel):
    """One fiscal period of an EPS or revenue series.
    Periods that are not reported yet have only an estimate.
    Revenue is in the reporting currency, not abbreviated.
    """

    period: str = Field(examples=["2026", "2026-Q2"])
    reported: bool
    actual: float | None
    estimate: float | None
    surprise_pct: float | None = Field(description="(actual - estimate) / |estimate|, in percent.")


class SeriesOut(BaseModel):
    """Annual and quarterly periods of one metric, oldest first.
    Up to 11 annual and 16 quarterly periods, including future estimates.
    Periods with neither an actual nor an estimate are left out.
    """

    annual: list[PeriodOut]
    quarterly: list[PeriodOut]


class EstimatesOut(BaseModel):
    """EPS and revenue actuals versus analyst estimates, including future periods.
    eps is earnings per share; revenue is total revenue.
    Both come from the extras crawl.
    """

    eps: SeriesOut
    revenue: SeriesOut


class ForecastResponse(BaseModel):
    """The stored analyst forecast for one ticker.
    created is true when this request started tracking the ticker.
    stale is true when the data is older than twice the refresh interval.
    """

    ticker: TickerOut
    status: TickerStatus
    created: bool
    fetched_at: datetime
    stale: bool
    price: PriceOut
    price_target: PriceTargetOut
    rating: RatingOut
    next_earnings: datetime | None
    estimates: EstimatesOut | None = Field(
        description="EPS and revenue series; null until the extras crawl has succeeded."
    )

    @classmethod
    def from_result(cls, result: ForecastResult) -> "ForecastResponse":
        """Build the response from a service result whose ticker has a forecast.
        Raises ValueError if the ticker has no stored forecast.
        Percent fields are converted from fractions here.
        """
        ticker = result.view.ticker
        forecast = ticker.forecast
        if forecast is None or ticker.fetched_at is None:
            raise ValueError("a forecast response needs a stored forecast")
        extras = result.view.extras
        label, _ = rating_label(forecast.rating_mark)
        return cls(
            ticker=TickerOut(exchange=ticker.exchange, symbol=ticker.symbol, name=ticker.name),
            status=ticker.status,
            created=result.created,
            fetched_at=datetime.fromtimestamp(ticker.fetched_at, UTC),
            stale=result.stale,
            price=PriceOut(
                last=forecast.price, change_pct=forecast.change_pct, all_time_high=forecast.ath
            ),
            price_target=_price_target(ticker, forecast),
            rating=RatingOut(
                score=forecast.rating_mark,
                label=label,
                total=forecast.n_ratings,
                counts=_counts(extras),
            ),
            next_earnings=(
                datetime.fromtimestamp(forecast.next_earnings, UTC)
                if forecast.next_earnings
                else None
            ),
            estimates=_estimates(extras),
        )


class ErrorResponse(BaseModel):
    """Body of every error answer: a stable machine code and a human message.
    Clients should branch on code; detail is for people and may change.
    The codes are invalid_ticker, ticker_not_found, upstream_error and crawl_timeout.
    """

    code: str = Field(examples=["ticker_not_found"])
    detail: str


def _price_target(ticker: TrackedTicker, forecast: Forecast) -> PriceTargetOut:
    upside = ticker.upside
    return PriceTargetOut(
        average=forecast.pt_avg,
        high=forecast.pt_high,
        low=forecast.pt_low,
        upside_pct=None if upside is None else upside * 100,
        analysts=forecast.n_analysts,
    )


def _counts(extras: Extras | None) -> RatingCountsOut | None:
    if extras is None or extras.rating_counts is None:
        return None
    strong_buy, buy, hold, sell, strong_sell = (n for _, n in extras.rating_counts)
    return RatingCountsOut(
        strong_buy=strong_buy, buy=buy, hold=hold, sell=sell, strong_sell=strong_sell
    )


def _period(period: Period) -> PeriodOut:
    surprise = period.surprise
    return PeriodOut(
        period=period.label,
        reported=period.reported,
        actual=period.actual,
        estimate=period.estimate,
        surprise_pct=None if surprise is None else surprise * 100,
    )


def _estimates(extras: Extras | None) -> EstimatesOut | None:
    if extras is None:
        return None
    return EstimatesOut(
        eps=SeriesOut(
            annual=[_period(p) for p in extras.eps_fy],
            quarterly=[_period(p) for p in extras.eps_fq],
        ),
        revenue=SeriesOut(
            annual=[_period(p) for p in extras.rev_fy],
            quarterly=[_period(p) for p in extras.rev_fq],
        ),
    )
