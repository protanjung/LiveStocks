"""SQLite persistence: tracked tickers, crawl status, and a history of forecast snapshots.

Operations are tiny and local, so they are called synchronously from the event loop under a lock.
"""

import sqlite3
import threading
import time
from pathlib import Path

import json
from dataclasses import asdict

from .models import Extras, Forecast, Period, TickerRow

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
    exchange    TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    name        TEXT,
    added_at    INTEGER NOT NULL,
    last_fetch  INTEGER,
    next_fetch  INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    fail_count  INTEGER NOT NULL DEFAULT 0,
    dead        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (exchange, symbol)
);
CREATE TABLE IF NOT EXISTS forecasts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange      TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    fetched_at    INTEGER NOT NULL,
    name          TEXT,
    price         REAL,
    change_pct    REAL,
    pt_avg        REAL,
    pt_high       REAL,
    pt_low        REAL,
    n_analysts    INTEGER,
    rating_mark   REAL,
    n_ratings     INTEGER,
    ath           REAL,
    next_earnings INTEGER
);
CREATE TABLE IF NOT EXISTS prices (
    exchange TEXT NOT NULL,
    symbol   TEXT NOT NULL,
    ts       INTEGER NOT NULL,
    close    REAL NOT NULL,
    PRIMARY KEY (exchange, symbol, ts)
);
CREATE TABLE IF NOT EXISTS extras (
    exchange   TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    fetched_at INTEGER NOT NULL,
    data       TEXT NOT NULL,
    PRIMARY KEY (exchange, symbol)
);
CREATE INDEX IF NOT EXISTS forecasts_ticker_time ON forecasts (exchange, symbol, fetched_at);
"""

_FORECAST_COLS = (
    "name, price, change_pct, pt_avg, pt_high, pt_low, n_analysts, rating_mark, n_ratings, ath, next_earnings"
)
# Latest forecast per ticker, joined to the ticker row.
_ROWS_SQL = f"""
SELECT t.exchange, t.symbol, t.name AS tname, t.added_at, t.last_fetch, t.next_fetch, t.last_error, t.fail_count, t.dead,
       f.fetched_at, f.name, f.price, f.change_pct, f.pt_avg, f.pt_high, f.pt_low, f.n_analysts,
       f.rating_mark, f.n_ratings, f.ath, f.next_earnings
