"""Async SQLite persistence: tracked tickers, crawl status and forecast snapshots.
Each method runs in its own short transaction on an SQLAlchemy async session.
Rows are mapped to the domain dataclasses so callers never see ORM objects.
"""

import asyncio
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, func, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from livestocks.domain import ErrorKind, Extras, Forecast, PriceBar, SuggestionReport, TrackedTicker
from livestocks.storage.db import create_engine, upgrade_database
from livestocks.storage.mapping import (
    extras_from_json,
    extras_to_json,
    forecast_from_row,
    forecast_to_row,
    suggestion_from_row,
    tracked_from_rows,
)
from livestocks.storage.models import (
    ExtrasTable,
    ForecastTable,
    PriceTable,
    SuggestionReportTable,
    TickerTable,
)


def _now(now: int | None) -> int:
    return now or int(time.time())


class Store:
    """Async SQLite store for tickers, forecasts, price history and extras.
    Call initialize() once before use and close() when finished.
    Tests pass migrate=False to build the schema straight from the models.
    """

    def __init__(self, path: Path | str, *, migrate: bool = True):
        """Create the engine for a database file; nothing is opened until initialize()."""
        self._path = path
        self._migrate = migrate
        self._engine: AsyncEngine = create_engine(path)
        self._sessions = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize(self) -> None:
        """Create or upgrade the schema so the store is ready for use.
        By default the Alembic migrations run in a worker thread.
        With migrate=False the tables are created straight from the models instead.
        """
        if self._migrate:
            await asyncio.to_thread(upgrade_database, self._path)
        else:
            async with self._engine.begin() as connection:
                await connection.run_sync(SQLModel.metadata.create_all)

    async def close(self) -> None:
        """Release every pooled connection.
        No method may be called afterwards.
        Registered as a NiceGUI shutdown hook.
        """
        await self._engine.dispose()

    # ---- tracked tickers ----
    async def add_ticker(self, exchange: str, symbol: str, now: int | None = None) -> bool:
        """Start tracking a ticker; returns False if it was already tracked.
        New tickers are due immediately, so the updater crawls them on its next sweep.
        now overrides the creation time and exists for tests.
        """
        statement = (
            insert(TickerTable)
            .values(exchange=exchange, symbol=symbol, added_at=_now(now))
            .on_conflict_do_nothing()
        )
        async with self._sessions.begin() as session:
            result = await session.exec(statement)
            return cast("CursorResult[Any]", result).rowcount == 1

    async def remove_ticker(self, exchange: str, symbol: str) -> None:
        """Stop tracking a ticker and delete its snapshots, prices and extras.
        Does nothing if the ticker is not tracked.
        A crawl already in flight finds the row gone and drops its result.
        """
        async with self._sessions.begin() as session:
            for table in (TickerTable, ForecastTable, PriceTable, ExtrasTable):
                await session.exec(
                    delete(table).where(
                        col(table.exchange) == exchange, col(table.symbol) == symbol
                    )
                )

    async def retry(self, exchange: str, symbol: str) -> None:
        """Clear a ticker's failure state so the updater picks it up on its next sweep.
        Resets the fail counter, the dead flag, the last error and its kind.
        Used by the retry button and when a failed ticker is added again.
        """
        async with self._sessions.begin() as session:
            await session.exec(
                update(TickerTable)
                .where(col(TickerTable.exchange) == exchange, col(TickerTable.symbol) == symbol)
                .values(next_fetch=0, fail_count=0, dead=False, last_error=None, error_kind=None)
            )

    async def retry_all(self) -> None:
        """Make every live ticker due now.
        Dead tickers stay dead until retry() is called for them.
        Lets the UI offer a refresh-everything action.
        """
        async with self._sessions.begin() as session:
            await session.exec(
                update(TickerTable).where(col(TickerTable.dead).is_(False)).values(next_fetch=0)
            )

    # ---- reads ----
    def _tickers_with_latest_forecast(self):
        newest = (
            select(
                col(ForecastTable.exchange),
                col(ForecastTable.symbol),
                func.max(col(ForecastTable.id)).label("newest_id"),
            )
            .group_by(col(ForecastTable.exchange), col(ForecastTable.symbol))
            .subquery()
        )
        return (
            select(TickerTable, ForecastTable)
            .outerjoin(
                newest,
                and_(
                    col(TickerTable.exchange) == newest.c.exchange,
                    col(TickerTable.symbol) == newest.c.symbol,
                ),
            )
            .outerjoin(ForecastTable, col(ForecastTable.id) == newest.c.newest_id)
        )

    async def rows(self) -> list[TrackedTicker]:
        """Return every tracked ticker with its latest forecast, oldest first.
        Tickers without a forecast have forecast set to None.
        The status property tells pending, error and failed apart.
        """
        statement = self._tickers_with_latest_forecast().order_by(
            col(TickerTable.added_at), col(TickerTable.symbol)
        )
        async with self._sessions() as session:
            result = await session.exec(statement)
            return [tracked_from_rows(ticker, latest) for ticker, latest in result.all()]

    async def row(self, exchange: str, symbol: str) -> TrackedTicker | None:
        """Return one tracked ticker with its latest forecast, or None if untracked.
        Same shape as the items returned by rows().
        Cheap enough to call on every page refresh.
        """
        statement = self._tickers_with_latest_forecast().where(
            col(TickerTable.exchange) == exchange, col(TickerTable.symbol) == symbol
        )
        async with self._sessions() as session:
            found = (await session.exec(statement)).first()
        return tracked_from_rows(*found) if found else None

    async def history(
        self, exchange: str, symbol: str, since: int = 0
    ) -> list[tuple[int, Forecast]]:
        """Return every forecast snapshot since a timestamp as (fetched_at, Forecast).
        Ordered oldest first; since is unix seconds and 0 means all.
        Used as a price fallback when no price history exists for an exchange.
        """
        statement = (
            select(ForecastTable)
            .where(
                col(ForecastTable.exchange) == exchange,
                col(ForecastTable.symbol) == symbol,
                col(ForecastTable.fetched_at) >= since,
            )
            .order_by(col(ForecastTable.fetched_at), col(ForecastTable.id))
        )
        async with self._sessions() as session:
            rows = (await session.exec(statement)).all()
        return [(row.fetched_at, forecast_from_row(row)) for row in rows]

    async def prices(self, exchange: str, symbol: str, since: int = 0) -> list[PriceBar]:
        """Return stored daily closes since a timestamp, oldest first.
        since is unix seconds; 0 returns the whole history.
        Bars come from the price-history crawl, not from forecast snapshots.
        """
        statement = (
            select(PriceTable)
            .where(
                col(PriceTable.exchange) == exchange,
                col(PriceTable.symbol) == symbol,
                col(PriceTable.ts) >= since,
            )
            .order_by(col(PriceTable.ts))
        )
        async with self._sessions() as session:
            rows = (await session.exec(statement)).all()
        return [PriceBar(row.ts, row.close) for row in rows]

    async def upsert_prices(self, exchange: str, symbol: str, bars: Sequence[PriceBar]) -> None:
        """Insert price bars, replacing any stored bar with the same timestamp.
        Re-crawling the same two-year window is therefore idempotent.
        An empty sequence is allowed and does nothing.
        """
        if not bars:
            return
        statement = insert(PriceTable).values(
            [{"exchange": exchange, "symbol": symbol, "ts": b.ts, "close": b.close} for b in bars]
        )
        statement = statement.on_conflict_do_update(
            index_elements=["exchange", "symbol", "ts"], set_={"close": statement.excluded.close}
        )
        async with self._sessions.begin() as session:
            await session.exec(statement)

    async def save_extras(
        self, exchange: str, symbol: str, extras: Extras, now: int | None = None
    ) -> None:
        """Store the latest EPS, revenue and rating-count extras for a ticker.
        Replaces any previous extras; only the most recent set is kept.
        now overrides the stored timestamp and exists for tests.
        """
        statement = insert(ExtrasTable).values(
            exchange=exchange,
            symbol=symbol,
            fetched_at=_now(now),
            data=extras_to_json(extras),
        )
        statement = statement.on_conflict_do_update(
            index_elements=["exchange", "symbol"],
            set_={"fetched_at": statement.excluded.fetched_at, "data": statement.excluded.data},
        )
        async with self._sessions.begin() as session:
            await session.exec(statement)

    async def extras(self, exchange: str, symbol: str) -> tuple[int, Extras] | None:
        """Return (fetched_at, Extras) for a ticker, or None if never fetched.
        Extras are stored as JSON and rebuilt into dataclasses on the way out.
        The detail page uses them for the gauge counts and the EPS and revenue charts.
        """
        async with self._sessions() as session:
            row = await session.get(ExtrasTable, (exchange, symbol))
        return (row.fetched_at, extras_from_json(row.data)) if row else None

    async def queue_missing_extras(self) -> None:
        """Make tickers that were crawled before extras existed due immediately.
        A one-off backfill so older databases gain EPS and revenue data.
        Dead tickers and never-crawled tickers are left alone.
        """
        has_extras = (
            select(col(ExtrasTable.symbol))
            .where(
                col(ExtrasTable.exchange) == col(TickerTable.exchange),
                col(ExtrasTable.symbol) == col(TickerTable.symbol),
            )
            .exists()
        )
        async with self._sessions.begin() as session:
            await session.exec(
                update(TickerTable)
                .where(
                    col(TickerTable.dead).is_(False),
                    col(TickerTable.last_fetch).is_not(None),
                    ~has_extras,
                )
                .values(next_fetch=0)
            )

    async def due(self, now: int | None = None) -> list[tuple[str, str]]:
        """Return (exchange, symbol) of live tickers whose next fetch time has passed.
        Ordered by how long they have waited; now overrides the clock for tests.
        Dead tickers are never returned.
        """
        statement = (
            select(col(TickerTable.exchange), col(TickerTable.symbol))
            .where(col(TickerTable.dead).is_(False), col(TickerTable.next_fetch) <= _now(now))
            .order_by(col(TickerTable.next_fetch))
        )
        async with self._sessions() as session:
            result = await session.exec(statement)
            return [(exchange, symbol) for exchange, symbol in result.all()]

    async def next_due_at(self) -> int | None:
        """Return the earliest next_fetch of any live ticker, or None.
        A value in the past means something is due now.
        The updater uses it to show a countdown.
        """
        statement = select(func.min(col(TickerTable.next_fetch))).where(
            col(TickerTable.dead).is_(False)
        )
        async with self._sessions() as session:
            return (await session.exec(statement)).one()

    # ---- crawl results ----
    async def record_success(self, f: Forecast, interval: int, now: int | None = None) -> None:
        """Store a forecast snapshot and schedule the next refresh after interval seconds.
        Clears the ticker's failure counters and updates its display name.
        Ignored if the ticker was removed while its crawl was running; now overrides the clock.
        """
        stamp = _now(now)
        async with self._sessions.begin() as session:
            ticker = await session.get(TickerTable, (f.exchange, f.symbol))
            if ticker is None:  # removed while fetching
                return
            session.add(forecast_to_row(f, stamp))
            ticker.name = f.name or ticker.name
            ticker.last_fetch = stamp
            ticker.next_fetch = stamp + interval
            ticker.last_error = None
            ticker.error_kind = None
            ticker.fail_count = 0
            ticker.dead = False
            session.add(ticker)

    async def record_failure(
        self,
        exchange: str,
        symbol: str,
        error: str,
        interval: int,
        max_failures: int,
        now: int | None = None,
        kind: ErrorKind | None = None,
    ) -> None:
        """Count a failed crawl and schedule a retry with exponential backoff.
        After max_failures failures in a row the ticker is marked dead; kind records why it failed.
        Ignored if the ticker was removed while its crawl was running.
        """
        stamp = _now(now)
        async with self._sessions.begin() as session:
            ticker = await session.get(TickerTable, (exchange, symbol))
            if ticker is None:  # removed while fetching
                return
            fails = ticker.fail_count + 1
            ticker.fail_count = fails
            ticker.last_error = error
            ticker.error_kind = kind.value if kind else None
            ticker.next_fetch = stamp + min(interval, 60 * 2**fails)
            ticker.dead = fails >= max_failures
            session.add(ticker)

    # ---- suggestion reports ----
    async def save_suggestions(
        self, date: str, generated_at: str, payload: str, now: int | None = None
    ) -> SuggestionReport:
        """Store the suggestions of a trading day, replacing any earlier report for that date.
        payload is the validated JSON text; now overrides the received time and exists for tests.
        Returns the report as stored.
        """
        stamp = _now(now)
        statement = insert(SuggestionReportTable).values(
            date=date, generated_at=generated_at, received_at=stamp, payload=payload
        )
        statement = statement.on_conflict_do_update(
            index_elements=["date"],
            set_={
                "generated_at": statement.excluded.generated_at,
                "received_at": statement.excluded.received_at,
                "payload": statement.excluded.payload,
            },
        )
        async with self._sessions.begin() as session:
            await session.exec(statement)
        return SuggestionReport(date, generated_at, stamp, payload)

    async def suggestions_on(self, date: str) -> SuggestionReport | None:
        """Return the report for a trading date (YYYY-MM-DD), or None if there is none.
        Dates compare as plain text, which orders them correctly.
        Used by the by-date endpoint.
        """
        async with self._sessions() as session:
            row = await session.get(SuggestionReportTable, date)
        return suggestion_from_row(row) if row else None

    async def latest_suggestions(self) -> SuggestionReport | None:
        """Return the report with the newest trading date, or None if nothing was stored yet.
        The date decides, not the time of arrival, so a late re-run of an old day does not win.
        Used by the latest endpoint.
        """
        statement = select(SuggestionReportTable).order_by(col(SuggestionReportTable.date).desc())
        async with self._sessions() as session:
            row = (await session.exec(statement)).first()
        return suggestion_from_row(row) if row else None

    async def recent_suggestions(self, limit: int) -> list[SuggestionReport]:
        """Return up to limit reports, newest trading date first.
        Each one carries its full payload.
        The list endpoint summarises them.
        """
        statement = (
            select(SuggestionReportTable)
            .order_by(col(SuggestionReportTable.date).desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.exec(statement)).all()
        return [suggestion_from_row(row) for row in rows]
