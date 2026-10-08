"""SQLite persistence: tracked tickers, crawl status and forecast snapshots.
Operations are tiny and local, so they run synchronously under a lock.
Every method opens its own transaction and is safe to call from any thread.
"""

import json
import sqlite3
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from livestocks.domain import ErrorKind, Extras, Forecast, Period, PriceBar, TrackedTicker
from livestocks.storage.migrations import migrate
from livestocks.storage.models import FORECAST_COLUMNS, TICKER_ROWS_SQL

_FORECAST_COLS = FORECAST_COLUMNS
_ROWS_SQL = TICKER_ROWS_SQL


def _forecast(row: sqlite3.Row) -> Forecast:
    return Forecast(
        exchange=row["exchange"],
        symbol=row["symbol"],
        name=row["name"],
        price=row["price"],
        change_pct=row["change_pct"],
        pt_avg=row["pt_avg"],
        pt_high=row["pt_high"],
        pt_low=row["pt_low"],
        n_analysts=row["n_analysts"],
        rating_mark=row["rating_mark"],
        n_ratings=row["n_ratings"],
        ath=row["ath"],
        next_earnings=row["next_earnings"],
    )


def _ticker_row(row: sqlite3.Row) -> TrackedTicker:
    return TrackedTicker(
        exchange=row["exchange"],
        symbol=row["symbol"],
        name=row["name"] or row["tname"],
        added_at=row["added_at"],
        last_fetch=row["last_fetch"],
        next_fetch=row["next_fetch"],
        last_error=row["last_error"],
        fail_count=row["fail_count"],
        dead=bool(row["dead"]),
        forecast=_forecast(row) if row["fetched_at"] is not None else None,
        fetched_at=row["fetched_at"],
        error_kind=ErrorKind(row["error_kind"]) if row["error_kind"] else None,
    )