FROM tickers t
LEFT JOIN forecasts f ON f.id = (
    SELECT id FROM forecasts WHERE exchange = t.exchange AND symbol = t.symbol ORDER BY fetched_at DESC, id DESC LIMIT 1
)
"""


def _forecast(row: sqlite3.Row) -> Forecast:
    return Forecast(
        exchange=row["exchange"], symbol=row["symbol"], name=row["name"], price=row["price"],
        change_pct=row["change_pct"], pt_avg=row["pt_avg"], pt_high=row["pt_high"], pt_low=row["pt_low"],
        n_analysts=row["n_analysts"], rating_mark=row["rating_mark"], n_ratings=row["n_ratings"],
        ath=row["ath"], next_earnings=row["next_earnings"],
    )


def _ticker_row(row: sqlite3.Row) -> TickerRow:
    return TickerRow(
        exchange=row["exchange"], symbol=row["symbol"], name=row["name"] or row["tname"],
        added_at=row["added_at"], last_fetch=row["last_fetch"], next_fetch=row["next_fetch"], last_error=row["last_error"],
        fail_count=row["fail_count"], dead=bool(row["dead"]),
        forecast=_forecast(row) if row["fetched_at"] is not None else None,
        fetched_at=row["fetched_at"],
    )


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ---- tracked tickers ----
    def add_ticker(self, exchange: str, symbol: str, now: int | None = None) -> bool:
        """Track a ticker. Returns False if it was already tracked."""
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO tickers (exchange, symbol, added_at) VALUES (?, ?, ?)",
                (exchange, symbol, now or int(time.time())),
            )
            return cur.rowcount == 1

    def remove_ticker(self, exchange: str, symbol: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM tickers WHERE exchange = ? AND symbol = ?", (exchange, symbol))
            self._db.execute("DELETE FROM forecasts WHERE exchange = ? AND symbol = ?", (exchange, symbol))
            self._db.execute("DELETE FROM prices WHERE exchange = ? AND symbol = ?", (exchange, symbol))
            self._db.execute("DELETE FROM extras WHERE exchange = ? AND symbol = ?", (exchange, symbol))

    def retry(self, exchange: str, symbol: str) -> None:
        """Clear failure state so the updater picks the ticker up on its next sweep."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE tickers SET next_fetch = 0, fail_count = 0, dead = 0, last_error = NULL "
                "WHERE exchange = ? AND symbol = ?",
                (exchange, symbol),
            )

    def retry_all(self) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE tickers SET next_fetch = 0 WHERE dead = 0")

    # ---- reads ----
    def rows(self) -> list[TickerRow]:
        with self._lock:
            return [_ticker_row(r) for r in self._db.execute(_ROWS_SQL + " ORDER BY t.added_at, t.symbol")]

    def row(self, exchange: str, symbol: str) -> TickerRow | None:
        with self._lock:
            r = self._db.execute(
                _ROWS_SQL + " WHERE t.exchange = ? AND t.symbol = ?", (exchange, symbol)
            ).fetchone()
        return _ticker_row(r) if r else None

    def history(self, exchange: str, symbol: str, since: int = 0) -> list[tuple[int, Forecast]]:
        with self._lock:
            cur = self._db.execute(
                f"SELECT exchange, symbol, fetched_at, {_FORECAST_COLS} FROM forecasts "
                "WHERE exchange = ? AND symbol = ? AND fetched_at >= ? ORDER BY fetched_at, id",
                (exchange, symbol, since),
            )
            return [(r["fetched_at"], _forecast(r)) for r in cur]

    def prices(self, exchange: str, symbol: str, since: int = 0) -> list[tuple[int, float]]:
        with self._lock:
            cur = self._db.execute(
                "SELECT ts, close FROM prices WHERE exchange = ? AND symbol = ? AND ts >= ? ORDER BY ts",
                (exchange, symbol, since),
            )
            return [(r["ts"], r["close"]) for r in cur]

    def upsert_prices(self, exchange: str, symbol: str, bars: list[tuple[int, float]]) -> None:
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO prices (exchange, symbol, ts, close) VALUES (?, ?, ?, ?)",
                [(exchange, symbol, ts, close) for ts, close in bars],
            )

    def save_extras(self, exchange: str, symbol: str, extras: Extras, now: int | None = None) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO extras (exchange, symbol, fetched_at, data) VALUES (?, ?, ?, ?)",
                (exchange, symbol, now or int(time.time()), json.dumps(asdict(extras))),
            )

    def extras(self, exchange: str, symbol: str) -> tuple[int, Extras] | None:
        with self._lock:
            r = self._db.execute(
                "SELECT fetched_at, data FROM extras WHERE exchange = ? AND symbol = ?", (exchange, symbol)
            ).fetchone()
        if r is None:
            return None
        d = json.loads(r["data"])
        for k in ("eps_fy", "eps_fq", "rev_fy", "rev_fq"):
            d[k] = tuple(Period(**p) for p in d[k])
        return r["fetched_at"], Extras(**d)

    def queue_missing_extras(self) -> None:
        """Backfill: tickers crawled before extras existed get fetched on the next sweep."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE tickers SET next_fetch = 0 WHERE dead = 0 AND last_fetch IS NOT NULL AND NOT EXISTS ("
                "SELECT 1 FROM extras e WHERE e.exchange = tickers.exchange AND e.symbol = tickers.symbol)"
            )

    def due(self, now: int | None = None) -> list[tuple[str, str]]:
        with self._lock:
            cur = self._db.execute(
                "SELECT exchange, symbol FROM tickers WHERE dead = 0 AND next_fetch <= ? ORDER BY next_fetch",
                (now or int(time.time()),),
            )
            return [(r["exchange"], r["symbol"]) for r in cur]

    def next_due_at(self) -> int | None:
        with self._lock:
            r = self._db.execute("SELECT MIN(next_fetch) AS n FROM tickers WHERE dead = 0").fetchone()
        return r["n"]

    # ---- crawl results ----
    def record_success(self, f: Forecast, interval: int, now: int | None = None) -> None:
        now = now or int(time.time())
        with self._lock, self._db:
            self._db.execute(
                f"INSERT INTO forecasts (exchange, symbol, fetched_at, {_FORECAST_COLS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f.exchange, f.symbol, now, f.name, f.price, f.change_pct, f.pt_avg, f.pt_high, f.pt_low,
                 f.n_analysts, f.rating_mark, f.n_ratings, f.ath, f.next_earnings),
            )
            self._db.execute(
                "UPDATE tickers SET name = COALESCE(?, name), last_fetch = ?, next_fetch = ?, "
                "last_error = NULL, fail_count = 0, dead = 0 WHERE exchange = ? AND symbol = ?",
                (f.name, now, now + interval, f.exchange, f.symbol),
            )

    def record_failure(
        self, exchange: str, symbol: str, error: str, interval: int, max_failures: int, now: int | None = None
    ) -> None:
        """Count a failure; back off exponentially, and stop fetching after ``max_failures`` in a row."""
        now = now or int(time.time())
        with self._lock, self._db:
            r = self._db.execute(
                "SELECT fail_count FROM tickers WHERE exchange = ? AND symbol = ?", (exchange, symbol)
            ).fetchone()
            if r is None:  # removed while fetching
                return
            fails = r["fail_count"] + 1
            backoff = min(interval, 60 * 2**fails)
            self._db.execute(
                "UPDATE tickers SET fail_count = ?, last_error = ?, next_fetch = ?, dead = ? "
                "WHERE exchange = ? AND symbol = ?",
                (fails, error, now + backoff, int(fails >= max_failures), exchange, symbol),
            )
