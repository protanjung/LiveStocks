"""Pydantic models that define the JSON the HTTP API returns.
ForecastResponse and the suggestion models (idx-suggestions/v1) are built from service results.
ErrorResponse is the shared error body; percentages are plain numbers, so 46.9 means 46.9%.
"""

import json
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from livestocks.domain import (
    Extras,
    Forecast,
    Period,
    SuggestionReport,
    TickerStatus,
    TrackedTicker,
    rating_label,
)
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
    Codes are listed in docs/api.md, for example ticker_not_found, unauthorized or invalid_payload.
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


class OrderCondition(BaseModel):
    """The price condition of an auto order: price compared with value.
    The operator is <= for a buy and >= for a sell.
    value is a whole rupiah amount on a valid IDX tick.
    """

    type: Literal["price"]
    operator: Literal[">=", "<="]
    value: int


class OrderExecution(BaseModel):
    """How an auto order is executed once its condition is met.
    Only execution by a limit price is used.
    price is a whole rupiah amount.
    """

    by: Literal["price"]
    price: int


class Order(BaseModel):
    """One Growin PRO auto order the user may place: side, stock, dates, condition and lots.
    exits use the same shape with a label, TP1 or STOP.
    qty_lots counts lots of 100 shares.
    """

    label: str | None = None
    side: Literal["BUY", "SELL"]
    stock: str
    start_date: date
    end_date: date
    condition: OrderCondition
    execute: OrderExecution
    qty_lots: int = Field(ge=1)


class Entry(BaseModel):
    """The entry zone of a suggestion and the single limit price to use.
    Any value is null when it could not be supported by the sources.
    Prices are whole rupiah.
    """

    low: int | None = None
    high: int | None = None
    price: int | None = None


class Market(BaseModel):
    """The market snapshot at the top of a brief.
    ihsg_last is the latest IHSG close, or null when unknown.
    summary is the one-line snapshot.
    """

    ihsg_last: float | None = None
    summary: str


class Suggestion(BaseModel):
    """One stock row of the brief: action, size, trade levels and the reason.
    lots is 0 for HOLD; auto_order and exits are only set for a verified BUY or SELL.
    Prices are whole rupiah and stop_pct is a negative percent from the entry price.
    """

    ticker: str = Field(pattern=r"^[A-Z0-9]{1,10}$", examples=["BBCA"])
    name: str
    held: bool
    action: Literal["BUY", "SELL", "HOLD"]
    lots: int = Field(ge=0)
    reference_price: int | None = None
    reference_source: Literal["search", "sheet"] | None = None
    entry: Entry
    tp1: int | None = None
    tp2: int | None = None
    stop: int | None = None
    stop_pct: float | None = None
    rr: float | None = None
    post_trade_weight_pct: float | None = None
    verified: bool
    reason: str
    auto_order: Order | None = None
    exits: list[Order] = []


class SuggestionsPayload(BaseModel):
    """The idx-suggestions/v1 document the scheduled routine delivers once a trading day.
    schema_version is sent under the JSON key schema.
    date is the Jakarta trading date the brief is for.
    """

    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["idx-suggestions/v1"] = Field(alias="schema")
    date: date
    generated_at: datetime
    market: Market
    suggestions: list[Suggestion]
    disclaimer: str


class SuggestionsResponse(SuggestionsPayload):
    """A stored suggestions document as the API returns it.
    received_at says when LiveStocks stored it, as a UTC timestamp.
    Everything else is the delivered payload, validated again on the way out.
    """

    received_at: datetime

    @classmethod
    def from_report(cls, report: SuggestionReport) -> "SuggestionsResponse":
        """Build the response from a stored report by parsing its payload JSON.
        Raises ValueError if the stored text is no longer valid.
        The received time comes from the report, not the payload.
        """
        data = json.loads(report.payload)
        data["received_at"] = datetime.fromtimestamp(report.received_at, UTC)
        return cls.model_validate(data)


class SuggestionAccepted(BaseModel):
    """Answer to a successful delivery of a suggestions document.
    date is the trading date it was stored under; a repeat for the same date replaced the old one.
    count is the number of stock rows it held.
    """

    date: date
    received_at: datetime
    count: int


class SuggestionDay(BaseModel):
    """One line of the suggestions history: a trading date with its action counts.
    Fetch the date for the full table.
    Counts are of stock rows by action.
    """

    date: date
    generated_at: datetime
    received_at: datetime
    ihsg_last: float | None
    summary: str
    buy: int
    sell: int
    hold: int

    @classmethod
    def from_report(cls, report: SuggestionReport) -> "SuggestionDay":
        """Summarise a stored report by parsing its payload JSON.
        Raises ValueError if the stored text is no longer valid.
        Counts the stock rows by action.
        """
        full = SuggestionsResponse.from_report(report)
        actions = [s.action for s in full.suggestions]
        return cls(
            date=full.date,
            generated_at=full.generated_at,
            received_at=full.received_at,
            ihsg_last=full.market.ihsg_last,
            summary=full.market.summary,
            buy=actions.count("BUY"),
            sell=actions.count("SELL"),
            hold=actions.count("HOLD"),
        )