class Store:
    """Thread-safe SQLite store for tickers, forecasts, price history and extras.
    Pass ':memory:' for a throwaway database in tests.
    Opening it creates the file and applies any pending schema migrations.
    """

    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            migrate(self._db)

    def close(self) -> None:
        """Close the database connection.
        No method may be called afterwards.
        Registered as a NiceGUI shutdown hook.
        """
        with self._lock:
            self._db.close()

    # ---- tracked tickers ----
    def add_ticker(self, exchange: str, symbol: str, now: int | None = None) -> bool:
        """Start tracking a ticker; returns False if it was already tracked.
        New tickers are due immediately, so the updater crawls them on its next sweep.
        now overrides the creation time and exists for tests.
        """
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO tickers (exchange, symbol, added_at) VALUES (?, ?, ?)",
                (exchange, symbol, now or int(time.time())),
            )
            return cur.rowcount == 1

    def remove_ticker(self, exchange: str, symbol: str) -> None:
        """Stop tracking a ticker and delete its snapshots, prices and extras.
        Does nothing if the ticker is not tracked.
        A crawl already in flight finds the row gone and drops its result.
        """
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM tickers WHERE exchange = ? AND symbol = ?", (exchange, symbol)
            )
            self._db.execute(
                "DELETE FROM forecasts WHERE exchange = ? AND symbol = ?", (exchange, symbol)
            )
            self._db.execute(
                "DELETE FROM prices WHERE exchange = ? AND symbol = ?", (exchange, symbol)
            )
            self._db.execute(
                "DELETE FROM extras WHERE exchange = ? AND symbol = ?", (exchange, symbol)
            )

    def retry(self, exchange: str, symbol: str) -> None:
        """Clear a ticker's failure state so the updater picks it up on its next sweep.
        Resets the fail counter, the dead flag and the last error.
        Used by the retry button and when a failed ticker is added again.
        """
        with self._lock, self._db:
            self._db.execute(
                "UPDATE tickers SET next_fetch = 0, fail_count = 0, dead = 0, last_error = NULL, "
                "error_kind = NULL "
                "WHERE exchange = ? AND symbol = ?",
                (exchange, symbol),
            )

    def retry_all(self) -> None:
        """Make every live ticker due now.
        Dead tickers stay dead until retry() is called for them.
        Lets the UI offer a refresh-everything action.
        """
        with self._lock, self._db:
            self._db.execute("UPDATE tickers SET next_fetch = 0 WHERE dead = 0")

    # ---- reads ----
    def rows(self) -> list[TrackedTicker]:
        """Return every tracked ticker with its latest forecast, oldest first.
        Tickers without a forecast have forecast set to None.
        The status property tells pending, error and failed apart.
        """
        with self._lock:
            return [
                _ticker_row(r)
                for r in self._db.execute(_ROWS_SQL + " ORDER BY t.added_at, t.symbol")
            ]

    def row(self, exchange: str, symbol: str) -> TrackedTicker | None:
        """Return one tracked ticker with its latest forecast, or None if untracked.
        Same shape as the items returned by rows().
        Cheap enough to call on every page refresh.
        """
        with self._lock:
            r = self._db.execute(
                _ROWS_SQL + " WHERE t.exchange = ? AND t.symbol = ?", (exchange, symbol)
            ).fetchone()
        return _ticker_row(r) if r else None

    def history(self, exchange: str, symbol: str, since: int = 0) -> list[tuple[int, Forecast]]:
        """Return every forecast snapshot since a timestamp as (fetched_at, Forecast).
        Ordered oldest first; since is unix seconds and 0 means all.
        Used as a price fallback when no price history exists for an exchange.
        """
        with self._lock:
            cur = self._db.execute(
                f"SELECT exchange, symbol, fetched_at, {_FORECAST_COLS} FROM forecasts "
                "WHERE exchange = ? AND symbol = ? AND fetched_at >= ? ORDER BY fetched_at, id",
                (exchange, symbol, since),
            )
            return [(r["fetched_at"], _forecast(r)) for r in cur]

    def prices(self, exchange: str, symbol: str, since: int = 0) -> list[PriceBar]:
        """Return stored daily closes since a timestamp, oldest first.
        since is unix seconds; 0 returns the whole history.
        Bars come from the price-history crawl, not from forecast snapshots.
        """
        with self._lock:
            cur = self._db.execute(
                "SELECT ts, close FROM prices "
                "WHERE exchange = ? AND symbol = ? AND ts >= ? ORDER BY ts",
                (exchange, symbol, since),
            )
            return [PriceBar(r["ts"], r["close"]) for r in cur]

    def upsert_prices(self, exchange: str, symbol: str, bars: Sequence[PriceBar]) -> None:
        """Insert price bars, replacing any stored bar with the same timestamp.
        Re-crawling the same two-year window is therefore idempotent.
        An empty sequence is allowed and does nothing.
        """
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO prices (exchange, symbol, ts, close) VALUES (?, ?, ?, ?)",
                [(exchange, symbol, b.ts, b.close) for b in bars],
            )

    def save_extras(
        self, exchange: str, symbol: str, extras: Extras, now: int | None = None
    ) -> None:
        """Store the latest EPS, revenue and rating-count extras for a ticker.
        Replaces any previous extras; only the most recent set is kept.
        now overrides the stored timestamp and exists for tests.
        """
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO extras (exchange, symbol, fetched_at, data) "
                "VALUES (?, ?, ?, ?)",
                (exchange, symbol, now or int(time.time()), json.dumps(asdict(extras))),
            )

    def extras(self, exchange: str, symbol: str) -> tuple[int, Extras] | None:
        """Return (fetched_at, Extras) for a ticker, or None if never fetched.
        Extras are stored as JSON and rebuilt into dataclasses on the way out.
        The detail page uses them for the gauge counts and the EPS and revenue charts.
        """
        with self._lock:
            r = self._db.execute(
                "SELECT fetched_at, data FROM extras WHERE exchange = ? AND symbol = ?",
                (exchange, symbol),
            ).fetchone()
        if r is None:
            return None
        d = json.loads(r["data"])
        for k in ("eps_fy", "eps_fq", "rev_fy", "rev_fq"):
            d[k] = tuple(Period(**p) for p in d[k])
        return r["fetched_at"], Extras(**d)

    def queue_missing_extras(self) -> None:
        """Make tickers that were crawled before extras existed due immediately.
        A one-off backfill so older databases gain EPS and revenue data.
        Dead tickers and never-crawled tickers are left alone.
        """
        with self._lock, self._db:
            self._db.execute(
                "UPDATE tickers SET next_fetch = 0 "
                "WHERE dead = 0 AND last_fetch IS NOT NULL AND NOT EXISTS ("
                "SELECT 1 FROM extras e "
                "WHERE e.exchange = tickers.exchange AND e.symbol = tickers.symbol)"
            )

    def due(self, now: int | None = None) -> list[tuple[str, str]]:
        """Return (exchange, symbol) of live tickers whose next fetch time has passed.
        Ordered by how long they have waited; now overrides the clock for tests.
        Dead tickers are never returned.
        """
        with self._lock:
            cur = self._db.execute(
                "SELECT exchange, symbol FROM tickers "
                "WHERE dead = 0 AND next_fetch <= ? ORDER BY next_fetch",
                (now or int(time.time()),),
            )
            return [(r["exchange"], r["symbol"]) for r in cur]

    def next_due_at(self) -> int | None:
        """Return the earliest next_fetch of any live ticker, or None.
        A value in the past means something is due now.
        The updater uses it to show a countdown.
        """
        with self._lock:
            r = self._db.execute(
                "SELECT MIN(next_fetch) AS n FROM tickers WHERE dead = 0"
            ).fetchone()
        return r["n"]

    # ---- crawl results ----
    def record_success(self, f: Forecast, interval: int, now: int | None = None) -> None:
        """Store a forecast snapshot and schedule the next refresh after interval seconds.
        Clears the ticker's failure counters and updates its display name.
        Ignored if the ticker was removed while its crawl was running; now overrides the clock.
        """
        now = now or int(time.time())
        with self._lock, self._db:
            tracked = self._db.execute(
                "SELECT 1 FROM tickers WHERE exchange = ? AND symbol = ?", (f.exchange, f.symbol)
            ).fetchone()
            if tracked is None:  # removed while fetching
                return
            self._db.execute(
                f"INSERT INTO forecasts (exchange, symbol, fetched_at, {_FORECAST_COLS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f.exchange,
                    f.symbol,
                    now,
                    f.name,
                    f.price,
                    f.change_pct,
                    f.pt_avg,
                    f.pt_high,
                    f.pt_low,
                    f.n_analysts,
                    f.rating_mark,
                    f.n_ratings,
                    f.ath,
                    f.next_earnings,
                ),
            )
            self._db.execute(
                "UPDATE tickers SET name = COALESCE(?, name), last_fetch = ?, next_fetch = ?, "
                "last_error = NULL, error_kind = NULL, fail_count = 0, dead = 0 "
                "WHERE exchange = ? AND symbol = ?",
                (f.name, now, now + interval, f.exchange, f.symbol),
            )

    def record_failure(
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
        now = now or int(time.time())
        with self._lock, self._db:
            r = self._db.execute(
                "SELECT fail_count FROM tickers WHERE exchange = ? AND symbol = ?",
                (exchange, symbol),
            ).fetchone()
            if r is None:  # removed while fetching
                return
            fails = r["fail_count"] + 1
            backoff = min(interval, 60 * 2**fails)
            self._db.execute(
                "UPDATE tickers SET fail_count = ?, last_error = ?, error_kind = ?, "
                "next_fetch = ?, dead = ? WHERE exchange = ? AND symbol = ?",
                (
                    fails,
                    error,
                    kind.value if kind else None,
                    now + backoff,
                    int(fails >= max_failures),
                    exchange,
                    symbol,
                ),
            )
