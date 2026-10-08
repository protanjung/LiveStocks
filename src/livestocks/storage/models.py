"""SQLModel table definitions for tickers, forecast snapshots, prices and extras.
They are the persistence shape only; the rest of the code works with the domain dataclasses.
mapping.py converts between the two, and the Alembic baseline mirrors these tables.
"""

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class TickerTable(SQLModel, table=True):
    """A tracked ticker with its crawl schedule and failure state.
    The primary key is the exchange and symbol pair.
    next_fetch, fail_count and dead drive the updater's schedule.
    """

    __tablename__ = "tickers"  # pyright: ignore[reportAssignmentType]

    exchange: str = Field(primary_key=True)
    symbol: str = Field(primary_key=True)
    name: str | None = None
    added_at: int
    last_fetch: int | None = None
    next_fetch: int = 0
    last_error: str | None = None
    error_kind: str | None = None
    fail_count: int = 0
    dead: bool = False


class ForecastTable(SQLModel, table=True):
    """One forecast snapshot per crawl, kept as history.
    The row with the highest id of a ticker is its current forecast.
    Values are None when TradingView did not publish them.
    """

    __tablename__ = "forecasts"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (Index("forecasts_ticker_time", "exchange", "symbol", "fetched_at"),)

    id: int | None = Field(default=None, primary_key=True)
    exchange: str
    symbol: str
    fetched_at: int
    name: str | None = None
    price: float | None = None
    change_pct: float | None = None
    pt_avg: float | None = None
    pt_high: float | None = None
    pt_low: float | None = None
    n_analysts: int | None = None
    rating_mark: float | None = None
    n_ratings: int | None = None
    ath: float | None = None
    next_earnings: int | None = None


class PriceTable(SQLModel, table=True):
    """One daily close of a ticker, unique per timestamp.
    Re-crawling the same window replaces rows instead of duplicating them.
    ts is a unix timestamp in seconds.
    """

    __tablename__ = "prices"  # pyright: ignore[reportAssignmentType]

    exchange: str = Field(primary_key=True)
    symbol: str = Field(primary_key=True)
    ts: int = Field(primary_key=True)
    close: float


class ExtrasTable(SQLModel, table=True):
    """The latest EPS, revenue and rating-count extras of a ticker, as JSON text.
    Only the most recent set is kept for each ticker.
    fetched_at says when it was crawled.
    """

    __tablename__ = "extras"  # pyright: ignore[reportAssignmentType]

    exchange: str = Field(primary_key=True)
    symbol: str = Field(primary_key=True)
    fetched_at: int
    data: str
