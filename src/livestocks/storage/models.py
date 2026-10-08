"""SQLite schema (DDL) and the shared SQL fragments built on it."""

SCHEMA_V1 = """
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

FORECAST_COLUMNS = (
    "name, price, change_pct, pt_avg, pt_high, pt_low, n_analysts, rating_mark, n_ratings, ath, next_earnings"
)

# Every tracked ticker joined to its latest forecast snapshot (if any).
TICKER_ROWS_SQL = """
SELECT t.exchange, t.symbol, t.name AS tname, t.added_at, t.last_fetch, t.next_fetch, t.last_error,
       t.fail_count, t.dead, f.fetched_at, f.name, f.price, f.change_pct, f.pt_avg, f.pt_high, f.pt_low,
       f.n_analysts, f.rating_mark, f.n_ratings, f.ath, f.next_earnings
FROM tickers t
LEFT JOIN forecasts f ON f.id = (
    SELECT id FROM forecasts WHERE exchange = t.exchange AND symbol = t.symbol
    ORDER BY fetched_at DESC, id DESC LIMIT 1
)
"""
